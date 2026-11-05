package main

import (
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/labstack/echo/v4"
)

// Exams a student types in themselves, to show on the website and the mirror
// when they have no class (KAMAR's timetable doesn't carry them).
const (
	maxExamsPerUser = 40
	examKeepDays    = 7 // an exam stays listed this long after its day, then is deleted
)

type examJSON struct {
	ID          int64  `json:"id"`
	Subject     string `json:"subject"`
	Date        string `json:"date"`      // YYYY-MM-DD
	StartTime   string `json:"startTime"` // HH:MM, or "" when not known
	DurationMin int    `json:"durationMin"`
	Room        string `json:"room"`
}

// examNow is the clock, so tests can fix the date.
var examNow = time.Now

func today() time.Time {
	n := examNow().In(nzLocation())
	return time.Date(n.Year(), n.Month(), n.Day(), 0, 0, 0, 0, nzLocation())
}

// examWindow is when exams can be entered for: 1 November to 9 December of this year.
func examWindow() (start, end time.Time) {
	y := today().Year()
	return time.Date(y, time.November, 1, 0, 0, 0, 0, nzLocation()),
		time.Date(y, time.December, 9, 0, 0, 0, 0, nzLocation())
}

// pruneOldExams deletes this student's exams that finished a while ago.
func pruneOldExams(userID string) {
	cutoff := today().AddDate(0, 0, -examKeepDays).Format("2006-01-02")
	db.Exec(`DELETE FROM exams WHERE user_id = ? AND exam_date < ?`, userID, cutoff)
}

// listExams returns the exams, soonest first. A signed-in user gets their own; a
// mirror (with its key) may ask for any user with ?user_id=, as for timetables.
func listExams(c echo.Context) error {
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
	return c.JSON(http.StatusOK, map[string]interface{}{"exams": examsOf(userID)})
}

func examsOf(userID string) []examJSON {
	pruneOldExams(userID)
	out := []examJSON{}
	rows, err := db.Query(`SELECT id, subject, exam_date, start_time, duration_min, room FROM exams
		WHERE user_id = ? ORDER BY exam_date, CASE WHEN start_time = '' THEN '99:99' ELSE start_time END, id`, userID)
	if err != nil {
		return out
	}
	defer rows.Close()
	for rows.Next() {
		var e examJSON
		if rows.Scan(&e.ID, &e.Subject, &e.Date, &e.StartTime, &e.DurationMin, &e.Room) == nil {
			out = append(out, e)
		}
	}
	return out
}

// checkExam tidies and checks one exam. The string is what to tell the student
// when it isn't acceptable.
func checkExam(subject, date, start string, durationMin int, room string) (examJSON, string) {
	subject = strings.Join(strings.Fields(subject), " ")
	room = strings.Join(strings.Fields(room), " ")
	if n := utf8.RuneCountInString(subject); n == 0 || n > 60 {
		return examJSON{}, "Type the exam's subject (up to 60 characters)."
	}
	if utf8.RuneCountInString(room) > 24 {
		return examJSON{}, "The room is too long (up to 24 characters)."
	}
	day, err := time.ParseInLocation("2006-01-02", strings.TrimSpace(date), nzLocation())
	if err != nil {
		return examJSON{}, "Pick the exam's date."
	}
	if from, to := examWindow(); day.Before(from) || day.After(to) {
		return examJSON{}, "Exams can be entered for 1 November to 9 December."
	}
	start = strings.TrimSpace(start)
	if start != "" {
		t, err := time.Parse("15:04", start)
		if err != nil {
			return examJSON{}, "The start time should look like 09:30."
		}
		start = t.Format("15:04")
	}
	if durationMin < 0 || durationMin > 600 {
		return examJSON{}, "The length should be between 0 and 600 minutes."
	}
	return examJSON{Subject: subject, Date: day.Format("2006-01-02"), StartTime: start, DurationMin: durationMin, Room: room}, ""
}

// saveExam stores a checked exam for a student, unless they are at the limit.
func saveExam(userID string, e examJSON) (examJSON, error) {
	res, err := db.Exec(`INSERT INTO exams(user_id, subject, exam_date, start_time, duration_min, room) VALUES(?, ?, ?, ?, ?, ?)`,
		userID, e.Subject, e.Date, e.StartTime, e.DurationMin, e.Room)
	if err != nil {
		return e, err
	}
	e.ID, _ = res.LastInsertId()
	return e, nil
}

func examCount(userID string) int {
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM exams WHERE user_id = ?`, userID).Scan(&n)
	return n
}

// addExam saves one exam for the signed-in student.
func addExam(c echo.Context) error {
	var body struct {
		Subject     string `json:"subject"`
		Date        string `json:"date"`
		StartTime   string `json:"startTime"`
		DurationMin int    `json:"durationMin"`
		Room        string `json:"room"`
	}
	if err := c.Bind(&body); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	exam, problem := checkExam(body.Subject, body.Date, body.StartTime, body.DurationMin, body.Room)
	if problem != "" {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": problem})
	}
	userID := getUserIDFromToken(c)
	pruneOldExams(userID)
	if examCount(userID) >= maxExamsPerUser {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "That's the most exams you can keep (" + strconv.Itoa(maxExamsPerUser) + "). Delete one first."})
	}
	saved, err := saveExam(userID, exam)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save the exam"})
	}
	return c.JSON(http.StatusOK, saved)
}

// deleteExam removes one of the signed-in student's exams.
func deleteExam(c echo.Context) error {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Bad exam id"})
	}
	res, err := db.Exec(`DELETE FROM exams WHERE id = ? AND user_id = ?`, id, getUserIDFromToken(c))
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete the exam"})
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No such exam"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Exam deleted"})
}
