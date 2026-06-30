// ARCHIVED: Barcode/OCR feature has been removed. Routes were unregistered from main.go.
// This file is kept for history. Functions here are no longer called.
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/labstack/echo/v4"
)

func getBarcodePath(userID string) string {
	return fmt.Sprintf("data/%s_barcode.txt", getSafeUserID(userID))
}

// saveBarcode saves the barcode for the currently logged in user
func saveBarcode(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Unauthorized"})
	}

	var body struct {
		Barcode string `json:"barcode"`
	}
	if err := c.Bind(&body); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	barcode := strings.TrimSpace(body.Barcode)
	if barcode == "" {
		return c.JSON(400, map[string]string{"error": "Barcode cannot be empty"})
	}

	path := getBarcodePath(userID)
	if err := os.WriteFile(path, []byte(barcode), 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save barcode"})
	}

	return c.JSON(200, map[string]string{"message": "Barcode saved successfully", "barcode": barcode})
}

// getBarcode retrieves the barcode for the currently logged in user
func getBarcode(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Unauthorized"})
	}

	path := getBarcodePath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return c.JSON(200, map[string]string{"barcode": ""})
		}
		return c.JSON(500, map[string]string{"error": "Failed to read barcode"})
	}

	return c.JSON(200, map[string]string{"barcode": strings.TrimSpace(string(data))})
}

// verifyBarcode searches for a user with the matching barcode and returns their widget layout
func verifyBarcode(c echo.Context) error {
	var req struct {
		Barcode string `json:"barcode"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	barcode := strings.TrimSpace(req.Barcode)
	if barcode == "" {
		return c.JSON(400, map[string]string{"error": "Barcode required"})
	}

	files, err := os.ReadDir("data")
	if err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to read data directory"})
	}

	var matchedUserID string
	for _, file := range files {
		if strings.HasSuffix(file.Name(), "_barcode.txt") {
			content, err := os.ReadFile("data/" + file.Name())
			if err == nil && strings.TrimSpace(string(content)) == barcode {
				matchedUserID = strings.TrimSuffix(file.Name(), "_barcode.txt")
				break
			}
		}
	}

	if matchedUserID == "" {
		return c.JSON(404, map[string]string{"error": "Barcode not recognized"})
	}

	return c.JSON(200, map[string]interface{}{
		"user_id": matchedUserID,
		"widgets": getWidgetsForUser(matchedUserID),
	})
}
