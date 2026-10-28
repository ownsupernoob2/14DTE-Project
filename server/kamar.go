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
	"io"
	"log"
	"net/http"
	"os"
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
				ID        kamarID `json:"id"`
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
		"options": map[string]interface{}{
			"ics": true,
			"students": map[string]interface{}{
				// KAMAR's Students options stayed greyed out while details were
				// off. We ask for details with the shortest field list, just the
				// school's own ID number, and drop those records in kamarListener.
				"details":  true,
				"minLevel": 1, // every year level, as in KAMAR's own example
				"maxLevel": 13,
				"fields": map[string]interface{}{
					"required": "uniqueid",
					"optional": "",
				},
				"timetables": true,
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
		saved, err := saveKamarTimetables(msg)
		if err != nil {
			log.Printf("[KAMAR] Saving timetables failed: %v", err)
			// KAMAR resends after a delay, so a failure here isn't lost.
			return kamarReply(c, http.StatusInternalServerError, map[string]interface{}{"error": 500, "result": "Could not save timetables"})
		}
		log.Printf("[KAMAR] Saved %d student timetables", saved)
		return kamarOK(c)

	default:
		// Student records ("full"/"part") come with the details KAMAR needs us
		// to ask for, and are never stored. Accept and drop them, since an
		// error makes KAMAR retry and eventually disable the service.
		log.Printf("[KAMAR] Ignored %q message", msg.Data.Sync)
		return kamarOK(c)
	}
}

func saveKamarTimetables(msg kamarMessage) (int, error) {
	tx, err := db.Begin()
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()

	now := time.Now()
	saved := 0
	for _, t := range msg.Data.Timetables.Data {
		id := normalizeBarcode(string(t.ID))
		if validateBarcode(id) != nil || !strings.Contains(t.Timetable, "BEGIN:VCALENDAR") {
			continue
		}
		if _, err := tx.Exec(`INSERT INTO kamar_timetables(student_id, ics, grid, updated_at) VALUES(?, ?, ?, ?)
			ON CONFLICT(student_id) DO UPDATE SET ics = excluded.ics, grid = excluded.grid, updated_at = excluded.updated_at`,
			id, t.Timetable, t.Grid, now.Unix()); err != nil {
			return 0, err
		}
		saved++
	}
	if _, err := tx.Exec(`DELETE FROM kamar_timetables WHERE updated_at < ?`, now.Add(-kamarRetention).Unix()); err != nil {
		return 0, err
	}
	return saved, tx.Commit()
}
