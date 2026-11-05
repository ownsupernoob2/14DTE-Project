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
	subject := strings.Join(strings.Fields(body.Subject), " ")
	room := strings.Join(strings.Fields(body.Room), " ")
	if n := utf8.RuneCountInString(subject); n == 0 || n > 60 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Type the exam's subject (up to 60 characters)."})
	}
	if utf8.RuneCountInString(room) > 24 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "The room is too long (up to 24 characters)."})
	}
	day, err := time.ParseInLocation("2006-01-02", strings.TrimSpace(body.Date), nzLocation())
	if err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Pick the exam's date."})
	}
	if start, end := examWindow(); day.Before(start) || day.After(end) {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Exams can be entered for 1 November to 9 December."})
	}
	start := strings.TrimSpace(body.StartTime)
	if start != "" {
		t, err := time.Parse("15:04", start)
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"error": "The start time should look like 09:30."})
		}
		start = t.Format("15:04")
	}
	if body.DurationMin < 0 || body.DurationMin > 600 {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "The length should be between 0 and 600 minutes."})
	}

	userID := getUserIDFromToken(c)
	pruneOldExams(userID)
	var count int
	db.QueryRow(`SELECT COUNT(*) FROM exams WHERE user_id = ?`, userID).Scan(&count)
	if count >= maxExamsPerUser {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "That's the most exams you can keep (" + strconv.Itoa(maxExamsPerUser) + "). Delete one first."})
	}
	res, err := db.Exec(`INSERT INTO exams(user_id, subject, exam_date, start_time, duration_min, room) VALUES(?, ?, ?, ?, ?, ?)`,
		userID, subject, day.Format("2006-01-02"), start, body.DurationMin, room)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save the exam"})
	}
	id, _ := res.LastInsertId()
	return c.JSON(http.StatusOK, examJSON{ID: id, Subject: subject, Date: day.Format("2006-01-02"),
		StartTime: start, DurationMin: body.DurationMin, Room: room})
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
