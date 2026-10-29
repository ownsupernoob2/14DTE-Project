package main

import (
	"bufio"
	"database/sql"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"sync"
	"time"
	_ "time/tzdata"

	"github.com/labstack/echo/v4"
)

// isValidKingsHighICS ensures the calendar URL is strictly from kingshigh.school.kiwi with an .ics file.
// Example: https://kingshigh.school.kiwi/ics/23239-SOKKEUXX7P0OKX50E27H4H6L.ics
func isValidKingsHighICS(rawURL string) bool {
	u, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return false
	}
	if u.Scheme != "https" {
		return false
	}
	if strings.ToLower(u.Host) != "kingshigh.school.kiwi" {
		return false
	}
	lowerPath := strings.ToLower(u.Path)
	if !strings.HasPrefix(lowerPath, "/ics/") || !strings.HasSuffix(lowerPath, ".ics") {
		return false
	}
	return true
}

// TimetableEvent represents a single calendar event from an ICS file.
type TimetableEvent struct {
	Summary     string `json:"summary"`
	StartTime   string `json:"startTime"`   // "09:00"
	EndTime     string `json:"endTime"`     // "10:00"
	Location    string `json:"location"`
	Description string `json:"description"`
	IsNow       bool   `json:"isNow"`  // currently in progress
	IsDone      bool   `json:"isDone"` // already finished
	Date        string `json:"date"`        // "2026-06-05"
}

// nzLocation loads the Pacific/Auckland timezone, falling back to UTC on error.
func nzLocation() *time.Location {
	loc, err := time.LoadLocation("Pacific/Auckland")
	if err != nil {
		return time.UTC
	}
	return loc
}

// currentWeekBoundaries returns the start (Monday 00:00:00) and end (Sunday 23:59:59) of the current week.
func currentWeekBoundaries(t time.Time) (time.Time, time.Time) {
	wd := t.Weekday()
	daysSinceMonday := int(wd) - 1
	if wd == time.Sunday {
		daysSinceMonday = 6
	}

	monday := t.AddDate(0, 0, -daysSinceMonday)
	startOfWeek := time.Date(monday.Year(), monday.Month(), monday.Day(), 0, 0, 0, 0, t.Location())
	endOfWeek := startOfWeek.AddDate(0, 0, 7).Add(-time.Second)

	return startOfWeek, endOfWeek
}

// parseICSTime parses an ICS DTSTART/DTEND value (with optional TZID parameter).
// Handles:
//   - DTSTART;TZID=Pacific/Auckland:20260524T090000
//   - DTSTART:20260524T090000Z  (UTC)
//   - DTSTART:20260524T090000   (local/floating – treated as NZ local)
//   - DTSTART;VALUE=DATE:20260524 (date-only)
func parseICSTime(propLine string) (time.Time, error) {
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
	const layoutDate = "20060102"

	if strings.HasSuffix(value, "Z") {
		// UTC time
		t, err := time.Parse(layout+"Z", value)
		if err != nil {
			// Try parsing date-only
			t, err = time.Parse(layoutDate+"Z", value)
			if err != nil {
				return time.Time{}, fmt.Errorf("parsing UTC time %q: %w", value, err)
			}
		}
		return t.In(nzLocation()), nil
	}

	var loc *time.Location
	if tzid != "" {
		var err error
		loc, err = time.LoadLocation(tzid)
		if err != nil {
			loc = nzLocation()
		}
	} else {
		loc = nzLocation()
	}

	t, err := time.ParseInLocation(layout, value, loc)
	if err != nil {
		// Try parsing date-only layout
		t, err = time.ParseInLocation(layoutDate, value, loc)
		if err != nil {
			return time.Time{}, fmt.Errorf("parsing local time %q: %w", value, err)
		}
	}
	return t.In(nzLocation()), nil
}

// The school's calendar is the same for every request in a lesson, and the
// mirror gives up waiting after a few seconds, so keep each feed briefly and
// fall back to the last good copy if the school's site is slow or down.
const (
	icsFresh = 10 * time.Minute
	icsStale = 24 * time.Hour
)

var (
	icsMu     sync.Mutex
	icsCache  = map[string]icsEntry{}
	icsClient = &http.Client{Timeout: 15 * time.Second}
)

type icsEntry struct {
	body string
	at   time.Time
}

func fetchICS(icsURL string) (string, error) {
	icsMu.Lock()
	cached, ok := icsCache[icsURL]
	icsMu.Unlock()
	if ok && time.Since(cached.at) < icsFresh {
		return cached.body, nil
	}
	body, err := downloadICS(icsURL)
	if err != nil {
		if ok && time.Since(cached.at) < icsStale {
			return cached.body, nil
		}
		return "", err
	}
	icsMu.Lock()
	icsCache[icsURL] = icsEntry{body: body, at: time.Now()}
	icsMu.Unlock()
	return body, nil
}

