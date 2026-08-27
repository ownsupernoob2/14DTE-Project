package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/labstack/echo/v4"
)

// Student ID barcodes are short alphanumeric codes. Anything outside this shape
// is either a misread scan or someone probing the public verify endpoint.
const (
	barcodeMinLen = 4
	barcodeMaxLen = 32
)

var barcodeShapeRe = regexp.MustCompile(`^[A-Z0-9][A-Z0-9-]*$`)

// normalizeBarcode makes typed and scanned input compare equal: scanners often
// emit trailing newlines and students type their ID with spaces or lowercase.
func normalizeBarcode(raw string) string {
	var sb strings.Builder
	for _, r := range raw {
		switch {
		case r >= 'a' && r <= 'z':
			sb.WriteRune(r - 32)
		case r == ' ' || r == '\t' || r == '\r' || r == '\n':
			// drop
		default:
			sb.WriteRune(r)
		}
	}
	return sb.String()
}

func validateBarcode(code string) error {
	if len(code) < barcodeMinLen {
		return fmt.Errorf("student ID must be at least %d characters", barcodeMinLen)
	}
	if len(code) > barcodeMaxLen {
		return fmt.Errorf("student ID must be at most %d characters", barcodeMaxLen)
	}
	if !barcodeShapeRe.MatchString(code) {
		return fmt.Errorf("student ID may only contain letters, numbers and dashes")
	}
	return nil
}

func getBarcodePath(userID string) string {
	return fmt.Sprintf("data/%s_barcode.txt", getSafeUserID(userID))
}

// findUserByBarcode returns the user ID that owns code, or "" if unclaimed.
func findUserByBarcode(code string) string {
	entries, err := os.ReadDir("data")
	if err != nil {
		if !os.IsNotExist(err) {
			log.Printf("barcode lookup: cannot read data dir: %v", err)
		}
		return ""
	}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || !strings.HasSuffix(name, "_barcode.txt") {
			continue
		}
		content, err := os.ReadFile(filepath.Join("data", name))
		if err != nil {
			continue
		}
		if normalizeBarcode(string(content)) == code {
			return strings.TrimSuffix(name, "_barcode.txt")
		}
	}
	return ""
}

// saveBarcode links a student ID to the logged-in user. Accepts both a scanned
// barcode and a hand-typed ID — they are the same value by the time we get here.
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

	code := normalizeBarcode(body.Barcode)
	if err := validateBarcode(code); err != nil {
		return c.JSON(400, map[string]string{"error": err.Error()})
	}

	// A barcode identifies exactly one student at the mirror, so refuse to let
	// two accounts claim the same code.
	if owner := findUserByBarcode(code); owner != "" && owner != getSafeUserID(userID) {
		return c.JSON(409, map[string]string{
			"error": "That student ID is already linked to another account.",
		})
	}

	if err := os.MkdirAll("data", 0755); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save student ID"})
	}
	if err := os.WriteFile(getBarcodePath(userID), []byte(code), 0644); err != nil {
		log.Printf("barcode save failed for %s: %v", getSafeUserID(userID), err)
		return c.JSON(500, map[string]string{"error": "Failed to save student ID"})
	}

	return c.JSON(200, map[string]string{
		"message": "Student ID linked successfully",
		"barcode": code,
	})
}

// getBarcode returns the logged-in user's linked student ID, or "" if none.
func getBarcode(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Unauthorized"})
	}

	data, err := os.ReadFile(getBarcodePath(userID))
	if err != nil {
		if os.IsNotExist(err) {
			return c.JSON(200, map[string]string{"barcode": ""})
		}
		return c.JSON(500, map[string]string{"error": "Failed to read student ID"})
	}

	return c.JSON(200, map[string]string{"barcode": normalizeBarcode(string(data))})
}

// deleteBarcode unlinks the logged-in user's student ID.
func deleteBarcode(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Unauthorized"})
	}

	if err := os.Remove(getBarcodePath(userID)); err != nil && !os.IsNotExist(err) {
		log.Printf("barcode delete failed for %s: %v", getSafeUserID(userID), err)
		return c.JSON(500, map[string]string{"error": "Failed to unlink student ID"})
	}

	return c.JSON(200, map[string]string{"message": "Student ID unlinked"})
}

// verifyBarcode is the mirror-facing counterpart to verifyFace: it resolves a
// scanned barcode to a user and returns the same payload, so a successful scan
// drives the mirror down the identical "recognised" path.
//
// This route is unauthenticated (the mirror has no token), so it is rate limited
// in main.go to make guessing student IDs impractical.
func verifyBarcode(c echo.Context) error {
	var req struct {
		Barcode string `json:"barcode"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	code := normalizeBarcode(req.Barcode)
	if err := validateBarcode(code); err != nil {
		return c.JSON(400, map[string]string{"error": err.Error()})
	}

	matchedUserID := findUserByBarcode(code)
	if matchedUserID == "" {
		return c.JSON(404, map[string]string{"error": "Student ID not recognised"})
	}

	log.Printf("Barcode sign-in: %s", matchedUserID)

	return c.JSON(200, map[string]interface{}{
		"user_id":     matchedUserID,
		"widgets":     getWidgetsForUser(matchedUserID),
		"config":      getDashboardConfigForUser(matchedUserID),
		"auth_method": "barcode",
	})
}
