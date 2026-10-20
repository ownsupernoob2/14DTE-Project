package main

import (
	"os"
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