func downloadICS(icsURL string) (string, error) {
	resp, err := icsClient.Get(icsURL) //nolint:noctx
	if err != nil {
		return "", fmt.Errorf("fetching ICS: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("ICS fetch returned HTTP %d", resp.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return "", fmt.Errorf("reading ICS body: %w", err)
	}
	return string(raw), nil
}

// parseTimetable fetches an ICS file from icsURL and returns this and next week's events sorted by date and start time.
func parseTimetable(icsURL string) ([]TimetableEvent, error) {
	if !isValidKingsHighICS(icsURL) {
		return nil, fmt.Errorf("invalid calendar URL: only kingshigh.school.kiwi ICS feeds are permitted")
	}

	body, err := fetchICS(icsURL)
	if err != nil {
		return nil, err
	}
	return parseICSWeek(body, time.Now()), nil
}

// parseICSWeek returns the events in body from the start of the week containing
// now to the end of the following week. Next week is included so the mirror can
// say what's on after school on a Friday; the website and the mirror both only
// show today's lessons from it.
func parseICSWeek(body string, now time.Time) []TimetableEvent {
	now = now.In(nzLocation())
	startOfWeek, endOfWeek := currentWeekBoundaries(now)
	endOfWeek = endOfWeek.AddDate(0, 0, 7)

	var events []TimetableEvent

	// Unfold ICS lines (lines ending with CRLF + whitespace are continuations)
	lines := unfoldICSLines(body)

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
				// Only include events that fall within the current week (NZ local time)
				if startTime.After(startOfWeek) && startTime.Before(endOfWeek) {
					cur.Date = startTime.Format("2006-01-02")
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

	// Sort by date, then start time
	sort.Slice(events, func(i, j int) bool {
		if events[i].Date != events[j].Date {
			return events[i].Date < events[j].Date
		}
		return events[i].StartTime < events[j].StartTime
	})

	return events
}

// unfoldICSLines splits body into lines and unfolds continuation lines
// (RFC 5545: a line that begins with a space/tab is a continuation of the previous line).
func unfoldICSLines(body string) []string {
	scanner := bufio.NewScanner(strings.NewReader(body))
	var lines []string
	for scanner.Scan() {
		line := scanner.Text()
		line = strings.TrimRight(line, "\r\n")
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

// ─── Handlers ─────────────────────────────────────────────────────────────────

// studentIDOf is the student ID to look up in KAMAR's timetables: the one in a
// "kamar|…" ID, or the one a user linked to their account.
func studentIDOf(userID string) string {
	if id, ok := kamarStudentID(userID); ok {
		return id
	}
	var code sql.NullString
	db.QueryRow(`SELECT barcode FROM users WHERE id = ?`, userID).Scan(&code)
	return code.String
}

func icsURLOf(userID string) string {
	var u string
	db.QueryRow(`SELECT ics_url FROM users WHERE id = ?`, userID).Scan(&u)
	return strings.TrimSpace(u)
}

// getTimetable returns this week's timetable. A signed-in user gets their own;
// a mirror (with its key) may ask for any user with ?user_id=.
func getTimetable(c echo.Context) error {
	userID := ""
	if bearerToken(c) != "" {
		if err := validateRequestToken(c); err != nil {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Please sign in again."})
		}
		userID = getUserIDFromToken(c)
	} else {
		if !mirrorKeyValid(c) {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unknown mirror"})
		}
		userID = c.QueryParam("user_id")
	}
	if userID == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "user_id required"})
	}

	// The timetable KAMAR sent for the student's ID wins; their own calendar
	// link is the fallback for anyone KAMAR doesn't cover.
	var events []TimetableEvent
	if ics := kamarICS(studentIDOf(userID)); ics != "" {
		events = parseICSWeek(ics, time.Now())
	} else {
		icsURL := icsURLOf(userID)
		if icsURL == "" {
			return c.JSON(http.StatusNotFound, map[string]string{"error": "No timetable URL configured"})
		}
		var err error
		if events, err = parseTimetable(icsURL); err != nil {
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to fetch timetable: " + err.Error()})
		}
	}
	if events == nil {
		events = []TimetableEvent{}
	}

	viewMode := "today"
	for _, w := range getWidgetsForUser(userID) {
		if w.Type != "timetable" {
			continue
		}
		if dataMap, ok := w.Data.(map[string]interface{}); ok {
			if vm, ok := dataMap["viewMode"].(string); ok {
				viewMode = vm
			}
		}
	}
	return c.JSON(http.StatusOK, map[string]interface{}{"viewMode": viewMode, "periods": events})
}

// setTimetableURL saves the user's ICS calendar URL. Archived fallback: timetables
// now come from KAMAR, and this is only reached from Settings > Troubleshooting
// (docs/archive/ics-timetable-link.md).
func setTimetableURL(c echo.Context) error {
	var body struct {
		ICSURL string `json:"ics_url"`
	}
	if err := c.Bind(&body); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	url := strings.TrimSpace(body.ICSURL)
	if !isValidKingsHighICS(url) {
		return c.JSON(http.StatusBadRequest, map[string]string{
			"error": "URL must be a valid King's High School calendar link (e.g. https://kingshigh.school.kiwi/ics/23239-SOKKEUXX7P0OKX50E27H4H6L.ics)",
		})
	}
	if _, err := db.Exec(`UPDATE users SET ics_url = ? WHERE id = ?`, url, getUserIDFromToken(c)); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to save URL"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Timetable URL saved"})
}

// getMyTimetableURL returns the currently saved ICS URL for the user.
func getMyTimetableURL(c echo.Context) error {
	icsURL := icsURLOf(getUserIDFromToken(c))
	if icsURL == "" {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No timetable URL configured"})
	}
	return c.JSON(http.StatusOK, map[string]string{"ics_url": icsURL})
}

// deleteMyTimetableURL unlinks the user's timetable.
func deleteMyTimetableURL(c echo.Context) error {
	if _, err := db.Exec(`UPDATE users SET ics_url = '' WHERE id = ?`, getUserIDFromToken(c)); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Failed to unlink timetable"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Timetable unlinked"})
}
