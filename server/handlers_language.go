package main

import (
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"
)

type LanguageRequest struct {
	Language string `json:"language"`
}

type LanguageResponse struct {
	Language string `json:"language"`
}

func normalizeLanguage(lang string) string {
	if lang = strings.TrimSpace(lang); lang == "mi-NZ" {
		return lang
	}
	return "en-NZ"
}

func languageOf(userID string) string {
	var lang string
	if userID == "" || db.QueryRow(`SELECT language FROM users WHERE id = ?`, userID).Scan(&lang) != nil {
		return "en-NZ"
	}
	return normalizeLanguage(lang)
}

// PUT|POST /api/users/me/language — en-NZ or mi-NZ.
func saveUserLanguage(c echo.Context) error {
	var req LanguageRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	lang := normalizeLanguage(req.Language)
	if _, err := db.Exec(`UPDATE users SET language = ? WHERE id = ?`, lang, getUserIDFromToken(c)); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to save language preference"})
	}
	return c.JSON(http.StatusOK, LanguageResponse{Language: lang})
}

// GET /api/users/me/language
func getUserLanguage(c echo.Context) error {
	return c.JSON(http.StatusOK, LanguageResponse{Language: languageOf(getUserIDFromToken(c))})
}

// GET /api/users/language?user_id=|barcode= (mirror)
func getPublicUserLanguage(c echo.Context) error {
	userID := c.QueryParam("user_id")
	if userID == "" {
		if barcode := c.QueryParam("barcode"); barcode != "" {
			userID = findUserByBarcode(normalizeBarcode(barcode))
		}
	}
	return c.JSON(http.StatusOK, LanguageResponse{Language: languageOf(userID)})
}
