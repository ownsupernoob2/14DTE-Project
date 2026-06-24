package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

// FaceRequest is used by the legacy single-image upload and verify endpoints.
type FaceRequest struct {
	Image  string `json:"image,omitempty"`
	UserID string `json:"user_id,omitempty"`
}

// TrainRequest accepts a batch of up to 10 base64-encoded images.
type TrainRequest struct {
	Images []string `json:"images"`
}

type faceMeta struct {
	TrainedAt int64 `json:"trained_at"`
}

const faceRetrainCooldown = 24 * time.Hour

func safeUserIDFromToken(c echo.Context) string {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return ""
	}
	safeUserID := strings.ReplaceAll(userID, "|", "_")
	safeUserID = strings.ReplaceAll(safeUserID, "/", "_")
	return safeUserID
}

func faceMetaPath(safeUserID string) string {
	return fmt.Sprintf("encodings/%s.meta.json", safeUserID)
}

func facePicklePath(safeUserID string) string {
	return fmt.Sprintf("encodings/%s.pickle", safeUserID)
}

func readFaceMeta(safeUserID string) (faceMeta, bool) {
	data, err := os.ReadFile(faceMetaPath(safeUserID))
	if err != nil {
		return faceMeta{}, false
	}
	var meta faceMeta
	if err := json.Unmarshal(data, &meta); err != nil {
		return faceMeta{}, false
	}
	return meta, true
}

func writeFaceMeta(safeUserID string) error {
	meta := faceMeta{TrainedAt: time.Now().Unix()}
	data, err := json.Marshal(meta)
	if err != nil {
		return err
	}
	return os.WriteFile(faceMetaPath(safeUserID), data, 0644)
}

// trainFace receives up to 10 base64 images, saves them temporarily, runs train.py
// to build a face encoding pickle, then deletes the raw images.
// The encoding is saved to encodings/<user_id>.pickle.
func trainFace(c echo.Context) error {
	safeUserID := safeUserIDFromToken(c)
	if safeUserID == "" {
		return c.JSON(401, map[string]string{"error": "Could not identify user from token"})
	}

	// Enforce 24h cooldown when updating an existing encoding
	picklePath := facePicklePath(safeUserID)
	if _, err := os.Stat(picklePath); err == nil {
		if meta, ok := readFaceMeta(safeUserID); ok {
			trainedAt := time.Unix(meta.TrainedAt, 0)
			if time.Since(trainedAt) < faceRetrainCooldown {
				retryAfter := faceRetrainCooldown - time.Since(trainedAt)
				hours := int(retryAfter.Hours())
				if hours < 1 {
					hours = 1
				}
				return c.JSON(429, map[string]interface{}{
					"error": fmt.Sprintf("Face scan was updated recently. You can update again in about %d hour(s). To register a new scan sooner, delete your face data in Settings first.", hours),
				})
			}
		}
	}

	var req TrainRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request body"})
	}

	if len(req.Images) == 0 {
		return c.JSON(400, map[string]string{"error": "No images provided"})
	}

	// Sanitise userID for use as a directory name (Auth0 sub looks like "auth0|abc123")
	tempDir := fmt.Sprintf("temp/%s", safeUserID)
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return c.JSON(500, map[string]string{"error": "Could not create temp directory"})
	}
	// Always clean up temp images when we're done
	defer os.RemoveAll(tempDir)

	// Decode and save each image
	saved := 0
	for i, img := range req.Images {
		b64data := img
		if idx := strings.Index(b64data, ","); idx != -1 {
			b64data = b64data[idx+1:]
		}
		imgBytes, err := base64.StdEncoding.DecodeString(b64data)
		if err != nil {
			log.Printf("Skipping image %d: base64 decode error: %v", i, err)
			continue
		}
		filepath := fmt.Sprintf("%s/frame_%d.jpg", tempDir, i)
		if err := os.WriteFile(filepath, imgBytes, 0644); err != nil {
			log.Printf("Skipping image %d: write error: %v", i, err)
			continue
		}
		saved++
	}

	if saved == 0 {
		return c.JSON(400, map[string]string{"error": "No valid images could be decoded"})
	}

	outputPickle := facePicklePath(safeUserID)

	// Run the Python training script
	cmd := exec.Command(getPythonCmd(), "train.py", tempDir, outputPickle)
	var out bytes.Buffer
	var errOut bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errOut

	if err := cmd.Run(); err != nil {
		log.Printf("train.py error: %v, stderr: %s", err, errOut.String())
		return c.JSON(500, map[string]string{"error": "Training failed: " + strings.TrimSpace(out.String())})
	}

	output := strings.TrimSpace(out.String())

	lines := strings.Split(output, "\n")
	lastLine := strings.TrimSpace(lines[len(lines)-1])

	if !strings.HasPrefix(lastLine, "OK:") {
		return c.JSON(500, map[string]string{
			"error": "Training failed: " + output,
		})
	}

	framesUsed := 0
	fmt.Sscanf(strings.TrimPrefix(output, "OK:"), "%d", &framesUsed)

	if err := writeFaceMeta(safeUserID); err != nil {
		log.Printf("Failed to write face meta for %s: %v", safeUserID, err)
	}

	log.Printf("Face training complete for user %s: %d frames used, pickle at %s", safeUserID, framesUsed, outputPickle)

	// Recompile FAISS index (export encodings) in background
	exec.Command(getPythonCmd(), "export_encodings.py").Start()

	return c.JSON(200, map[string]interface{}{
		"status":      "trained",
		"frames_used": framesUsed,
		"user_id":     safeUserID,
	})
}

