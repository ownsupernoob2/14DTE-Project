package main

// screensaver.go — what the mirrors show while nobody is in front of them.
//
//   demo       the gesture demo video (built into the mirror)
//   slideshow  images uploaded here, shown in turn
//   logo       one uploaded image, centred
//
// Mirrors poll GET /api/screensaver, download any image they don't have yet by
// its SHA-256, and keep showing their cached copy while the server is offline.

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"time"

	"github.com/labstack/echo/v4"
)

const (
	screensaverMaxBytes  = 10 << 20
	screensaverMaxSlides = 40
)

var sha256Re = regexp.MustCompile(`^[0-9a-f]{64}$`)

var imageExts = map[string]string{"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

type ScreensaverConfig struct {
	Mode         string `json:"mode"`
	SlideSeconds int    `json:"slide_seconds"`
	UpdatedAt    int64  `json:"updated_at"`
}

type screensaverImage struct {
	ID          int64  `json:"id"`
	Kind        string `json:"kind"`
	SHA256      string `json:"sha256"`
	Ext         string `json:"ext"`
	ContentType string `json:"content_type"`
	Size        int64  `json:"size"`
	URL         string `json:"url"`
}

func screensaverDir() string { return dataPath("screensaver") }

func loadScreensaverConfig() ScreensaverConfig {
	cfg := ScreensaverConfig{Mode: "demo", SlideSeconds: 8}
	getSetting("screensaver", &cfg)
	return cfg
}

func listScreensaverImages(kind string) []screensaverImage {
	out := []screensaverImage{}
	rows, err := db.Query(`SELECT id, kind, sha256, ext, content_type, size FROM screensaver_images
		WHERE kind = ? ORDER BY position, id`, kind)
	if err != nil {
		return out
	}
	defer rows.Close()
	for rows.Next() {
		var img screensaverImage
		if rows.Scan(&img.ID, &img.Kind, &img.SHA256, &img.Ext, &img.ContentType, &img.Size) == nil {
			img.URL = "/api/screensaver/files/" + img.SHA256 + "." + img.Ext
			out = append(out, img)
		}
	}
	return out
}

// GET /api/screensaver — public; mirrors and the admin page both read it.
func getScreensaver(c echo.Context) error {
	cfg := loadScreensaverConfig()
	var logo interface{}
	if logos := listScreensaverImages("logo"); len(logos) > 0 {
		logo = logos[0]
	}
	return c.JSON(http.StatusOK, map[string]interface{}{
		"mode":          cfg.Mode,
		"slide_seconds": cfg.SlideSeconds,
		"updated_at":    cfg.UpdatedAt,
		"slides":        listScreensaverImages("slide"),
		"logo":          logo,
	})
}

// GET /api/screensaver/files/:name — <sha256>.<ext>, immutable.
func getScreensaverFile(c echo.Context) error {
	name := filepath.Base(c.Param("name"))
	ext := filepath.Ext(name)
	if len(ext) < 2 || !sha256Re.MatchString(name[:len(name)-len(ext)]) {
		return c.NoContent(http.StatusNotFound)
	}
	path := filepath.Join(screensaverDir(), name)
	if _, err := os.Stat(path); err != nil {
		return c.NoContent(http.StatusNotFound)
	}
	c.Response().Header().Set("Cache-Control", "public, max-age=31536000, immutable")
	c.Response().Header().Set("X-Content-Type-Options", "nosniff")
	return c.File(path)
}

// POST /api/admin/screensaver (admin) — {mode, slide_seconds}
func setScreensaverConfig(c echo.Context) error {
	var req struct {
		Mode         string `json:"mode"`
		SlideSeconds int    `json:"slide_seconds"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request"})
	}
	cfg := loadScreensaverConfig()
	if req.Mode != "" {
		cfg.Mode = oneOf(req.Mode, "demo", "slideshow", "logo")
	}
	if req.SlideSeconds > 0 {
		if req.SlideSeconds < 3 {
			req.SlideSeconds = 3
		}
		if req.SlideSeconds > 120 {
			req.SlideSeconds = 120
		}
		cfg.SlideSeconds = req.SlideSeconds
	}
	if cfg.Mode == "slideshow" && len(listScreensaverImages("slide")) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Upload at least one slideshow image first."})
	}
	if cfg.Mode == "logo" && len(listScreensaverImages("logo")) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Upload a logo first."})
	}
	cfg.UpdatedAt = time.Now().Unix()
	if err := setSetting("screensaver", cfg); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save"})
	}
	auditAdmin(c, "screensaver_mode", "", fmt.Sprintf("%s/%ds", cfg.Mode, cfg.SlideSeconds))
	return getScreensaver(c)
}

// POST /api/admin/screensaver/images?kind=slide|logo (admin) — multipart "files".
// A new logo replaces the old one.
func uploadScreensaverImages(c echo.Context) error {
	kind := oneOf(c.QueryParam("kind"), "slide", "logo")
	form, err := c.MultipartForm()
	if err != nil || len(form.File["files"]) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Choose at least one image"})
	}
	files := form.File["files"]
	if kind == "logo" {
		files = files[:1]
	} else if have := len(listScreensaverImages("slide")); have+len(files) > screensaverMaxSlides {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": fmt.Sprintf("The slideshow holds at most %d images.", screensaverMaxSlides)})
	}
	if err := os.MkdirAll(screensaverDir(), 0755); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not store images"})
	}

	var maxPos int
	db.QueryRow(`SELECT COALESCE(MAX(position), 0) FROM screensaver_images WHERE kind = ?`, kind).Scan(&maxPos)
	var rejected []string
	for _, fh := range files {
		if fh.Size > screensaverMaxBytes {
			rejected = append(rejected, fh.Filename+" (over 10 MB)")
			continue
		}
		f, err := fh.Open()
		if err != nil {
			rejected = append(rejected, fh.Filename)
			continue
		}
		data, err := io.ReadAll(io.LimitReader(f, screensaverMaxBytes+1))
		f.Close()
		ctype := http.DetectContentType(data)
		ext, ok := imageExts[ctype]
		if err != nil || !ok || len(data) > screensaverMaxBytes {
			rejected = append(rejected, fh.Filename+" (not a JPEG, PNG or WebP image)")
			continue
		}
		if kind == "logo" {
			removeScreensaverImages(`kind = 'logo'`) // before writing, in case it is the same file
		}
		sum := sha256.Sum256(data)
		hash := hex.EncodeToString(sum[:])
		path := filepath.Join(screensaverDir(), hash+"."+ext)
		if _, err := os.Stat(path); err != nil {
			if err := os.WriteFile(path, data, 0644); err != nil {
				rejected = append(rejected, fh.Filename)
				continue
			}
		}
		maxPos++
		db.Exec(`INSERT INTO screensaver_images(kind, sha256, ext, content_type, size, position, created_at)
			VALUES(?, ?, ?, ?, ?, ?, ?)`, kind, hash, ext, ctype, len(data), maxPos, time.Now().Unix())
	}
	auditAdmin(c, "screensaver_upload", kind, strconv.Itoa(len(files)-len(rejected)))
	touchScreensaver()
	resp := map[string]interface{}{"rejected": rejected}
	if len(rejected) == len(files) {
		return c.JSON(http.StatusBadRequest, map[string]interface{}{"error": "No images were uploaded", "rejected": rejected})
	}
	return c.JSON(http.StatusOK, resp)
}

// DELETE /api/admin/screensaver/images/:id (admin)
func deleteScreensaverImage(c echo.Context) error {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Bad image id"})
	}
	if removeScreensaverImages(`id = ?`, id) == 0 {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No such image"})
	}
	// Don't leave the mirrors on a mode with nothing to show.
	cfg := loadScreensaverConfig()
	if (cfg.Mode == "slideshow" && len(listScreensaverImages("slide")) == 0) ||
		(cfg.Mode == "logo" && len(listScreensaverImages("logo")) == 0) {
		cfg.Mode = "demo"
		cfg.UpdatedAt = time.Now().Unix()
		setSetting("screensaver", cfg)
	}
	auditAdmin(c, "screensaver_delete", strconv.FormatInt(id, 10), "")
	touchScreensaver()
	return getScreensaver(c)
}

// removeScreensaverImages deletes matching rows, and files no other row uses.
func removeScreensaverImages(where string, args ...interface{}) int {
	rows, err := db.Query(`SELECT id, sha256, ext FROM screensaver_images WHERE `+where, args...)
	if err != nil {
		return 0
	}
	type rec struct {
		id        int64
		hash, ext string
	}
	var recs []rec
	for rows.Next() {
		var r rec
		if rows.Scan(&r.id, &r.hash, &r.ext) == nil {
			recs = append(recs, r)
		}
	}
	rows.Close()
	for _, r := range recs {
		db.Exec(`DELETE FROM screensaver_images WHERE id = ?`, r.id)
		var still int
		db.QueryRow(`SELECT COUNT(*) FROM screensaver_images WHERE sha256 = ?`, r.hash).Scan(&still)
		if still == 0 {
			os.Remove(filepath.Join(screensaverDir(), r.hash+"."+r.ext))
		}
	}
	return len(recs)
}

// touchScreensaver bumps updated_at so mirrors notice new or removed images.
func touchScreensaver() {
	cfg := loadScreensaverConfig()
	cfg.UpdatedAt = time.Now().Unix()
	setSetting("screensaver", cfg)
}
