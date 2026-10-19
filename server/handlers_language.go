package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/labstack/echo/v4"
)

type LanguageRequest struct {
	Language string `json:"language"`
}

type LanguageResponse struct {
	Language string `json:"language"`
}

func getLanguagePath(userID string) string {
	return fmt.Sprintf("data/%s_language.txt", getSafeUserID(userID))
}

// saveUserLanguage persists the user's chosen language (en-NZ or mi-NZ)
func saveUserLanguage(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
	}

	var req LanguageRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}

	lang := strings.TrimSpace(req.Language)
	if lang != "mi-NZ" && lang != "en-NZ" {
		lang = "en-NZ"
	}

	if err := os.MkdirAll("data", 0755); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to create data directory"})
	}

	path := getLanguagePath(userID)
	if err := os.WriteFile(path, []byte(lang), 0644); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to save language preference"})
	}

	return c.JSON(http.StatusOK, LanguageResponse{Language: lang})
}

// getUserLanguage retrieves the user's stored language preference
func getUserLanguage(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
	}

	path := getLanguagePath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return c.JSON(http.StatusOK, LanguageResponse{Language: "en-NZ"})
	}

	lang := strings.TrimSpace(string(data))
	if lang == "" {
		lang = "en-NZ"
	}

	return c.JSON(http.StatusOK, LanguageResponse{Language: lang})
}

// getPublicUserLanguage allows the mirror display to query language by user_id or barcode
func getPublicUserLanguage(c echo.Context) error {
	userID := c.QueryParam("user_id")
	barcode := c.QueryParam("barcode")

	if userID == "" && barcode != "" {
		userID = findUserByBarcode(barcode)
	}

	if userID == "" {
		return c.JSON(http.StatusOK, LanguageResponse{Language: "en-NZ"})
	}

	path := getLanguagePath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return c.JSON(http.StatusOK, LanguageResponse{Language: "en-NZ"})
	}

	lang := strings.TrimSpace(string(data))
	if lang == "" {
		lang = "en-NZ"
	}

	return c.JSON(http.StatusOK, LanguageResponse{Language: lang})
}