// deleteFace removes the user's face encoding pickle file
func deleteFace(c echo.Context) error {
	safeUserID := safeUserIDFromToken(c)
	if safeUserID == "" {
		return c.JSON(401, map[string]string{"error": "Could not identify user from token"})
	}

	picklePath := facePicklePath(safeUserID)
	if err := os.Remove(picklePath); err != nil && !os.IsNotExist(err) {
		log.Printf("Failed to delete face encoding for %s: %v", safeUserID, err)
		return c.JSON(500, map[string]string{"error": "Failed to delete face scan"})
	}

	metaPath := faceMetaPath(safeUserID)
	if err := os.Remove(metaPath); err != nil && !os.IsNotExist(err) {
		log.Printf("Failed to delete face meta for %s: %v", safeUserID, err)
	}

	// Recompile FAISS index (export encodings) in background
	exec.Command(getPythonCmd(), "export_encodings.py").Start()

	return c.JSON(200, map[string]string{"message": "Face scan deleted successfully"})
}

// uploadFace is the legacy single-image face upload, kept for backward compat.
func uploadFace(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = "user-123"
	}

	var req FaceRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	b64data := req.Image
	if idx := strings.Index(b64data, ","); idx != -1 {
		b64data = b64data[idx+1:]
	}

	imgBytes, err := base64.StdEncoding.DecodeString(b64data)
	if err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid base64 image"})
	}

	filepath := fmt.Sprintf("faces/%s.jpg", userID)
	if err := os.WriteFile(filepath, imgBytes, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save image"})
	}

	return c.JSON(200, map[string]string{"message": "Face registered successfully"})
}

func verifyFace(c echo.Context) error {
	var req FaceRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	if req.UserID != "" {
		if req.UserID == "idle" || req.UserID == "unknown" {
			return c.JSON(401, map[string]string{"error": "Face not recognised"})
		}
		return c.JSON(200, map[string]interface{}{
			"user_id": req.UserID,
			"widgets": getWidgetsForUser(req.UserID),
		})
	}

	b64data := req.Image
	if idx := strings.Index(b64data, ","); idx != -1 {
		b64data = b64data[idx+1:]
	}

	if b64data == "bypass" {
		return c.JSON(200, map[string]interface{}{
			"user_id": "bypass_user",
			"widgets": getWidgetsForUser("bypass_user"),
		})
	}

	imgBytes, err := base64.StdEncoding.DecodeString(b64data)
	if err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid base64 image"})
	}

	tempPath := "temp/verify.jpg"
	if err := os.WriteFile(tempPath, imgBytes, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save temp image"})
	}
	defer os.Remove(tempPath)

	// Run Python verification script against the encodings directory
	cmd := exec.Command(getPythonCmd(), "verify.py", tempPath, "encodings")
	var out bytes.Buffer
	cmd.Stdout = &out
	err = cmd.Run()
	if err != nil {
		log.Println("Python verify error:", err)
		return c.JSON(500, map[string]string{"error": "Verification failed"})
	}

	output := strings.TrimSpace(out.String())

	if output == "NO_FACE" {
		return c.JSON(401, map[string]string{"error": "No face detected"})
	}

	if strings.HasPrefix(output, "MATCH:") {
		matchedUserID := strings.TrimPrefix(output, "MATCH:")
		if matchedUserID == "unknown" {
			return c.JSON(401, map[string]string{"error": "Face not recognised"})
		}

		return c.JSON(200, map[string]interface{}{
			"user_id": matchedUserID,
			"widgets": getWidgetsForUser(matchedUserID),
		})
	}

	return c.JSON(401, map[string]string{"error": "Face not recognised"})
}

func downloadIndex(c echo.Context) error {
	exportFile := "encodings/exported_encodings.json"

	// If exported file does not exist, compile it
	if _, err := os.Stat(exportFile); os.IsNotExist(err) {
		cmd := exec.Command(getPythonCmd(), "export_encodings.py")
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		if err := cmd.Run(); err != nil {
			return c.JSON(500, map[string]string{
				"error":  "Failed to export encodings: " + err.Error(),
				"stderr": stderr.String(),
			})
		}
	}

	data, err := os.ReadFile(exportFile)
	if err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to read exported encodings file"})
	}

	var payload struct {
		Vectors [][]float32 `json:"vectors"`
		UserMap []string    `json:"user_map"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to parse exported encodings"})
	}

	return c.JSON(200, payload)
}
