package main

import (
	"testing"
)

func TestIsValidKingsHighICS(t *testing.T) {
	validURLs := []string{
		"https://kingshigh.school.kiwi/ics/23239-SOKKEUXX7P0OKX50E27H4H6L.ics",
		"https://kingshigh.school.kiwi/ics/student123.ics",
		"https://KINGSHIGH.SCHOOL.KIWI/ics/test.ICS",
	}

	for _, u := range validURLs {
		if !isValidKingsHighICS(u) {
			t.Errorf("expected valid URL for %q, got false", u)
		}
	}

	invalidURLs := []string{
		"",
		"http://kingshigh.school.kiwi/ics/test.ics",       // not https
		"https://google.com/calendar.ics",                 // wrong domain
		"https://kingshigh.school.nz/ics/test.ics",        // wrong domain (.nz instead of .school.kiwi)
		"https://malicious.com/kingshigh.school.kiwi.ics", // wrong host
		"https://kingshigh.school.kiwi/other/test.ics",    // wrong path (not /ics/)
		"https://kingshigh.school.kiwi/ics/test.txt",      // not .ics
	}

	for _, u := range invalidURLs {
		if isValidKingsHighICS(u) {
			t.Errorf("expected invalid URL for %q, got true", u)
		}
	}
}
