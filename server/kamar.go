package main

// kamar.go — the KAMAR Directory Services listener.
//
// The school's KAMAR posts student timetables here (overnight, and again when
// one changes). We never call KAMAR: it pushes, we store each timetable as an
// ICS calendar keyed by the student's ID number, and the mirror reads it back
// through /api/timetable when that student scans their card.
//
// Protocol: https://directoryservices.kamar.nz/?listening-service
// Setup for the school: kamar-directory-services-setup.md

import (
	"bytes"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

// KAMAR re-sends every timetable each night, so a row that hasn't been
// refreshed in this long belongs to a student who has left (or the school
// turned the service off). Matches the retention promised in the setup guide.
const kamarRetention = 30 * 24 * time.Hour

// A student who has never made an account signs in at the mirror as
// "kamar|<student ID>": enough to show their timetable, nothing else.
const kamarUserPrefix = "kamar|"

func kamarStudentID(userID string) (string, bool) {
	if !strings.HasPrefix(userID, kamarUserPrefix) {
		return "", false
	}
	return strings.TrimPrefix(userID, kamarUserPrefix), true
}

// kamarICS returns the timetable KAMAR sent for studentID, or "" if none.
func kamarICS(studentID string) string {
	if studentID == "" {
		return ""
	}
	var ics string
	db.QueryRow(`SELECT ics FROM kamar_timetables WHERE student_id = ?`, studentID).Scan(&ics)
	return ics
}

func hasKamarTimetable(studentID string) bool {
	var one int
	return db.QueryRow(`SELECT 1 FROM kamar_timetables WHERE student_id = ?`, studentID).Scan(&one) == nil
}

// kamarAuthorised checks the Basic auth KAMAR sends against KAMAR_DS_USERNAME
// and KAMAR_DS_PASSWORD. With either unset, nothing is accepted.
func kamarAuthorised(c echo.Context) bool {
	wantUser, wantPass := os.Getenv("KAMAR_DS_USERNAME"), os.Getenv("KAMAR_DS_PASSWORD")
	if wantUser == "" || wantPass == "" {
		return false
	}
	user, pass, ok := c.Request().BasicAuth()
	if !ok {
		return false
	}
	userOK := subtle.ConstantTimeCompare([]byte(user), []byte(wantUser)) == 1
	passOK := subtle.ConstantTimeCompare([]byte(pass), []byte(wantPass)) == 1
	return userOK && passOK
}

// kamarID accepts KAMAR's ID as either a JSON number or a string.
type kamarID string

func (k *kamarID) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err == nil {
		*k = kamarID(s)
		return nil
	}
	var n json.Number
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	if err := dec.Decode(&n); err != nil {
		return err
	}
	*k = kamarID(n.String())
	return nil
}

type kamarMessage struct {
	Data struct {
		Sync       string `json:"sync"`
		Timetables struct {
			Data []struct {
				// KAMAR's docs say "id"; the real messages use "student".
				ID        kamarID `json:"id"`
				Student   kamarID `json:"student"`
				Grid      string  `json:"grid"`
				Timetable string  `json:"timetable"`
			} `json:"data"`
		} `json:"timetables"`
	} `json:"SMSDirectoryData"`
}

func kamarReply(c echo.Context, status int, body map[string]interface{}) error {
	c.Response().Header().Set("Server", "Smart Mirror/1.0")
	return c.JSON(status, map[string]interface{}{"SMSDirectoryData": body})
}

func kamarOK(c echo.Context) error {
	return kamarReply(c, http.StatusOK, map[string]interface{}{"error": 0, "result": "OK"})
}

// kamarCheckResponse is what we ask the school's KAMAR for: student
// timetables as ICS, and nothing else. Changing these options disables the
// service at the school until they accept the change.
func kamarCheckResponse() map[string]interface{} {
	return map[string]interface{}{
		"error":   0,
		"result":  "OK",
		"service": "Smart Mirror",
		"version": 1.0,
		"status":  "Ready",
		"infourl": "https://smartmirror.me/privacy",
		"privacystatement": "Stores each student's timetable only, keyed by their student ID, on a server in New Zealand.|" +
			"Used only to show a student their own timetable on the Smart Mirror after they scan their ID card.|" +
			"Student records KAMAR sends with it (ID number only) are discarded unread, never stored.|" +
			"Deleted 30 days after KAMAR stops sending it (the student leaves or the service is turned off).",
		"countryDataStored": "New Zealand",
		// Every option KAMAR defines is listed, false for the ones we don't
		// want, the way its own example and working listeners do: its screen
		// kept the data boxes locked when the unwanted ones were left out.
		"options": map[string]interface{}{
			"ics": true,
			"students": map[string]interface{}{
				// Details are on only because KAMAR wants them alongside
				// timetables: the shortest field list, just the school's own ID
				// number, and kamarListener drops those records unread.
				"details":         true,
				"minLevel":        1, // every year level
				"maxLevel":        13,
				"photos":          false,
				"groups":          false,
				"awards":          false,
				"timetables":      true,
				"attendance":      false,
				"assessments":     false,
				"pastoral":        false,
				"recognitions":    false,
				"classefforts":    false,
				"learningsupport": false,
				"fields": map[string]interface{}{
					"required": "uniqueid",
					"optional": "",
				},
			},
			"staff": map[string]interface{}{
				"details":    false,
				"photos":     false,
				"timetables": false,
			},
			"common": map[string]interface{}{
				"subjects": false,
				"notices":  false,
				"calendar": false,
				"bookings": false,
			},
		},
	}
}

