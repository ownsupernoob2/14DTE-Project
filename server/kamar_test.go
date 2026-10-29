package main

import (
	"bytes"
	"fmt"
	"log"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/labstack/echo/v4"
)

func setKamarLogin(t *testing.T) {
	t.Helper()
	os.Setenv("KAMAR_DS_USERNAME", "kamar-user")
	os.Setenv("KAMAR_DS_PASSWORD", "kamar-pass")
	t.Cleanup(func() {
		os.Unsetenv("KAMAR_DS_USERNAME")
		os.Unsetenv("KAMAR_DS_PASSWORD")
	})
}

// postKamar sends body to /api/kamar through the real router, as KAMAR would.
func postKamar(t *testing.T, user, pass, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest("POST", "/api/kamar", strings.NewReader(body))
	req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
	if user != "" || pass != "" {
		req.SetBasicAuth(user, pass)
	}
	rec := httptest.NewRecorder()
	newServer().ServeHTTP(rec, req)
	return rec
}

// lessonToday is a one-lesson ICS calendar for 10:00–11:00 today, NZ time.
func lessonToday(subject string) string {
	day := time.Now().In(nzLocation()).Format("20060102")
	return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n" +
		"DTSTART;TZID=Pacific/Auckland:" + day + "T100000\r\n" +
		"DTEND;TZID=Pacific/Auckland:" + day + "T110000\r\n" +
		"SUMMARY:" + subject + "\r\nLOCATION:B12\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
}

func timetablesMessage(entries ...string) string {
	return `{"SMSDirectoryData":{"datetime":20261027020000,"sync":"studenttimetables","sms":"KAMAR",
		"schools":[{"index":1,"moeCode":"0123","name":"Kings High"}],
		"timetables":{"count":` + fmt.Sprint(len(entries)) + `,"data":[` + strings.Join(entries, ",") + `]}}}`
}

// realTimetableEntry is shaped like KAMAR's actual messages: the student number
// is in "student", not the "id" its documentation names.
func realTimetableEntry(student, ics string) string {
	return fmt.Sprintf(`{"student":%s,"uuid":"u","grid":"2026TT","timetable":%q}`, student, ics)
}

func timetableEntry(id, ics string) string {
	return fmt.Sprintf(`{"id":%s,"uuid":"u","grid":"2026TT","timetable":%q}`, id, ics)
}

func TestKamarRefusesWrongOrMissingLogins(t *testing.T) {
	newTestDB(t)
	check := `{"SMSDirectoryData":{"sync":"check","sms":"KAMAR"}}`

	// Not configured: nobody gets in, not even with "empty" credentials.
	if rec := postKamar(t, "", "", check); rec.Code != 403 {
		t.Errorf("unconfigured = %d, want 403", rec.Code)
	}
	setKamarLogin(t)
	for _, login := range [][2]string{{"", ""}, {"kamar-user", "wrong"}, {"wrong", "kamar-pass"}} {
		rec := postKamar(t, login[0], login[1], check)
		if rec.Code != 403 || !strings.Contains(rec.Body.String(), "Authentication Failed") {
			t.Errorf("login %v = %d %s, want 403", login, rec.Code, rec.Body)
		}
	}
	// Refused before the body is read, so junk gets the same answer.
	if rec := postKamar(t, "kamar-user", "wrong", "not json"); rec.Code != 403 {
		t.Errorf("bad login with junk body = %d, want 403", rec.Code)
	}
}

func TestKamarCheckAsksForStudentTimetablesOnly(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	rec := postKamar(t, "kamar-user", "kamar-pass", `{"SMSDirectoryData":{"sync":"check","sms":"KAMAR"}}`)
	if rec.Code != 200 {
		t.Fatalf("check = %d %s", rec.Code, rec.Body)
	}
	var out struct {
		D struct {
			Error   int    `json:"error"`
			Result  string `json:"result"`
			Country string `json:"countryDataStored"`
			Options map[string]interface{}
		} `json:"SMSDirectoryData"`
	}
	decode(t, rec, &out)
	if out.D.Error != 0 || out.D.Result != "OK" || out.D.Country != "New Zealand" {
		t.Errorf("check reply = %+v", out.D)
	}
	students, _ := out.D.Options["students"].(map[string]interface{})
	if out.D.Options["ics"] != true || students["timetables"] != true || students["details"] != true {
		t.Errorf("options = %v", out.D.Options)
	}
	// Details are asked for only so KAMAR unlocks the options: the school's own
	// ID number and nothing optional.
	fields, _ := students["fields"].(map[string]interface{})
	if fields["required"] != "uniqueid" || fields["optional"] != "" {
		t.Errorf("student fields = %v, want only uniqueid", fields)
	}
	// Every option is listed, but only ICS, student details and timetables are on.
	wanted := map[string]bool{"ics": true, "students.details": true, "students.timetables": true}
	for group, v := range out.D.Options {
		sub, isGroup := v.(map[string]interface{})
		if !isGroup {
			if v != wanted[group] {
				t.Errorf("option %s = %v", group, v)
			}
			continue
		}
		for name, val := range sub {
			if b, isBool := val.(bool); isBool && b != wanted[group+"."+name] {
				t.Errorf("option %s.%s = %v, want %v", group, name, b, !b)
			}
		}
	}
	for _, key := range []string{"staff", "common"} {
		if _, ok := out.D.Options[key].(map[string]interface{}); !ok {
			t.Errorf("options.%s missing: KAMAR's screen wants every option listed", key)
		}
	}
	if students["minLevel"] != float64(1) || students["maxLevel"] != float64(13) {
		t.Errorf("year levels = %v-%v, want 1-13", students["minLevel"], students["maxLevel"])
	}
}

