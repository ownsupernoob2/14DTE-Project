package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNormalizeBarcodeMakesScannedAndTypedInputEqal(t *testing.T) {
	// A scanner appends a newline; a student types spaces and lowercase.
	cases := map[string]string{
		"18234\n":       "18234",
		" 18234 ":       "18234",
		"18 234":        "18234",
		"kh-18234":      "KH-18234",
		"\tkh18234\r\n": "KH18234",
	}
	for in, want := range cases {
		if got := normalizeBarcode(in); got != want {
			t.Errorf("normalizeBarcode(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestValidateBarcodeRejectsBadShapes(t *testing.T) {
	valid := []string{"1823", "18234", "KH-18234", "ABC123456789"}
	for _, code := range valid {
		if err := validateBarcode(code); err != nil {
			t.Errorf("validateBarcode(%q) rejected a valid ID: %v", code, err)
		}
	}

	invalid := []string{
		"",                                  // empty
		"123",                               // too short
		"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", // 33 chars, too long
		"-18234",                            // leading dash
		"18234/../etc",                      // path traversal attempt
		"18_234",                            // underscore not allowed
		"18234;DROP",                        // punctuation
	}
	for _, code := range invalid {
		if err := validateBarcode(code); err == nil {
			t.Errorf("validateBarcode(%q) accepted an invalid ID", code)
		}
	}
}

// A traversal-shaped barcode must never escape the data directory, both because
// validateBarcode rejects it and because the path is built from the user ID.
func TestBarcodePathStaysInDataDir(t *testing.T) {
	for _, userID := range []string{"auth0|abc123", "auth0/abc", "plain"} {
		path := getBarcodePath(userID)
		if filepath.Dir(filepath.Clean(path)) != "data" {
			t.Errorf("getBarcodePath(%q) = %q, escaped the data dir", userID, path)
		}
	}
}

func TestFindUserByBarcodeMatchesNormalizedContent(t *testing.T) {
	// findUserByBarcode reads the relative "data" dir, so run from a temp cwd.
	chdirTemp(t)
	if err := os.MkdirAll("data", 0755); err != nil {
		t.Fatal(err)
	}
	// Stored with a trailing newline, as an earlier write or manual edit might.
	if err := os.WriteFile("data/auth0_abc_barcode.txt", []byte("KH-18234\n"), 0644); err != nil {
		t.Fatal(err)
	}
	// A non-barcode file in the same dir must be ignored.
	if err := os.WriteFile("data/auth0_abc_widgets.json", []byte(`{"x":1}`), 0644); err != nil {
		t.Fatal(err)
	}

	if got := findUserByBarcode("KH-18234"); got != "auth0_abc" {
		t.Errorf("findUserByBarcode = %q, want %q", got, "auth0_abc")
	}
	// Typed lowercase resolves to the same owner after normalisation.
	if got := findUserByBarcode(normalizeBarcode("kh-18234")); got != "auth0_abc" {
		t.Errorf("lowercase lookup = %q, want %q", got, "auth0_abc")
	}
	if got := findUserByBarcode("KH-00000"); got != "" {
		t.Errorf("unknown barcode resolved to %q, want empty", got)
	}
}

func TestFindUserByBarcodeHandlesMissingDataDir(t *testing.T) {
	chdirTemp(t)
	if got := findUserByBarcode("KH-18234"); got != "" {
		t.Errorf("expected no match with no data dir, got %q", got)
	}
}

// chdirTemp runs the test from a throwaway working directory.
//
// The chdir-back cleanup is registered *after* t.TempDir(), so LIFO ordering
// releases the directory before TempDir tries to remove it — on Windows a
// process cannot delete its own working directory.
func chdirTemp(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	orig, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chdir(orig) })
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
}