// POST /api/kamar — KAMAR Directory Services posts here with Basic auth.
func kamarListener(c echo.Context) error {
	// KAMAR deliberately tries wrong passwords to make sure we refuse them.
	if !kamarAuthorised(c) {
		log.Printf("[KAMAR] Refused a post with a wrong or missing login (KAMAR does this on purpose during a check)")
		return kamarReply(c, http.StatusForbidden, map[string]interface{}{"error": 403, "result": "Authentication Failed"})
	}
	raw, err := io.ReadAll(c.Request().Body)
	if err != nil {
		return kamarReply(c, http.StatusBadRequest, map[string]interface{}{"error": 400, "result": "Could not read the post"})
	}
	if bytes.HasPrefix(bytes.TrimSpace(raw), []byte("<")) {
		log.Printf("[KAMAR] Got XML. In KAMAR, set this service's Format to JSON.")
		return kamarReply(c, http.StatusBadRequest, map[string]interface{}{"error": 400, "result": "Expected JSON, got XML. Set the service Format to JSON."})
	}
	var msg kamarMessage
	if err := json.Unmarshal(raw, &msg); err != nil {
		log.Printf("[KAMAR] Unreadable post: %v", err)
		return kamarReply(c, http.StatusBadRequest, map[string]interface{}{"error": 400, "result": "Expected JSON"})
	}

	switch msg.Data.Sync {
	case "check":
		log.Printf("[KAMAR] Check from the school's KAMAR")
		return kamarReply(c, http.StatusOK, kamarCheckResponse())

	case "studenttimetables":
		stats, err := saveKamarTimetables(msg)
		if err != nil {
			log.Printf("[KAMAR] Saving timetables failed: %v", err)
			// KAMAR resends after a delay, so a failure here isn't lost.
			return kamarReply(c, http.StatusInternalServerError, map[string]interface{}{"error": 500, "result": "Could not save timetables"})
		}
		log.Printf("[KAMAR] Timetables message: %d entries, %d saved, %d with an unusable student ID, %d not a calendar",
			stats.received, stats.saved, stats.badID, stats.notICS)
		if stats.saved == 0 {
			// Say what the message looked like (names and sizes only, never the
			// values) so a format we don't expect can be seen from the log.
			log.Printf("[KAMAR] Nothing saved. Message shape: %s", kamarShape(raw))
		}
		return kamarOK(c)

	default:
		// Student records ("full"/"part") come with the details KAMAR needs us
		// to ask for, and are never stored. Accept and drop them, since an
		// error makes KAMAR retry and eventually disable the service.
		log.Printf("[KAMAR] Ignored %q message", msg.Data.Sync)
		return kamarOK(c)
	}
}

type kamarSaveStats struct{ received, saved, badID, notICS int }

func saveKamarTimetables(msg kamarMessage) (kamarSaveStats, error) {
	var stats kamarSaveStats
	tx, err := db.Begin()
	if err != nil {
		return stats, err
	}
	defer tx.Rollback()

	now := time.Now()
	for _, t := range msg.Data.Timetables.Data {
		stats.received++
		raw := t.Student
		if raw == "" {
			raw = t.ID
		}
		id := normalizeBarcode(string(raw))
		if validateBarcode(id) != nil {
			stats.badID++
			continue
		}
		if !strings.Contains(t.Timetable, "BEGIN:VCALENDAR") {
			stats.notICS++
			continue
		}
		if _, err := tx.Exec(`INSERT INTO kamar_timetables(student_id, ics, grid, updated_at) VALUES(?, ?, ?, ?)
			ON CONFLICT(student_id) DO UPDATE SET ics = excluded.ics, grid = excluded.grid, updated_at = excluded.updated_at`,
			id, t.Timetable, t.Grid, now.Unix()); err != nil {
			return stats, err
		}
		stats.saved++
	}
	if _, err := tx.Exec(`DELETE FROM kamar_timetables WHERE updated_at < ?`, now.Add(-kamarRetention).Unix()); err != nil {
		return stats, err
	}
	return stats, tx.Commit()
}

// kamarShape describes a timetables post for the log: which fields it has and
// how big each is, for the message itself and its first entry. No values.
func kamarShape(raw []byte) string {
	describe := func(m map[string]json.RawMessage) string {
		keys := make([]string, 0, len(m))
		for k := range m {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		parts := make([]string, 0, len(keys))
		for _, k := range keys {
			kind := "other"
			if v := bytes.TrimSpace(m[k]); len(v) > 0 {
				switch {
				case v[0] == '"':
					kind = "text"
				case v[0] == '[':
					kind = "list"
				case v[0] == '{':
					kind = "object"
				case v[0] == '-' || (v[0] >= '0' && v[0] <= '9'):
					kind = "number"
				case string(v) == "null":
					kind = "null"
				}
			}
			parts = append(parts, fmt.Sprintf("%s=%s(%d bytes)", k, kind, len(m[k])))
		}
		return strings.Join(parts, " ")
	}
	var top struct {
		D map[string]json.RawMessage `json:"SMSDirectoryData"`
	}
	if json.Unmarshal(raw, &top) != nil {
		return "unreadable"
	}
	out := "message{" + describe(top.D) + "}"
	var tt struct {
		Data []map[string]json.RawMessage `json:"data"`
	}
	var ttFields map[string]json.RawMessage
	if json.Unmarshal(top.D["timetables"], &ttFields) == nil {
		out += " timetables{" + describe(ttFields) + "}"
		if json.Unmarshal(top.D["timetables"], &tt) == nil && len(tt.Data) > 0 {
			out += " firstEntry{" + describe(tt.Data[0]) + "}"
		}
	}
	return out
}
