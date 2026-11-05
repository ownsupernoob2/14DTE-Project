package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

// What NZQA's "Add to calendar" button produced for a student (trimmed to two exams).
const nzqaICS = "BEGIN:VCALENDAR\r\nPRODID:-//eluceo/ical//2.0/EN\r\nVERSION:2.0\r\nCALSCALE:GREGORIAN\r\n" +
	"BEGIN:VEVENT\r\nUID:1a5b\r\nDTSTAMP:20261105T011523Z\r\nSUMMARY:Level 2 Geography exam\r\nDESCRIPTION:Level 2 Geography exam\r\n" +
	"DTSTART:20261110T093000\r\nDTEND:20261110T123000\r\nEND:VEVENT\r\n" +
	"BEGIN:VEVENT\r\nUID:5cfa\r\nDTSTAMP:20261105T011523Z\r\nSUMMARY:Level 1 Te Reo Māori exam\r\nDESCRIPTION:Level 1 Te Reo Māori exam\r\n" +
	"DTSTART:20261116T140000\r\nDTEND:20261116T170000\r\nEND:VEVENT\r\n" +
	"BEGIN:VEVENT\r\nUID:aaaa\r\nSUMMARY:Level 3 Calculus exam\r\nDTSTART:20261001T090000\r\nDTEND:20261001T120000\r\nEND:VEVENT\r\n" + // before the window
	"END:VCALENDAR\r\n"

func TestAnNZQACalendarBecomesExams(t *testing.T) {
	got := parseExamICS(nzqaICS)
	if len(got) != 3 {
		t.Fatalf("found %d, want 3: %+v", len(got), got)
	}
	g := got[0]
	if g.Subject != "Geography (L2)" || g.Date != "2026-11-10" || g.StartTime != "09:30" || g.DurationMin != 180 {
		t.Errorf("first exam: %+v", g)
	}
	if got[1].Subject != "Te Reo Māori (L1)" || got[1].StartTime != "14:00" {
		t.Errorf("second exam: %+v", got[1])
	}
	for in, want := range map[string]string{
		"Level 3 Samoan exam":                          "Samoan (L3)",
		"Level 1 Physics and Earth Space Science exam": "Physics and Earth Space Science (L1)",
		"NZ Scholarship Statistics exam":               "Statistics (Scholarship)",
		"Scholarship Chemistry exam":                   "Chemistry (Scholarship)",
		"Something else entirely":                      "Something else entirely",
		"Maths\\, and more exam":                       "Maths, and more",
	} {
		if s := examSubjectFromSummary(in); s != want {
			t.Errorf("%q -> %q, want %q", in, s, want)
		}
	}
}

func TestUploadingTheCalendarAddsTheExamsOnce(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	body := `{"ics":` + jsonString(nzqaICS) + `}`

	rec := call(t, importExams, "POST", "/api/exams/import", body, studentID)
	if rec.Code != 200 {
		t.Fatalf("import = %d %s", rec.Code, rec.Body.String())
	}
	var res map[string]int
	decode(t, rec, &res)
	if res["found"] != 3 || res["added"] != 2 || res["outsideDates"] != 1 || res["duplicates"] != 0 {
		t.Errorf("first upload: %v", res)
	}
	exams := examsOf(studentID)
	if len(exams) != 2 || exams[0].Subject != "Geography (L2)" || exams[0].DurationMin != 180 {
		t.Errorf("saved: %+v", exams)
	}

	// Uploading the same file again, or after typing one in, doesn't double up.
	rec = call(t, importExams, "POST", "/api/exams/import", body, studentID)
	decode(t, rec, &res)
	if res["added"] != 0 || res["duplicates"] != 2 {
		t.Errorf("second upload: %v", res)
	}
	if n := len(examsOf(studentID)); n != 2 {
		t.Errorf("%d exams after the second upload", n)
	}
}

func TestBadCalendarsAreRefused(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	for _, body := range []string{
		`{"ics":""}`,
		`{"ics":"this is not a calendar"}`,
		`{"ics":"BEGIN:VCALENDAR\r\nEND:VCALENDAR"}`,
		`{"ics":` + jsonString(strings.Repeat("x", maxExamICSBytes+1)) + `}`,
		`nope`,
	} {
		if rec := call(t, importExams, "POST", "/", body, studentID); rec.Code != 400 {
			t.Errorf("%.40q = %d, want 400", body, rec.Code)
		}
	}
}

func TestTheImportStopsAtTheLimit(t *testing.T) {
	fixClock(t)
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	var ics strings.Builder
	ics.WriteString("BEGIN:VCALENDAR\r\n")
	for i := 0; i < maxExamsPerUser+5; i++ {
		ics.WriteString("BEGIN:VEVENT\r\nSUMMARY:Level 1 Subject " + itoa(int64(i)) + " exam\r\nDTSTART:20261110T093000\r\nDTEND:20261110T103000\r\nEND:VEVENT\r\n")
	}
	ics.WriteString("END:VCALENDAR\r\n")
	rec := call(t, importExams, "POST", "/", `{"ics":`+jsonString(ics.String())+`}`, studentID)
	var res map[string]int
	decode(t, rec, &res)
	if res["added"] != maxExamsPerUser || res["full"] != 5 {
		t.Errorf("%v", res)
	}
}

