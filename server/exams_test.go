package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/labstack/echo/v4"
)

// fixClock makes it Thursday 5 November 2026, inside the exam window.
func fixClock(t *testing.T) {
	t.Helper()
	old := examNow
	examNow = func() time.Time { return time.Date(2026, time.November, 5, 12, 0, 0, 0, nzLocation()) }
	t.Cleanup(func() { examNow = old })
}

func examDay(offset int) string {
	return today().AddDate(0, 0, offset).Format("2006-01-02")
}

func TestStudentsCanAddAndRemoveTheirOwnExams(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	addUser(t, "auth0|other", "other@kingshigh.school.nz")

	add := func(sub, body string) *httptest.ResponseRecorder {
		return call(t, addExam, "POST", "/api/exams", body, sub)
	}
	for _, body := range []string{
		`{"subject":"Calculus","date":"` + examDay(10) + `","startTime":"13:00","durationMin":180,"room":"Hall"}`,
		`{"subject":"  Physics  ","date":"` + examDay(3) + `","startTime":"9:30"}`,
		`{"subject":"English","date":"` + examDay(3) + `"}`, // no time: listed after the timed one that day
	} {
		if rec := add(studentID, body); rec.Code != 200 {
			t.Fatalf("add %s = %d %s", body, rec.Code, rec.Body.String())
		}
	}
	add("auth0|other", `{"subject":"Not mine","date":"`+examDay(2)+`"}`)

	var list struct{ Exams []examJSON }
	os.Setenv("MIRROR_API_KEY", "mirror-secret")
	defer os.Unsetenv("MIRROR_API_KEY")
	e := newServer()
	req := httptest.NewRequest("GET", "/api/exams?user_id="+studentID, nil)
	req.Header.Set("X-Mirror-Key", "mirror-secret")
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("mirror list = %d %s", rec.Code, rec.Body.String())
	}
	decode(t, rec, &list)
	var subjects []string
	for _, x := range list.Exams {
		subjects = append(subjects, x.Subject)
	}
	if got := strings.Join(subjects, ","); got != "Physics,English,Calculus" {
		t.Errorf("order = %s, want Physics,English,Calculus (soonest first, no-time exams last that day, only mine)", got)
	}
	if list.Exams[0].StartTime != "09:30" {
		t.Errorf("time not tidied: %q", list.Exams[0].StartTime)
	}

	// Only the owner can delete one.
	id := list.Exams[0].ID
	if rec := call(t, deleteExam, "DELETE", "/", "", "auth0|other", "id", itoa(id)); rec.Code != 404 {
		t.Errorf("someone else's delete = %d", rec.Code)
	}
	if rec := call(t, deleteExam, "DELETE", "/", "", studentID, "id", itoa(id)); rec.Code != 200 {
		t.Errorf("own delete = %d", rec.Code)
	}
	if n := len(examsOf(studentID)); n != 2 {
		t.Errorf("%d exams left, want 2", n)
	}
}

func TestExamsAreChecked(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	bad := []string{
		`{"subject":"","date":"` + examDay(2) + `"}`,
		`{"subject":"` + strings.Repeat("x", 61) + `","date":"` + examDay(2) + `"}`,
		`{"subject":"Maths","date":"tomorrow"}`,
		`{"subject":"Maths","date":""}`,
		`{"subject":"Maths","date":"2026-10-31"}`, // the day before the window opens
		`{"subject":"Maths","date":"2026-12-10"}`, // the day after it closes
		`{"subject":"Maths","date":"2027-11-10"}`, // next year's
		`{"subject":"Maths","date":"` + examDay(2) + `","startTime":"25:99"}`,
		`{"subject":"Maths","date":"` + examDay(2) + `","durationMin":9000}`,
		`{"subject":"Maths","date":"` + examDay(2) + `","room":"` + strings.Repeat("r", 25) + `"}`,
		`not json`,
	}
	for _, body := range bad {
		if rec := call(t, addExam, "POST", "/", body, studentID); rec.Code != http.StatusBadRequest {
			t.Errorf("%q = %d, want 400", body, rec.Code)
		}
	}
	if n := len(examsOf(studentID)); n != 0 {
		t.Errorf("%d bad exams were saved", n)
	}
	// The first and last days of the window are fine, and so is an exam from yesterday
	// (someone adding what they just sat).
	for _, day := range []string{"2026-11-01", "2026-12-09", examDay(-1)} {
		if rec := call(t, addExam, "POST", "/", `{"subject":"Maths","date":"`+day+`"}`, studentID); rec.Code != 200 {
			t.Errorf("%s = %d", day, rec.Code)
		}
	}
}

