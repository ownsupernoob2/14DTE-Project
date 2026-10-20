package main

// handlers_banner.go — the mirror-wide notice. An admin posts one message that
// every mirror shows at the top of the screen, for guests and signed-in
// students alike (and the website's dashboard shows it too). Messages for a
// single student — "your face scan was removed" — are user_messages instead.

import (
	"crypto/subtle"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

const bannerMaxLen = 280

// BannerResponse is what mirrors and the website read from GET /api/banner.
type BannerResponse struct {
	Message   string `json:"message"`
	Level     string `json:"level"`      // notice | warning | urgent
	ExpiresAt int64  `json:"expires_at"` // unix seconds, 0 = until cleared
	UpdatedAt int64  `json:"updated_at"`
	UpdatedBy string `json:"updated_by,omitempty"`
}

// RequireAdminOrUpdater lets an admin through, or the Windows updater script
// (run-and-update.ps1), which posts "server updating" notices with ADMIN_TOKEN.
func RequireAdminOrUpdater() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if want := os.Getenv("ADMIN_TOKEN"); want != "" {
				got := c.Request().Header.Get("X-Admin-Token")
				if subtle.ConstantTimeCompare([]byte(got), []byte(want)) == 1 {
					c.Set("updater", true)
					return next(c)
				}
			}
			if err := validateRequestToken(c); err != nil {
				return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Please sign in again."})
			}
			if !isAdmin(c) {
				return c.JSON(http.StatusForbidden, map[string]string{"error": "This area is for administrators only."})
			}
			return next(c)
		}
	}
}

func currentBanner() BannerResponse {
	var b BannerResponse
	getSetting("banner", &b)
	if b.Level == "" {
		b.Level = "notice"
	}
	if b.ExpiresAt > 0 && time.Now().Unix() >= b.ExpiresAt {
		return BannerResponse{Level: "notice"} // expired: nothing to show
	}
	return b
}

// POST /api/admin/banner — {message, level, expires_in_minutes}. An empty
// message clears it.
func setAdminBanner(c echo.Context) error {
	var req struct {
		Message          string `json:"message"`
		Level            string `json:"level"`
		ExpiresInMinutes int    `json:"expires_in_minutes"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	msg := strings.Join(strings.Fields(req.Message), " ") // one line on the mirror
	if len([]rune(msg)) > bannerMaxLen {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Keep the notice under 280 characters so it fits on the mirror."})
	}
	b := BannerResponse{
		Message:   msg,
		Level:     oneOf(req.Level, "notice", "warning", "urgent"),
		UpdatedAt: time.Now().Unix(),
	}
	if req.ExpiresInMinutes > 0 && msg != "" {
		b.ExpiresAt = b.UpdatedAt + int64(req.ExpiresInMinutes)*60
	}
	if updater, _ := c.Get("updater").(bool); updater {
		b.UpdatedBy = "server updater"
	} else {
		b.UpdatedBy = adminEmailOf(c)
		action := "banner_set"
		if msg == "" {
			action = "banner_clear"
		}
		auditAdmin(c, action, b.Level, msg)
	}
	if err := setSetting("banner", b); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save the notice"})
	}
	return c.JSON(http.StatusOK, currentBanner())
}

// GET /api/banner
func getAdminBanner(c echo.Context) error {
	return c.JSON(http.StatusOK, currentBanner())
}
