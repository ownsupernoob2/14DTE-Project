package main

import (
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

// NZQA's exam timetable page has an "Add to calendar" button that makes an .ics
// of the exams a student picked. Students upload it here instead of typing them.

const maxExamICSBytes = 300 * 1024

var examLevelRe = regexp.MustCompile(`(?i)^(?:NZ\s+)?(Level\s+(\d)|Scholarship)\s+(.+?)(?:\s+exam)?$`)

// icsUnescape undoes the escaping RFC 5545 puts on text values.
func icsUnescape(s string) string {
	return strings.NewReplacer(`\n`, " ", `\N`, " ", `\,`, ",", `\;`, ";", `\\`, `\`).Replace(s)
}

// examSubjectFromSummary turns "Level 2 Geography exam" into "Geography (L2)".
func examSubjectFromSummary(summary string) string {
	summary = strings.Join(strings.Fields(icsUnescape(summary)), " ")
	if m := examLevelRe.FindStringSubmatch(summary); m != nil {
		level := "Scholarship"
		if m[2] != "" {
			level = "L" + m[2]
		}
		return m[3] + " (" + level + ")"
	}
	return strings.TrimSpace(strings.TrimSuffix(summary, " exam"))
}

// parseExamICS reads the exams out of a calendar: subject, date, start time and length.
func parseExamICS(body string) []examJSON {
	var out []examJSON
	var summary, startLine, endLine string
	in := false
	for _, line := range unfoldICSLines(body) {
		switch {
		case strings.HasPrefix(line, "BEGIN:VEVENT"):
			in, summary, startLine, endLine = true, "", "", ""
		case strings.HasPrefix(line, "END:VEVENT"):
			if in && summary != "" && startLine != "" {
				if start, err := parseICSTime(startLine); err == nil {
					e := examJSON{Subject: examSubjectFromSummary(summary), Date: start.Format("2006-01-02")}
					if !strings.Contains(startLine, "VALUE=DATE") && len(strings.TrimSpace(startLine[strings.Index(startLine, ":")+1:])) > 8 {
						e.StartTime = start.Format("15:04")
						if end, err := parseICSTime(endLine); err == nil && end.After(start) {
							e.DurationMin = int(end.Sub(start) / time.Minute)
						}
					}
					out = append(out, e)
				}
			}
			in = false
		case in && strings.HasPrefix(line, "SUMMARY"):
			if i := strings.Index(line, ":"); i >= 0 {
				summary = line[i+1:]
			}
		case in && strings.HasPrefix(line, "DTSTART"):
			startLine = line
		case in && strings.HasPrefix(line, "DTEND"):
			endLine = line
		}
	}
	return out
}

// importExams adds the exams in an uploaded .ics to the signed-in student's list.
func importExams(c echo.Context) error {
	var body struct {
		ICS string `json:"ics"`
	}
	if err := c.Bind(&body); err != nil || strings.TrimSpace(body.ICS) == "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Choose the .ics file NZQA gave you."})
	}
	if len(body.ICS) > maxExamICSBytes {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "That file is too big to be an exam calendar."})
	}
	found := parseExamICS(body.ICS)
	if len(found) == 0 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "No exams were found in that file. Use the .ics from NZQA's \"Add to calendar\" button."})
	}

	userID := getUserIDFromToken(c)
	pruneOldExams(userID)
	have := map[string]bool{}
	for _, x := range examsOf(userID) {
		have[x.Subject+"|"+x.Date+"|"+x.StartTime] = true
	}
	count := examCount(userID)
	added, duplicates, outside, full := 0, 0, 0, 0
	for _, f := range found {
		exam, problem := checkExam(f.Subject, f.Date, f.StartTime, f.DurationMin, "")
		if problem != "" {
			outside++
			continue
		}
		key := exam.Subject + "|" + exam.Date + "|" + exam.StartTime
		if have[key] {
			duplicates++
			continue
		}
		if count >= maxExamsPerUser {
			full++
			continue
		}
		if _, err := saveExam(userID, exam); err != nil {
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save your exams"})
		}
		have[key] = true
		count++
		added++
	}
	return c.JSON(http.StatusOK, map[string]int{
		"found": len(found), "added": added, "duplicates": duplicates, "outsideDates": outside, "full": full,
	})
}
