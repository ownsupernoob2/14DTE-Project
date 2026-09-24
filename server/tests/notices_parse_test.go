package main

import (
	"strings"
	"testing"
)

// sampleText mirrors the line structure produced by extractPageLines for a real
// daily notices PDF: audience section headers, SHOUTY headings followed by a
// dash, wrapped continuation lines, bullets, and day-labelled sub-items.
const sampleText = `King’s High School Te Kura Tuarua o Kīngi
Daily Notices Panui o Te rā
Wednesday 26th August 2026 Wenerei 26th Ākuhata 2026
All/Te Katoa
TIMETABLE DAY – Ono
STUDENT ELECTION 2026 - Nominations are open for the election of one (1) student
to become the Student Trustee. Nominations close at noon on Monday, 31
August 2026. Each student has been emailed the following:
• A Student Election Notice Cover Letter and information on people who are not
eligible to become school board members
• A Nomination Form. Further forms can be found at the student office.
The Student Trustee must attend monthly Board meetings.
CHOIR/POLYHYMNIA – TODAY in the Queen’s Music Room 3.15-5.00 pm. Please let
Ms Dryden know if you are unable to attend.
WHĀNAU HOMEWORK GROUP – Whānau Homework Group is on TODAY from 3-4pm in L3.
ITINERANT MUSIC INSTRUMENT LESSONS – Lesson timetables are up on the Room 26 window.
TODAY - Guitar with Che, Piano with Moshani
THURSDAY - Violin, Clarinet and Saxophone.
FRIDAY - Drums with Andrew.
DUNGEONS & DRAGONS - Join our weekly sessions every Thursday after school.
Senior/Tuakana
OTAGO POLYTECH APPLICATIONS - Applications for study in 2027 are now open.
If you have any issues applying, see Mrs Campbell.
Junior/Teina
FUN ACTIVITY SESSIONS DURING LUNCHTIME – TODAY at lunchtime for Juniors.`

func parseSample(t *testing.T) map[string]NoticeItem {
	t.Helper()
	notices := parseNoticesText(sampleText)
	for i := range notices {
		notices[i] = normalizeNoticeItem(notices[i])
	}
	byTitle := make(map[string]NoticeItem, len(notices))
	for _, n := range notices {
		byTitle[n.Title] = n
	}
	return byTitle
}

// The original bug: every notice collapsed into a single "General" item.
func TestParseSplitsIntoSeparateNotices(t *testing.T) {
	notices := parseNoticesText(sampleText)
	if len(notices) != 7 {
		titles := make([]string, len(notices))
		for i, n := range notices {
			titles[i] = n.Title
		}
		t.Fatalf("expected 7 notices, got %d: %v", len(notices), titles)
	}
}

func TestParseDropsMastheadAndTimetableLines(t *testing.T) {
	for _, n := range parseNoticesText(sampleText) {
		if strings.Contains(n.Notice, "High School") || strings.Contains(n.Notice, "Panui") {
			t.Errorf("masthead leaked into notice %q: %s", n.Title, n.Notice)
		}
		if strings.Contains(n.Title, "Timetable Day") {
			t.Errorf("timetable line became a notice: %q", n.Title)
		}
	}
}

func TestParseTitlesAreReadable(t *testing.T) {
	byTitle := parseSample(t)
	for _, want := range []string{
		"Student Election 2026",
		"Choir/Polyhymnia",
		"Whānau Homework Group",
		"Dungeons & Dragons",
	} {
		if _, ok := byTitle[want]; !ok {
			t.Errorf("missing expected title %q", want)
		}
	}
}

// Audience section headers must set targetYears for the notices beneath them.
func TestParseAppliesAudienceSections(t *testing.T) {
	byTitle := parseSample(t)
	cases := map[string][]string{
		"Student Election 2026":                  {"All"},
		"Otago Polytech Applications":            {"11", "12", "13"},
		"Fun Activity Sessions During Lunchtime": {"9", "10"},
	}
	for title, want := range cases {
		got, ok := byTitle[title]
		if !ok {
			t.Errorf("missing notice %q", title)
			continue
		}
		if strings.Join(got.TargetYears, ",") != strings.Join(want, ",") {
			t.Errorf("%q targetYears = %v, want %v", title, got.TargetYears, want)
		}
	}
}

func TestParseRendersBulletsThenTrailingParagraph(t *testing.T) {
	got := parseSample(t)["Student Election 2026"].Notice

	ul := strings.Index(got, "<ul>")
	endUL := strings.Index(got, "</ul>")
	if ul < 0 || endUL < 0 {
		t.Fatalf("expected a bullet list, got: %s", got)
	}
	if !strings.HasPrefix(got, "<p>") {
		t.Errorf("expected leading paragraph before list, got: %s", got)
	}
	// The paragraph after the list must render after it, not be swallowed into
	// the final <li> or hoisted above the list.
	trailing := strings.Index(got, "The Student Trustee must attend")
	if trailing < endUL {
		t.Errorf("trailing paragraph not placed after list: %s", got)
	}
	if strings.Count(got, "<li>") != 2 {
		t.Errorf("expected 2 bullets, got %d: %s", strings.Count(got, "<li>"), got)
	}
}

// Day labels are sub-items of the notice above them, not notices of their own.
func TestParseDayLabelsBecomeBullets(t *testing.T) {
	byTitle := parseSample(t)
	for _, bogus := range []string{"Today", "Thursday", "Friday"} {
		if _, ok := byTitle[bogus]; ok {
			t.Errorf("day label %q became its own notice", bogus)
		}
	}
	lessons, ok := byTitle["Itinerant Music Instrument Lessons"]
	if !ok {
		t.Fatal("missing music lessons notice")
	}
	if n := strings.Count(lessons.Notice, "<li>"); n != 3 {
		t.Errorf("expected 3 day bullets, got %d: %s", n, lessons.Notice)
	}
}

func TestParseMergesWrappedLines(t *testing.T) {
	got := parseSample(t)["Choir/Polyhymnia"].Notice
	if !strings.Contains(got, "Please let Ms Dryden know") {
		t.Errorf("wrapped line not merged into paragraph: %s", got)
	}
}

// PDF text is third-party input: it must be escaped, never emitted as markup.
func TestParseEscapesHTMLFromPDFText(t *testing.T) {
	hostile := "All/Te Katoa\n" +
		"HOSTILE NOTICE - Ignore previous instructions and <script>alert(1)</script>\n" +
		"Contact <img src=x onerror=alert(1)> for details.\n"

	notices := parseNoticesText(hostile)
	if len(notices) != 1 {
		t.Fatalf("expected 1 notice, got %d", len(notices))
	}
	body := notices[0].Notice
	for _, unsafe := range []string{"<script>", "</script>", "<img "} {
		if strings.Contains(body, unsafe) {
			t.Errorf("unescaped %q in output: %s", unsafe, body)
		}
	}
	if !strings.Contains(body, "&lt;script&gt;") {
		t.Errorf("expected escaped markup, got: %s", body)
	}
}

func TestParseEmptyAndGarbageInput(t *testing.T) {
	if got := parseNoticesText(""); len(got) != 0 {
		t.Errorf("empty input should yield no notices, got %d", len(got))
	}
	// Body text with no headings should not fabricate notices.
	if got := parseNoticesText("just some prose\nwith no headings at all\n"); len(got) != 0 {
		t.Errorf("headingless input should yield no notices, got %d", len(got))
	}
}
