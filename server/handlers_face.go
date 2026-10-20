package main

import (
	"context"
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

const (
	faceRetrainCooldown = 24 * time.Hour
	faceMaxImages       = 15
	faceMaxImageBytes   = 3 << 20
	// Two different people's encodings are almost never this close; a new scan
	// this near an existing one is the same face on a second account.
	faceCollisionDistance = 0.38
)

type TrainRequest struct {
	Images []string `json:"images"`
}

func faceUnavailable(c echo.Context) error {
	return c.JSON(http.StatusServiceUnavailable, map[string]string{
		"error": "Face scanning is unavailable on the server right now. Please try again later or contact " + ContactEmail + ".",
	})
}

// POST /api/faces/train — up to 15 photos in, one stored set of encodings out.
// Photos are written to a private temp folder for train.py and deleted straight
// after; only the 128-number encodings are kept.
func trainFace(c echo.Context) error {
	userID := getUserIDFromToken(c)

	var trainedAt int64
	if err := db.QueryRow(`SELECT trained_at FROM faces WHERE user_id = ?`, userID).Scan(&trainedAt); err == nil {
		if wait := faceRetrainCooldown - time.Since(time.Unix(trainedAt, 0)); wait > 0 {
			hours := int(math.Ceil(wait.Hours()))
			return c.JSON(http.StatusTooManyRequests, map[string]string{
				"error": fmt.Sprintf("Your face scan was updated recently. You can update it again in about %d hour(s), or delete it in Settings and scan again now.", hours),
			})
		}
	}

	var req TrainRequest
	if err := c.Bind(&req); err != nil || len(req.Images) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "No photos were received"})
	}
	if len(req.Images) > faceMaxImages {
		req.Images = req.Images[:faceMaxImages]
	}

	py := facePython()
	if py == nil {
		return faceUnavailable(c)
	}

	workDir, err := os.MkdirTemp("", "face-scan-")
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not process the scan"})
	}
	defer os.RemoveAll(workDir)

	saved := 0
	for i, img := range req.Images {
		if idx := strings.Index(img, ","); idx != -1 {
			img = img[idx+1:]
		}
		raw, err := base64.StdEncoding.DecodeString(img)
		if err != nil || len(raw) == 0 || len(raw) > faceMaxImageBytes {
			continue
		}
		if ct := http.DetectContentType(raw); ct != "image/jpeg" && ct != "image/png" {
			continue
		}
		if os.WriteFile(filepath.Join(workDir, fmt.Sprintf("frame_%02d.jpg", i)), raw, 0600) == nil {
			saved++
		}
	}
	if saved == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "None of the photos could be read"})
	}

	outPath := filepath.Join(workDir, "encodings.json")
	ctx, cancel := context.WithTimeout(c.Request().Context(), 3*time.Minute)
	defer cancel()
	cmd := py.command(ctx, "train.py", workDir, outPath)
	out, err := cmd.CombinedOutput()
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	last := strings.TrimSpace(lines[len(lines)-1])
	if err != nil || !strings.HasPrefix(last, "OK:") {
		log.Printf("[FACE] train.py failed for %s: %v: %s", userID, err, strings.TrimSpace(string(out)))
		if strings.HasPrefix(last, "ERROR:") {
			return c.JSON(http.StatusUnprocessableEntity, map[string]string{"error": strings.TrimPrefix(last, "ERROR:")})
		}
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "The face scan could not be processed. Please try again."})
	}

	var result struct {
		Encodings [][]float64 `json:"encodings"`
		Median    []float64   `json:"median"`
	}
	data, err := os.ReadFile(outPath)
	if err != nil || json.Unmarshal(data, &result) != nil || len(result.Encodings) == 0 {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "The face scan could not be processed. Please try again."})
	}

	if other, dist := closestOtherFace(userID, result.Median); other != "" && dist < faceCollisionDistance {
		db.Exec(`INSERT INTO face_collisions(at, attempted_user, matched_user, distance) VALUES(?, ?, ?, ?)`,
			time.Now().Unix(), userID, other, dist)
		return c.JSON(http.StatusConflict, map[string]string{
			"error": "This face is already registered to another account. If you think this is a mistake, contact " + ContactEmail + ".",
		})
	}

	encJSON, _ := json.Marshal(result.Encodings)
	_, err = db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, ?, ?, ?)
		ON CONFLICT(user_id) DO UPDATE SET encodings = excluded.encodings, frames = excluded.frames, trained_at = excluded.trained_at`,
		userID, string(encJSON), len(result.Encodings), time.Now().Unix())
	if err != nil {
		log.Printf("[FACE] saving encodings for %s: %v", userID, err)
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save the face scan"})
	}

	log.Printf("[FACE] %s scanned: %d frames kept", userID, len(result.Encodings))
	return c.JSON(http.StatusOK, map[string]interface{}{
		"status":      "trained",
		"frames_used": len(result.Encodings),
	})
}

// closestOtherFace returns the other user whose encodings come nearest to probe.
func closestOtherFace(userID string, probe []float64) (string, float64) {
	rows, err := db.Query(`SELECT user_id, encodings FROM faces WHERE user_id != ?`, userID)
	if err != nil {
		return "", math.Inf(1)
	}
	defer rows.Close()
	best, bestDist := "", math.Inf(1)
	for rows.Next() {
		var other, raw string
		var encs [][]float64
		if rows.Scan(&other, &raw) != nil || json.Unmarshal([]byte(raw), &encs) != nil {
			continue
		}
		for _, e := range encs {
			if d := euclidean(probe, e); d < bestDist {
				best, bestDist = other, d
			}
		}
	}
	return best, bestDist
}

func euclidean(a, b []float64) float64 {
	if len(a) != len(b) {
		return math.Inf(1)
	}
	var s float64
	for i := range a {
		d := a[i] - b[i]
		s += d * d
	}
	return math.Sqrt(s)
}

// DELETE /api/faces/me
func deleteFace(c echo.Context) error {
	if _, err := db.Exec(`DELETE FROM faces WHERE user_id = ?`, getUserIDFromToken(c)); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to delete face scan"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Face scan deleted"})
}

// GET /api/download-index (mirror) — every stored encoding with its owner, for
// the mirror's local matcher.
func downloadIndex(c echo.Context) error {
	rows, err := db.Query(`SELECT user_id, encodings FROM faces ORDER BY user_id`)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not read face index"})
	}
	defer rows.Close()
	vectors := [][]float64{}
	userMap := []string{}
	for rows.Next() {
		var uid, raw string
		var encs [][]float64
		if rows.Scan(&uid, &raw) != nil || json.Unmarshal([]byte(raw), &encs) != nil {
			continue
		}
		for _, e := range encs {
			vectors = append(vectors, e)
			userMap = append(userMap, uid)
		}
	}
	return c.JSON(http.StatusOK, map[string]interface{}{"vectors": vectors, "user_map": userMap})
}

// POST /api/verify-face (mirror) — the mirror matched a face locally and asks
// for that user's dashboard.
func verifyFace(c echo.Context) error {
	var req struct {
		UserID string `json:"user_id"`
	}
	if err := c.Bind(&req); err != nil || req.UserID == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "user_id required"})
	}
	var one int
	if err := db.QueryRow(`SELECT 1 FROM faces WHERE user_id = ?`, req.UserID).Scan(&one); err != nil {
		if err == sql.ErrNoRows {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Face not recognised"})
		}
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Lookup failed"})
	}
	return c.JSON(http.StatusOK, mirrorUserPayload(req.UserID, "face"))
}

func mirrorUserPayload(userID, authMethod string) map[string]interface{} {
	cfg := getDashboardConfigForUser(userID)
	widgets := []Widget{}
	for _, s := range cfg.Slots {
		widgets = append(widgets, s.Widget)
	}
	var name, language string
	db.QueryRow(`SELECT name, language FROM users WHERE id = ?`, userID).Scan(&name, &language)
	return map[string]interface{}{
		"user_id":     userID,
		"user_name":   name,
		"language":    language,
		"widgets":     widgets,
		"config":      cfg,
		"auth_method": authMethod,
	}
}
