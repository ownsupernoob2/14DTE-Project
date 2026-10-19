package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/labstack/echo/v4"
)

func TestLanguagePersistence(t *testing.T) {
	tempDir := t.TempDir()
	origDir, _ := os.Getwd()
	_ = os.Chdir(tempDir)
	defer func() { _ = os.Chdir(origDir) }()

	e := echo.New()

	// Test public endpoint when no language exists
	req := httptest.NewRequest(http.MethodGet, "/api/users/language?user_id=auth0_test123", nil)
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)

	if err := getPublicUserLanguage(c); err != nil {
		t.Fatalf("getPublicUserLanguage failed: %v", err)
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp LanguageResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp.Language != "en-NZ" {
		t.Errorf("expected default en-NZ, got %q", resp.Language)
	}

	// Save mi-NZ language
	_ = os.MkdirAll("data", 0755)
	path := getLanguagePath("auth0_test123")
	if err := os.WriteFile(path, []byte("mi-NZ"), 0644); err != nil {
		t.Fatalf("failed to write language file: %v", err)
	}

	// Test public endpoint after saving
	rec2 := httptest.NewRecorder()
	c2 := e.NewContext(req, rec2)
	if err := getPublicUserLanguage(c2); err != nil {
		t.Fatalf("getPublicUserLanguage failed: %v", err)
	}

	var resp2 LanguageResponse
	_ = json.Unmarshal(rec2.Body.Bytes(), &resp2)
	if resp2.Language != "mi-NZ" {
		t.Errorf("expected mi-NZ, got %q", resp2.Language)
	}
}

func TestFindUserByBarcodeLanguageQuery(t *testing.T) {
	tempDir := t.TempDir()
	origDir, _ := os.Getwd()
	_ = os.Chdir(tempDir)
	defer func() { _ = os.Chdir(origDir) }()

	_ = os.MkdirAll("data", 0755)
	_ = os.WriteFile("data/auth0_barcodetest_barcode.txt", []byte("KH-9999\n"), 0644)
	_ = os.WriteFile("data/auth0_barcodetest_language.txt", []byte("mi-NZ"), 0644)

	e := echo.New()
	req := httptest.NewRequest(http.MethodGet, "/api/users/language?barcode=KH-9999", nil)
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)

	if err := getPublicUserLanguage(c); err != nil {
		t.Fatalf("getPublicUserLanguage failed: %v", err)
	}

	var resp LanguageResponse
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp.Language != "mi-NZ" {
		t.Errorf("expected mi-NZ from barcode lookup, got %q", resp.Language)
	}
}
