package main

import (
	"encoding/json"
	"os"
	"sync"

	"github.com/labstack/echo/v4"
)

type BannerRequest struct {
	Message string `json:"message"`
}

type BannerResponse struct {
	Message string `json:"message"`
}

var (
	bannerMutex sync.RWMutex
	cachedBanner string
)

func init() {
	// Pre-load from simple cache file if exists
	data, err := os.ReadFile("data/admin_banner.json")
	if err == nil {
		var resp BannerResponse
		if json.Unmarshal(data, &resp) == nil {
			cachedBanner = resp.Message
		}
	}
}

// POST /api/admin/banner
func setAdminBanner(c echo.Context) error {
	// Simple admin token check: can use a header named X-Admin-Token or check token claims
	// Let's check environment variable ADMIN_TOKEN if set, or accept validated token.
	adminToken := os.Getenv("ADMIN_TOKEN")
	if adminToken != "" {
		reqToken := c.Request().Header.Get("X-Admin-Token")
		if reqToken != adminToken {
			return c.JSON(403, map[string]string{"error": "Forbidden: Invalid admin token"})
		}
	}

	var req BannerRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request body"})
	}

	bannerMutex.Lock()
	cachedBanner = req.Message
	bannerMutex.Unlock()

	// Persist to data directory
	resp := BannerResponse{Message: req.Message}
	data, err := json.Marshal(resp)
	if err == nil {
		_ = os.WriteFile("data/admin_banner.json", data, 0644)
	}

	return c.JSON(200, map[string]string{"message": "Banner set successfully", "banner": req.Message})
}

// GET /api/banner
func getAdminBanner(c echo.Context) error {
	bannerMutex.RLock()
	defer bannerMutex.RUnlock()
	return c.JSON(200, BannerResponse{Message: cachedBanner})
}