func TestExamsAreCappedPrunedAndWiped(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	for i := 0; i < maxExamsPerUser; i++ {
		call(t, addExam, "POST", "/", `{"subject":"E","date":"`+examDay(5)+`"}`, studentID)
	}
	if rec := call(t, addExam, "POST", "/", `{"subject":"One too many","date":"`+examDay(5)+`"}`, studentID); rec.Code != 400 {
		t.Errorf("past the cap = %d", rec.Code)
	}

	// Old ones go on their own once the week is out.
	db.Exec(`DELETE FROM exams`)
	db.Exec(`INSERT INTO exams(user_id, subject, exam_date) VALUES(?, 'Old', ?)`, studentID, examDay(-examKeepDays-1))
	db.Exec(`INSERT INTO exams(user_id, subject, exam_date) VALUES(?, 'Recent', ?)`, studentID, examDay(-2))
	got := examsOf(studentID)
	if len(got) != 1 || got[0].Subject != "Recent" {
		t.Errorf("after pruning: %+v", got)
	}

	// Wiping your data, or an admin deleting you, takes them too.
	if rec := call(t, deleteMyData, "DELETE", "/", "", studentID); rec.Code != 200 {
		t.Fatalf("wipe = %d", rec.Code)
	}
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM exams WHERE user_id = ?`, studentID).Scan(&n)
	if n != 0 {
		t.Errorf("%d exams survived the wipe", n)
	}
	call(t, addExam, "POST", "/", `{"subject":"Again","date":"`+examDay(4)+`"}`, studentID)
	addUser(t, adminID, "admin@kingshigh.school.nz")
	if rec := call(t, adminDeleteUser, "DELETE", "/", "", adminID, "id", studentID); rec.Code != 200 {
		t.Fatalf("admin delete = %d %s", rec.Code, rec.Body.String())
	}
	db.QueryRow(`SELECT COUNT(*) FROM exams WHERE user_id = ?`, studentID).Scan(&n)
	if n != 0 {
		t.Errorf("%d exams survived the account deletion", n)
	}
}

func TestExamRoutesNeedTheRightCredentials(t *testing.T) {
	newTestDB(t)
	os.Setenv("MIRROR_API_KEY", "mirror-secret")
	defer os.Unsetenv("MIRROR_API_KEY")
	e := newServer()
	for _, tc := range []struct {
		method, path string
		header       map[string]string
		want         int
	}{
		{"GET", "/api/exams?user_id=x", nil, 401},
		{"GET", "/api/exams?user_id=x", map[string]string{"X-Mirror-Key": "wrong"}, 401},
		{"GET", "/api/exams?user_id=x", map[string]string{"X-Mirror-Key": "mirror-secret"}, 200},
		{"POST", "/api/exams", nil, 401},
		{"POST", "/api/exams", map[string]string{"X-Mirror-Key": "mirror-secret"}, 401}, // a mirror can't add exams
		{"DELETE", "/api/exams/1", nil, 401},
	} {
		req := httptest.NewRequest(tc.method, tc.path, strings.NewReader("{}"))
		req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
		for k, v := range tc.header {
			req.Header.Set(k, v)
		}
		rec := httptest.NewRecorder()
		e.ServeHTTP(rec, req)
		if rec.Code != tc.want {
			t.Errorf("%s %s %v = %d, want %d", tc.method, tc.path, tc.header, rec.Code, tc.want)
		}
	}
	_ = time.Now
}
