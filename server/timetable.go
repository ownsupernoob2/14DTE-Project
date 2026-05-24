package main

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

// TimetableEvent represents a single calendar event from an ICS file.
type TimetableEvent struct {
	Summary     string `json:"summary"`
	StartTime   string `json:"startTime"`   // "09:00"
	EndTime     string `json:"endTime"`     // "10:00"
	Location    string `json:"location"`
	Description string `json:"description"`
	IsNow       bool   `json:"isNow"`  // currently in progress
	IsDone      bool   `json:"isDone"` // already finished
}

// nzLocation loads the Pacific/Auckland timezone, falling back to UTC on error.
func nzLocation() *time.Location {
	loc, err := time.LoadLocation("Pacific/Auckland")
	if err != nil {
		return time.UTC
	}
	return loc
}

// parseICSTime parses an ICS DTSTART/DTEND value (with optional TZID parameter).
// Handles:
//   - DTSTART;TZID=Pacific/Auckland:20260524T090000
//   - DTSTART:20260524T090000Z  (UTC)
//   - DTSTART:20260524T090000   (local/floating – treated as NZ local)
func parseICSTime(propLine string) (time.Time, error) {
	// propLine is the full property line, e.g. "DTSTART;TZID=Pacific/Auckland:20260524T090000"
	// Split at the first colon to separate key (with params) from value.
	colonIdx := strings.Index(propLine, ":")
	if colonIdx < 0 {
		return time.Time{}, fmt.Errorf("no colon in ICS property: %s", propLine)
	}
	key := propLine[:colonIdx]
	value := strings.TrimSpace(propLine[colonIdx+1:])

	// Extract TZID from the key portion if present.
	var tzid string
	for _, part := range strings.Split(key, ";") {
		if strings.HasPrefix(part, "TZID=") {
			tzid = strings.TrimPrefix(part, "TZID=")
		}
	}

	const layout = "20060102T150405"

	if strings.HasSuffix(value, "Z") {
		// UTC time
		t, err := time.Parse(layout+"Z", value)
		if err != nil {
			return time.Time{}, fmt.Errorf("parsing UTC time %q: %w", value, err)
		}
		return t.In(nzLocation()), nil
	}

	if tzid != "" {
		loc, err := time.LoadLocation(tzid)
		if err != nil {
			// Fall back to NZ local if TZID is unrecognised
			loc = nzLocation()
		}
		t, err := time.ParseInLocation(layout, value, loc)
		if err != nil {
			return time.Time{}, fmt.Errorf("parsing TZID time %q: %w", value, err)
		}
		return t.In(nzLocation()), nil
	}

	// Floating / no timezone — treat as NZ local
	t, err := time.ParseInLocation(layout, value, nzLocation())
	if err != nil {
		return time.Time{}, fmt.Errorf("parsing local time %q: %w", value, err)
	}
	return t, nil
}