func TestKamarTimetablesAreSavedByStudentID(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	msg := timetablesMessage(
		timetableEntry(`18234`, lessonToday("MATH")),    // KAMAR sends numbers…
		timetableEntry(`" kh-55 "`, lessonToday("ENG")), // …or strings
		timetableEntry(`"19999"`, "not a calendar"),     // skipped
	)
	rec := postKamar(t, "kamar-user", "kamar-pass", msg)
	if rec.Code != 200 || !strings.Contains(rec.Body.String(), `"result":"OK"`) {
		t.Fatalf("timetables = %d %s", rec.Code, rec.Body)
	}
	if !strings.Contains(kamarICS("18234"), "MATH") || !strings.Contains(kamarICS("KH-55"), "ENG") {
		t.Error("timetables not saved under their normalised IDs")
	}
	if hasKamarTimetable("19999") {
		t.Error("saved something that isn't a calendar")
	}

	// The next push replaces, rather than adds to, a student's timetable.
	postKamar(t, "kamar-user", "kamar-pass", timetablesMessage(timetableEntry(`18234`, lessonToday("PHYS"))))
	if ics := kamarICS("18234"); !strings.Contains(ics, "PHYS") || strings.Contains(ics, "MATH") {
		t.Errorf("timetable not replaced: %q", ics)
	}
}

func TestKamarSavesTimetablesSentAsStudent(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	postKamar(t, "kamar-user", "kamar-pass", timetablesMessage(realTimetableEntry(`18234`, lessonToday("MATH"))))
	if !strings.Contains(kamarICS("18234"), "MATH") {
		t.Error("a timetable sent under \"student\" was not saved")
	}
}

func TestKamarLogSaysWhyNothingWasSaved(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	var logged bytes.Buffer
	log.SetOutput(&logged)
	t.Cleanup(func() { log.SetOutput(os.Stderr) })

	// One entry with an ID too short to be a student ID, one that isn't a calendar.
	msg := timetablesMessage(
		timetableEntry(`"ab"`, lessonToday("MATH")),
		timetableEntry(`"18234"`, "NOT-A-CALENDAR-SECRET"),
	)
	if rec := postKamar(t, "kamar-user", "kamar-pass", msg); rec.Code != 200 {
		t.Fatalf("post = %d %s", rec.Code, rec.Body)
	}
	out := logged.String()
	for _, want := range []string{
		"2 entries, 0 saved, 1 with an unusable student ID, 1 not a calendar",
		"Nothing saved. Message shape:",
		"firstEntry{grid=text", "timetable=text",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("log is missing %q:\n%s", want, out)
		}
	}
	for _, secret := range []string{"NOT-A-CALENDAR-SECRET", "18234", "MATH"} {
		if strings.Contains(out, secret) {
			t.Errorf("log leaks the value %q:\n%s", secret, out)
		}
	}
}

func TestKamarDropsTimetablesItStopsSending(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	old := time.Now().Add(-kamarRetention - time.Hour).Unix()
	db.Exec(`INSERT INTO kamar_timetables(student_id, ics, updated_at) VALUES('LEFT1', 'BEGIN:VCALENDAR', ?)`, old)
	postKamar(t, "kamar-user", "kamar-pass", timetablesMessage(timetableEntry(`18234`, lessonToday("MATH"))))
	if hasKamarTimetable("LEFT1") {
		t.Error("a timetable KAMAR stopped sending was kept past the retention period")
	}
}