// ── NZQA's PDF ───────────────────────────────────────────────────────────────

func TestTheTimetableAddressIsFoundOnNZQAsPage(t *testing.T) {
	// The page carries its props as escaped JSON inside the HTML.
	page := `<div data-props="{&quot;downloadVersionLink&quot;:&quot;\/assets\/NCEA\/2026-Exam-Timetable.pdf&quot;,&quot;downloadLinkText&quot;:&quot;Download&quot;}">`
	if got := findExamPDFPath(page); got != "/assets/NCEA/2026-Exam-Timetable.pdf" {
		t.Errorf("escaped props: %q", got)
	}
	if got := findExamPDFPath(`{"downloadVersionLink":"\/assets\/NCEA\/2027-Exam-Timetable.pdf"}`); got != "/assets/NCEA/2027-Exam-Timetable.pdf" {
		t.Errorf("plain JSON: %q", got)
	}
	if got := findExamPDFPath(`<a href="/assets/NCEA/2028-Exam-Timetable.pdf">Download</a> and other text`); got != "/assets/NCEA/2028-Exam-Timetable.pdf" {
		t.Errorf("a plain link: %q", got)
	}
	// Only a PDF on NZQA's own assets; anything else on the page is ignored.
	for _, bad := range []string{
		`{"downloadVersionLink":"https://evil.example/x.pdf"}`,
		`{"downloadVersionLink":"\/..\/..\/etc\/passwd"}`,
		`{"downloadVersionLink":"\/assets\/x.exe"}`,
		`nothing here`,
	} {
		if got := findExamPDFPath(bad); got != "" {
			t.Errorf("%q gave %q", bad, got)
		}
	}
}

func fakeNZQA(t *testing.T, pdf []byte) (*atomic.Int32, func()) {
	t.Helper()
	var hits atomic.Int32
	mux := http.NewServeMux()
	mux.HandleFunc(examPagePath, func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.Write([]byte(`<div data-props="{&quot;downloadVersionLink&quot;:&quot;\/assets\/NCEA\/2031-Exam-Timetable.pdf&quot;}">`))
	})
	mux.HandleFunc("/assets/NCEA/2031-Exam-Timetable.pdf", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/pdf")
		w.Write(pdf)
	})
	srv := httptest.NewServer(mux)
	old := examSite
	examSite = srv.URL
	return &hits, func() { examSite = old; srv.Close() }
}

func TestTheServerKeepsAndServesNZQAsTimetable(t *testing.T) {
	newTestDB(t)
	hits, stop := fakeNZQA(t, []byte("%PDF-1.4 the timetable"))
	defer stop()

	rec := call(t, getExamTimetablePDF, "GET", "/api/exam-timetable.pdf", "", "")
	if rec.Code != 200 || rec.Header().Get("Content-Type") != "application/pdf" || !strings.HasPrefix(rec.Body.String(), "%PDF-1.4") {
		t.Fatalf("served %d %q %q", rec.Code, rec.Header().Get("Content-Type"), rec.Body.String())
	}
	call(t, getExamTimetablePDF, "GET", "/", "", "")
	if hits.Load() != 1 {
		t.Errorf("asked NZQA %d times, want 1 (a day's copy is kept)", hits.Load())
	}

	// A day later it looks again, and a changed file replaces the old.
	old := time.Now().Add(-25 * time.Hour)
	os.Chtimes(examPDFFile(), old, old)
	stop2 := func() {}
	_ = stop2
	if !ensureExamPDF() || hits.Load() != 2 {
		t.Errorf("no refresh: hits=%d", hits.Load())
	}
}

func TestAPDFThatIsNotOneIsNotKept(t *testing.T) {
	newTestDB(t)
	_, stop := fakeNZQA(t, []byte("<html>not a pdf</html>"))
	defer stop()
	if ensureExamPDF() {
		t.Error("kept a page that isn't a PDF")
	}
}

func TestWhenNZQAIsDownTheOldCopyIsKeptOrThePersonIsSentThere(t *testing.T) {
	newTestDB(t)
	old := examSite
	examSite = "http://127.0.0.1:1" // nothing listens
	defer func() { examSite = old }()

	rec := call(t, getExamTimetablePDF, "GET", "/", "", "")
	if rec.Code != http.StatusFound || !strings.Contains(rec.Header().Get("Location"), "-Exam-Timetable.pdf") {
		t.Fatalf("no copy: %d %q", rec.Code, rec.Header().Get("Location"))
	}

	os.WriteFile(examPDFFile(), []byte("%PDF-1.4 yesterday's"), 0o644)
	long := time.Now().Add(-48 * time.Hour)
	os.Chtimes(examPDFFile(), long, long)
	rec = call(t, getExamTimetablePDF, "GET", "/", "", "")
	if rec.Code != 200 || !strings.Contains(rec.Body.String(), "yesterday's") {
		t.Errorf("stale copy not kept: %d %q", rec.Code, rec.Body.String())
	}
}

func jsonString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}