// parseTimetable fetches an ICS file from icsURL and returns today's events sorted by start time.
func parseTimetable(icsURL string) ([]TimetableEvent, error) {
	resp, err := http.Get(icsURL) //nolint:noctx
	if err != nil {
		return nil, fmt.Errorf("fetching ICS: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("ICS fetch returned HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("reading ICS body: %w", err)
	}

	loc := nzLocation()
	now := time.Now().In(loc)
	todayDate := now.Format("2006-01-02")

	var events []TimetableEvent

	// Unfold ICS lines (lines ending with CRLF + whitespace are continuations)
	lines := unfoldICSLines(string(body))

	var (
		inEvent     bool
		cur         TimetableEvent
		startTime   time.Time
		endTime     time.Time
		hasStart    bool
		hasEnd      bool
	)

	for _, line := range lines {
		// Strip trailing CR
		line = strings.TrimRight(line, "\r")

		switch {
		case line == "BEGIN:VEVENT":
			inEvent = true
			cur = TimetableEvent{}
			startTime = time.Time{}
			endTime = time.Time{}
			hasStart = false
			hasEnd = false

		case line == "END:VEVENT":
			if inEvent && hasStart {
				// Only include events that fall on today (NZ time)
				if startTime.Format("2006-01-02") == todayDate {
					cur.StartTime = startTime.Format("15:04")
					if hasEnd {
						cur.EndTime = endTime.Format("15:04")
					}
					// Determine IsNow / IsDone
					if hasEnd && now.After(endTime) {
						cur.IsDone = true
					} else if hasStart && now.After(startTime) && (!hasEnd || now.Before(endTime)) {
						cur.IsNow = true
					}
					events = append(events, cur)
				}
			}
			inEvent = false

		default:
			if !inEvent {
				continue
			}
			// Parse relevant properties
			switch {
			case strings.HasPrefix(line, "SUMMARY:"):
				cur.Summary = strings.TrimPrefix(line, "SUMMARY:")
			case strings.HasPrefix(line, "LOCATION:"):
				cur.Location = strings.TrimPrefix(line, "LOCATION:")
			case strings.HasPrefix(line, "DESCRIPTION:"):
				cur.Description = strings.TrimPrefix(line, "DESCRIPTION:")
			case strings.HasPrefix(line, "DTSTART"):
				t, err := parseICSTime(line)
				if err == nil {
					startTime = t
					hasStart = true
				}
			case strings.HasPrefix(line, "DTEND"):
				t, err := parseICSTime(line)
				if err == nil {
					endTime = t
					hasEnd = true
				}
			}
		}
	}

	// Sort by start time
	sort.Slice(events, func(i, j int) bool {
		return events[i].StartTime < events[j].StartTime
	})

	return events, nil
}

// unfoldICSLines splits body into lines and unfolds continuation lines
// (RFC 5545: a line that begins with a space/tab is a continuation of the previous line).
func unfoldICSLines(body string) []string {
	scanner := bufio.NewScanner(strings.NewReader(body))
	var lines []string
	for scanner.Scan() {
		line := scanner.Text()
		if len(line) > 0 && (line[0] == ' ' || line[0] == '\t') {
			// Continuation — append to previous line (sans leading whitespace)
			if len(lines) > 0 {
				lines[len(lines)-1] += strings.TrimLeft(line, " \t")
			}
		} else {
			lines = append(lines, line)
		}
	}
	return lines
}

// ─── ICS URL helpers ──────────────────────────────────────────────────────────

func getICSURLPath(userID string) string {
	return fmt.Sprintf("data/%s_ics_url.txt", getSafeUserID(userID))
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

// getTimetable returns today's timetable events for the requesting user.
// Works with a JWT token OR a ?user_id= query param (mirrors can call without auth).
func getTimetable(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = c.QueryParam("user_id")
	}
	if userID == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "user_id required"})
	}

	path := getICSURLPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No timetable URL configured"})
	}

	icsURL := strings.TrimSpace(string(data))
	if icsURL == "" {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No timetable URL configured"})
	}

	events, err := parseTimetable(icsURL)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to fetch timetable: " + err.Error()})
	}

	return c.JSON(http.StatusOK, events)
}

// setTimetableURL saves the user's ICS calendar URL.
func setTimetableURL(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
	}

	var body struct {
		ICSURL string `json:"ics_url"`
	}
	if err := c.Bind(&body); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}

	url := strings.TrimSpace(body.ICSURL)
	if !strings.HasPrefix(url, "https://") || !strings.HasSuffix(url, ".ics") {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "URL must start with https:// and end with .ics"})
	}

	path := getICSURLPath(userID)
	if err := os.WriteFile(path, []byte(url), 0644); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to save URL"})
	}

	return c.JSON(http.StatusOK, map[string]string{"message": "Timetable URL saved"})
}

// getMyTimetableURL returns the currently saved ICS URL for the user.
func getMyTimetableURL(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
	}

	path := getICSURLPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No timetable URL configured"})
	}

	icsURL := strings.TrimSpace(string(data))
	return c.JSON(http.StatusOK, map[string]string{"ics_url": icsURL})
}
