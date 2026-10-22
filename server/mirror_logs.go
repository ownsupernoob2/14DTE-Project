package main

// mirror_logs.go — each mirror's daemon logs, viewable in the admin dashboard.
//
// Mirrors post the tail of their logs (mirror UI, face, gesture, camera) with
// their key; the server keeps the newest copy per mirror under
// data/mirror_logs/<mirror_id>/, capped in size.

import (
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/labstack/echo/v4"
)

const mirrorLogMaxBytes = 512 << 10

var (
	mirrorLogsMu  sync.Mutex
	mirrorIDClean = regexp.MustCompile(`[^A-Za-z0-9._-]+`)
	logFileNames  = map[string]string{
		"mirror":  "mirror.log",
		"face":    "face_daemon.log",
		"gesture": "gesture_daemon.log",
		"rpicam":  "rpicam.log",
		"ffmpeg":  "ffmpeg.log",
		"start":   "start.log",
	}
	logAliases = map[string]string{
		"smart_mirror": "mirror", "smart_mirror_pro": "mirror",
		"face_daemon": "face", "face_recognize": "face",
		"gesture_daemon": "gesture", "gesture_engine": "gesture",
		"rpicam-vid": "rpicam", "libcamera": "rpicam", "libcamera-vid": "rpicam",
		"start_smart_mirror": "start",
	}
)

func mirrorLogsDir() string { return dataPath("mirror_logs") }

// safeMirrorID turns whatever a mirror calls itself into one safe folder name.
func safeMirrorID(id string) string {
	id = strings.Trim(mirrorIDClean.ReplaceAllString(strings.TrimSpace(id), "-"), ".-")
	if len(id) > 40 {
		id = id[:40]
	}
	if id == "" {
		return "unknown"
	}
	return id
}

func resolveLogFileName(name string) (string, string, bool) {
	key := strings.TrimSuffix(strings.ToLower(strings.TrimSpace(name)), ".log")
	if alias, ok := logAliases[key]; ok {
		key = alias
	}
	file, ok := logFileNames[key]
	return key, file, ok
}

func tailBytes(s string, max int) string {
	if len(s) <= max {
		return s
	}
	s = s[len(s)-max:]
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		s = s[i+1:] // start on a whole line
	}
	return s
}

// POST /api/logs (mirror) — {mirror_id, logs: {mirror: "...", face: "...", ...}}
func receiveMirrorLogs(c echo.Context) error {
	var req struct {
		MirrorID string            `json:"mirror_id"`
		Logs     map[string]string `json:"logs"`
		Name     string            `json:"name"`
		Content  string            `json:"content"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid JSON payload"})
	}
	if req.Name != "" {
		if req.Logs == nil {
			req.Logs = map[string]string{}
		}
		req.Logs[req.Name] = req.Content
	}
	dir := filepath.Join(mirrorLogsDir(), safeMirrorID(req.MirrorID))

	mirrorLogsMu.Lock()
	defer mirrorLogsMu.Unlock()
	if err := os.MkdirAll(dir, 0755); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not store logs"})
	}
	saved := []string{}
	for name, content := range req.Logs {
		key, file, ok := resolveLogFileName(name)
		if !ok {
			continue
		}
		if err := os.WriteFile(filepath.Join(dir, file), []byte(tailBytes(content, mirrorLogMaxBytes)), 0644); err == nil {
			saved = append(saved, key)
		}
	}
	if len(saved) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "No recognised logs (mirror, face, gesture, rpicam, ffmpeg, start)"})
	}
	sort.Strings(saved)
	return c.JSON(http.StatusOK, map[string]interface{}{"status": "ok", "saved": saved})
}

type mirrorLogSummary struct {
	ID        string `json:"id"`
	UpdatedAt int64  `json:"updated_at"`
}

func listLoggedMirrors() []mirrorLogSummary {
	out := []mirrorLogSummary{}
	entries, err := os.ReadDir(mirrorLogsDir())
	if err != nil {
		return out
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		var newest int64
		files, _ := os.ReadDir(filepath.Join(mirrorLogsDir(), e.Name()))
		for _, f := range files {
			if info, err := f.Info(); err == nil && info.ModTime().Unix() > newest {
				newest = info.ModTime().Unix()
			}
		}
		out = append(out, mirrorLogSummary{ID: e.Name(), UpdatedAt: newest})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].UpdatedAt > out[j].UpdatedAt })
	return out
}

// GET /api/admin/logs?mirror=<id>&name=<log> (admin) — the newest copy of one
// log, plus every mirror that has reported (most recent first).
func getAdminLogs(c echo.Context) error {
	// This server's own logs, not a mirror's: its log, and the Windows
	// auto-updater's (which includes the face-scanning Python setup).
	ownLogs := map[string]string{"server": serverLogPath(), "updater": "updater.log"}
	if path, ok := ownLogs[c.QueryParam("name")]; ok {
		resp := map[string]interface{}{"name": c.QueryParam("name"), "mirrors": listLoggedMirrors(), "content": "", "updated_at": int64(0)}
		data, err := os.ReadFile(path)
		if err != nil {
			resp["content"] = "This log is empty (or this server has no auto-updater)."
			return c.JSON(http.StatusOK, resp)
		}
		resp["content"] = tailBytes(string(data), mirrorLogMaxBytes)
		if info, err := os.Stat(path); err == nil {
			resp["updated_at"] = info.ModTime().Unix()
		}
		return c.JSON(http.StatusOK, resp)
	}
	key, file, ok := resolveLogFileName(firstNonEmpty(c.QueryParam("name"), "mirror"))
	if !ok {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Unknown log"})
	}
	mirrors := listLoggedMirrors()
	mirror := c.QueryParam("mirror")
	if mirror == "" && len(mirrors) > 0 {
		mirror = mirrors[0].ID
	}
	resp := map[string]interface{}{"name": key, "mirror": mirror, "mirrors": mirrors, "content": "", "updated_at": int64(0)}
	if mirror == "" {
		resp["content"] = "No mirror has sent logs yet."
		return c.JSON(http.StatusOK, resp)
	}
	path := filepath.Join(mirrorLogsDir(), safeMirrorID(mirror), file)
	mirrorLogsMu.Lock()
	data, err := os.ReadFile(path)
	info, _ := os.Stat(path)
	mirrorLogsMu.Unlock()
	if err != nil {
		resp["content"] = "This mirror hasn't sent " + file + " yet."
		return c.JSON(http.StatusOK, resp)
	}
	resp["content"] = string(data)
	if info != nil {
		resp["updated_at"] = info.ModTime().Unix()
	}
	resp["fetched_at"] = time.Now().Unix()
	return c.JSON(http.StatusOK, resp)
}
