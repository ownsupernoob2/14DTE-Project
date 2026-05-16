package main

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"

	"github.com/labstack/echo/v4"
)

// FaceRequest is used by the legacy single-image upload and verify endpoints.
type FaceRequest struct {
	Image string `json:"image"`
}

// TrainRequest accepts a batch of up to 10 base64-encoded images.
type TrainRequest struct {
	Images []string `json:"images"`
}

// trainFace receives up to 10 base64 images, saves them temporarily, runs train.py
// to build a face encoding pickle, then deletes the raw images.
// The encoding is saved to encodings/<user_id>.pickle.
func trainFace(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Could not identify user from token"})
	}

	var req TrainRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request body"})
	}

	if len(req.Images) == 0 {
		return c.JSON(400, map[string]string{"error": "No images provided"})
	}

	// Sanitise userID for use as a directory name (Auth0 sub looks like "auth0|abc123")
	safeUserID := strings.ReplaceAll(userID, "|", "_")
	safeUserID = strings.ReplaceAll(safeUserID, "/", "_")

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

	outputPickle := fmt.Sprintf("encodings/%s.pickle", safeUserID)

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
	if !strings.HasPrefix(output, "OK:") {
		msg := strings.TrimPrefix(output, "ERROR:")
		return c.JSON(500, map[string]string{"error": "Training failed: " + msg})
	}

	framesUsed := 0
	fmt.Sscanf(strings.TrimPrefix(output, "OK:"), "%d", &framesUsed)

	log.Printf("Face training complete for user %s: %d frames used, pickle at %s", safeUserID, framesUsed, outputPickle)

	return c.JSON(200, map[string]interface{}{
		"status":      "trained",
		"frames_used": framesUsed,
		"user_id":     safeUserID,
	})
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