func TestKamarIgnoresMessagesWeDidNotAskFor(t *testing.T) {
	newTestDB(t)
	setKamarLogin(t)
	rec := postKamar(t, "kamar-user", "kamar-pass", `{"SMSDirectoryData":{"sync":"full","students":{"count":1,"data":[{"id":1}]}}}`)
	if rec.Code != 200 {
		t.Errorf("unrequested message = %d, want 200 so KAMAR doesn't disable us", rec.Code)
	}
	var stored int
	db.QueryRow(`SELECT COUNT(*) FROM kamar_timetables`).Scan(&stored)
	if stored != 0 {
		t.Errorf("student records were stored: %d rows", stored)
	}
}

func TestUnlinkedStudentSeesTheirKamarTimetable(t *testing.T) {
	newTestDB(t)
	db.Exec(`INSERT INTO kamar_timetables(student_id, ics, updated_at) VALUES('18234', ?, ?)`, lessonToday("MATH"), time.Now().Unix())

	rec := call(t, verifyBarcode, "POST", "/", `{"barcode":"18234"}`, "")
	var who map[string]interface{}
	decode(t, rec, &who)
	if rec.Code != 200 || who["user_id"] != "kamar|18234" || who["user_name"] != "" {
		t.Fatalf("scan = %d %v", rec.Code, who)
	}

	var tt struct {
		Periods []TimetableEvent `json:"periods"`
	}
	decode(t, call(t, getTimetable, "GET", "/api/timetable?user_id=kamar%7C18234", "", ""), &tt)
	if len(tt.Periods) != 1 || tt.Periods[0].Summary != "MATH" || tt.Periods[0].StartTime != "10:00" {
		t.Errorf("periods = %+v", tt.Periods)
	}

	// Still unknown to both the accounts and KAMAR.
	if rec := call(t, verifyBarcode, "POST", "/", `{"barcode":"77777"}`, ""); rec.Code != 404 {
		t.Errorf("unknown ID = %d, want 404", rec.Code)
	}
}

func TestTimetableIncludesNextWeekButNotTheWeekAfter(t *testing.T) {
	nz := nzLocation()
	now := time.Date(2026, 10, 29, 16, 0, 0, 0, nz) // Thursday after school
	lesson := func(day time.Time, subject string) string {
		d := day.Format("20060102")
		return "BEGIN:VEVENT\r\nDTSTART;TZID=Pacific/Auckland:" + d + "T090000\r\n" +
			"DTEND;TZID=Pacific/Auckland:" + d + "T100000\r\nSUMMARY:" + subject + "\r\nEND:VEVENT\r\n"
	}
	ics := "BEGIN:VCALENDAR\r\n" +
		lesson(now.AddDate(0, 0, -3), "LASTWEEK") + // Monday, this week
		lesson(now.AddDate(0, 0, 1), "FRIDAY") +
		lesson(now.AddDate(0, 0, 4), "NEXTMON") +
		lesson(now.AddDate(0, 0, 8), "NEXTFRI") +
		lesson(now.AddDate(0, 0, 11), "TOOFAR") + // the Monday after next
		"END:VCALENDAR\r\n"

	var got []string
	for _, e := range parseICSWeek(ics, now) {
		got = append(got, e.Summary)
	}
	want := "LASTWEEK FRIDAY NEXTMON NEXTFRI"
	if strings.Join(got, " ") != want {
		t.Errorf("events = %v, want %s", got, want)
	}
}

func TestLinkedStudentGetsKamarTimetableWithoutACalendarLink(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`UPDATE users SET barcode = '18234' WHERE id = ?`, studentID)

	// No KAMAR timetable and no calendar link: nothing to show.
	if rec := call(t, getTimetable, "GET", "/api/timetable?user_id="+studentID, "", ""); rec.Code != 404 {
		t.Errorf("no timetable = %d, want 404", rec.Code)
	}

	db.Exec(`INSERT INTO kamar_timetables(student_id, ics, updated_at) VALUES('18234', ?, ?)`, lessonToday("MATH"), time.Now().Unix())
	rec := call(t, verifyBarcode, "POST", "/", `{"barcode":"18234"}`, "")
	var who map[string]interface{}
	decode(t, rec, &who)
	if who["user_id"] != studentID {
		t.Errorf("a linked account should still sign in as itself, got %v", who["user_id"])
	}
	var tt struct {
		Periods []TimetableEvent `json:"periods"`
	}
	decode(t, call(t, getTimetable, "GET", "/api/timetable?user_id="+studentID, "", ""), &tt)
	if len(tt.Periods) != 1 || tt.Periods[0].Summary != "MATH" {
		t.Errorf("periods = %+v", tt.Periods)
	}
}
