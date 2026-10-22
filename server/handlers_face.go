package main

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
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

// POST /api/faces/train — up to 15 photos in, one stored set of encodings out.
// Photos are written to a private temp folder for train.py and deleted straight
// after; only the 128-number encodings are kept.
//
// Training can take longer than Cloudflare waits for a response (it answered
// 504), so this only checks and saves the photos, then answers 202 with a job
// ID. The site polls GET /api/faces/train/:id for the outcome.
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
	if job := runningFaceJob(userID); job != "" {
		return c.JSON(http.StatusAccepted, map[string]string{"status": "processing", "job_id": job})
	}

	var req TrainRequest
	if err := c.Bind(&req); err != nil || len(req.Images) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "No photos were received"})
	}
	if len(req.Images) > faceMaxImages {
		req.Images = req.Images[:faceMaxImages]
	}

	workDir, err := os.MkdirTemp("", "face-scan-")
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not process the scan"})
	}

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
		log.Printf("[FACE] Scan from %s rejected: none of %d photos could be read", userID, len(req.Images))
		os.RemoveAll(workDir)
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "None of the photos could be read"})
	}

	job := startFaceJob(userID)
	log.Printf("[FACE] Scan started for %s: %d of %d photos usable", userID, saved, len(req.Images))
	go func() {
		defer os.RemoveAll(workDir)
		code, body := runFaceTraining(userID, workDir)
		finishFaceJob(job, code, body)
	}()
	return c.JSON(http.StatusAccepted, map[string]string{"status": "processing", "job_id": job})
}

// GET /api/faces/train/:id — "processing" until training ends, then the result
// the old synchronous endpoint gave, with its status code.
func getFaceTrainJob(c echo.Context) error {
	faceJobsMu.Lock()
	job, ok := faceJobs[c.Param("id")]
	faceJobsMu.Unlock()
	if !ok || job.userID != getUserIDFromToken(c) {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "That face scan was not found. Please scan again."})
	}
	if !job.done {
		return c.JSON(http.StatusOK, map[string]string{"status": "processing"})
	}
	return c.JSON(job.code, job.body)
}

type faceJob struct {
	userID  string
	started time.Time
	done    bool
	code    int
	body    map[string]interface{}
}

var (
	faceJobsMu sync.Mutex
	faceJobs   = map[string]*faceJob{}
)

func runningFaceJob(userID string) string {
	faceJobsMu.Lock()
	defer faceJobsMu.Unlock()
	for id, j := range faceJobs {
		if j.userID == userID && !j.done {
			return id
		}
	}
	return ""
}

func startFaceJob(userID string) string {
	faceJobsMu.Lock()
	defer faceJobsMu.Unlock()
	for id, j := range faceJobs { // forget results nobody collected
		if time.Since(j.started) > 30*time.Minute {
			delete(faceJobs, id)
		}
	}
	b := make([]byte, 12)
	rand.Read(b)
	id := hex.EncodeToString(b)
	faceJobs[id] = &faceJob{userID: userID, started: time.Now()}
	return id
}

func finishFaceJob(id string, code int, body map[string]interface{}) {
	faceJobsMu.Lock()
	defer faceJobsMu.Unlock()
	if j, ok := faceJobs[id]; ok {
		j.done, j.code, j.body = true, code, body
	}
}

func faceErr(msg string) map[string]interface{} { return map[string]interface{}{"error": msg} }

// runFaceTraining runs train.py over the saved photos and stores the encodings.
func runFaceTraining(userID, workDir string) (int, map[string]interface{}) {
	py := facePython()
	if py == nil {
		log.Printf("[FACE] Scan for %s failed: no Python with face_recognition on this server", userID)
		return http.StatusServiceUnavailable, faceErr("Face scanning is unavailable on the server right now. Please try again later or contact " + ContactEmail + ".")
	}

	outPath := filepath.Join(workDir, "encodings.json")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	started := time.Now()
	cmd := py.command(ctx, "train.py", workDir, outPath)
	out, err := cmd.CombinedOutput()
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	last := strings.TrimSpace(lines[len(lines)-1])
	if err != nil || !strings.HasPrefix(last, "OK:") {
		log.Printf("[FACE] train.py failed for %s after %s: %v: %s", userID, time.Since(started).Round(time.Second), err, strings.TrimSpace(string(out)))
		if strings.HasPrefix(last, "ERROR:") {
			return http.StatusUnprocessableEntity, faceErr(strings.TrimPrefix(last, "ERROR:"))
		}
		return http.StatusInternalServerError, faceErr("The face scan could not be processed. Please try again.")
	}

	var result struct {
		Encodings [][]float64 `json:"encodings"`
		Median    []float64   `json:"median"`
	}
	data, err := os.ReadFile(outPath)
	if err != nil || json.Unmarshal(data, &result) != nil || len(result.Encodings) == 0 {
		return http.StatusInternalServerError, faceErr("The face scan could not be processed. Please try again.")
	}

	if other, dist := closestOtherFace(userID, result.Median); other != "" && dist < faceCollisionDistance {
		db.Exec(`INSERT INTO face_collisions(at, attempted_user, matched_user, distance) VALUES(?, ?, ?, ?)`,
			time.Now().Unix(), userID, other, dist)
		return http.StatusConflict, faceErr("This face is already registered to another account. If you think this is a mistake, contact " + ContactEmail + ".")
	}

	encJSON, _ := json.Marshal(result.Encodings)
	_, err = db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, ?, ?, ?)
		ON CONFLICT(user_id) DO UPDATE SET encodings = excluded.encodings, frames = excluded.frames, trained_at = excluded.trained_at`,
		userID, string(encJSON), len(result.Encodings), time.Now().Unix())
	if err != nil {
		log.Printf("[FACE] saving encodings for %s: %v", userID, err)
		return http.StatusInternalServerError, faceErr("Could not save the face scan")
	}

	log.Printf("[FACE] %s scanned: %d frames kept (%s)", userID, len(result.Encodings), time.Since(started).Round(time.Second))
	return http.StatusOK, map[string]interface{}{
		"status":      "trained",
		"frames_used": len(result.Encodings),
	}
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
