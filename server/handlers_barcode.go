package main

import (
	"database/sql"
	"fmt"
	"log"
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

// findUserByBarcode returns the user ID that owns code, or "" if unclaimed.
func findUserByBarcode(code string) string {
	var id string
	if err := db.QueryRow(`SELECT id FROM users WHERE barcode = ?`, code).Scan(&id); err != nil {
		return ""
	}
	return id
}

// PUT /api/users/me/barcode — link a scanned or typed student ID.
func saveBarcode(c echo.Context) error {
	userID := getUserIDFromToken(c)
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
	// A barcode identifies exactly one student at the mirror.
	if owner := findUserByBarcode(code); owner != "" && owner != userID {
		return c.JSON(409, map[string]string{"error": "That student ID is already linked to another account."})
	}
	if _, err := db.Exec(`UPDATE users SET barcode = ? WHERE id = ?`, code, userID); err != nil {
		log.Printf("barcode save failed for %s: %v", userID, err)
		return c.JSON(500, map[string]string{"error": "Failed to save student ID"})
	}
	return c.JSON(200, map[string]string{"message": "Student ID linked successfully", "barcode": code})
}

// GET /api/users/me/barcode
func getBarcode(c echo.Context) error {
	var code sql.NullString
	db.QueryRow(`SELECT barcode FROM users WHERE id = ?`, getUserIDFromToken(c)).Scan(&code)
	return c.JSON(200, map[string]string{"barcode": code.String})
}

// DELETE /api/users/me/barcode
func deleteBarcode(c echo.Context) error {
	if _, err := db.Exec(`UPDATE users SET barcode = NULL WHERE id = ?`, getUserIDFromToken(c)); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to unlink student ID"})
	}
	return c.JSON(200, map[string]string{"message": "Student ID unlinked"})
}

// POST /api/verify-barcode (mirror) — resolve a scanned student ID to a user.
// Rate limited in main.go so IDs cannot be guessed by brute force.
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
	matched := findUserByBarcode(code)
	if matched == "" {
		// No account, but KAMAR knows this student: show their timetable.
		if hasKamarTimetable(code) {
			log.Printf("Barcode sign-in: KAMAR student without an account")
			return c.JSON(200, kamarStudentPayload(code))
		}
		return c.JSON(404, map[string]string{"error": "Student ID not recognised"})
	}
	log.Printf("Barcode sign-in: %s", matched)
	return c.JSON(200, mirrorUserPayload(matched, "barcode"))
}

// kamarStudentPayload signs in a student who has no account: the default
// dashboard and their KAMAR timetable, nothing personal.
func kamarStudentPayload(code string) map[string]interface{} {
	return map[string]interface{}{
		"user_id":     kamarUserPrefix + code,
		"user_name":   "",
		"language":    "en-NZ",
		"widgets":     []Widget{},
		"config":      defaultDashboardConfig(),
		"auth_method": "barcode",
	}
}
