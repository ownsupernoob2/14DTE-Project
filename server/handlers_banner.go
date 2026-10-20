package main

import (
	"crypto/subtle"
	"net/http"
	"os"

	"github.com/labstack/echo/v4"
)

type BannerRequest struct {
	Message string `json:"message"`
}

type BannerResponse struct {
	Message string `json:"message"`
}

// RequireAdminOrUpdater lets an admin through, or the Windows updater script
// (run-and-update.ps1), which posts "server updating" notices with ADMIN_TOKEN.
func RequireAdminOrUpdater() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if want := os.Getenv("ADMIN_TOKEN"); want != "" {
				got := c.Request().Header.Get("X-Admin-Token")
				if subtle.ConstantTimeCompare([]byte(got), []byte(want)) == 1 {
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

// POST /api/admin/banner
func setAdminBanner(c echo.Context) error {
	var req BannerRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	if len(req.Message) > 500 {
		req.Message = req.Message[:500]
	}
	if err := setSetting("banner", BannerResponse{Message: req.Message}); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save the banner"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Banner set successfully", "banner": req.Message})
}

// GET /api/banner
func getAdminBanner(c echo.Context) error {
	var b BannerResponse
	getSetting("banner", &b)
	return c.JSON(http.StatusOK, b)
}
