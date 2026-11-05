package main

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/labstack/echo/v4"
)

// The school's exam timetable is NZQA's PDF, which has a new name every year.
// The server reads it off NZQA's exam timetable page, keeps a copy, and serves
// it to the website and the mirror, so nobody has to upload a new one each year.

var (
	examSite     = "https://www2.nzqa.govt.nz" // overridden in tests
	examPagePath = "/ncea/exam-timetable-and-key-assessment-dates/exam-timetable/"
)

const (
	examPDFFresh   = 24 * time.Hour
	examPDFMaxSize = 10 << 20
)

var (
	examPDFMu     sync.Mutex
	examPDFClient = &http.Client{Timeout: 30 * time.Second}

	// The page carries its props as JSON inside the HTML: "downloadVersionLink":"\/assets\/NCEA\/2026-Exam-Timetable.pdf"
	examLinkRe     = regexp.MustCompile(`downloadVersionLink(?:&quot;|")\s*:\s*(?:&quot;|")([^"&]+?)(?:&quot;|")`)
	examLinkAltRe  = regexp.MustCompile(`/assets/NCEA/\d{4}-Exam-Timetable\.pdf`)
	examLinkSafeRe = regexp.MustCompile(`^/assets/[A-Za-z0-9/._-]+\.pdf$`)
)

func examPDFFile() string { return dataPath("exam-timetable.pdf") }

// findExamPDFPath finds the timetable's address on NZQA's page ("" if it isn't there).
func findExamPDFPath(html string) string {
	if m := examLinkRe.FindStringSubmatch(html); m != nil {
		if p := strings.ReplaceAll(m[1], `\/`, "/"); examLinkSafeRe.MatchString(p) {
			return p
		}
	}
	return examLinkAltRe.FindString(html)
}

func examHTTPGet(url string, limit int64) ([]byte, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (compatible; SmartMirror school project)")
	resp, err := examPDFClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s: HTTP %d", url, resp.StatusCode)
	}
	return io.ReadAll(io.LimitReader(resp.Body, limit))
}

// fetchExamPDF reads NZQA's page, finds this year's PDF and saves it.
func fetchExamPDF() error {
	page, err := examHTTPGet(examSite+examPagePath, 5<<20)
	if err != nil {
		return err
	}
	path := findExamPDFPath(string(page))
	if path == "" {
		path = fmt.Sprintf("/assets/NCEA/%d-Exam-Timetable.pdf", today().Year()) // how it has been named
	}
	pdf, err := examHTTPGet(examSite+path, examPDFMaxSize)
	if err != nil {
		return err
	}
	if !bytes.HasPrefix(pdf, []byte("%PDF")) {
		return fmt.Errorf("%s is not a PDF", path)
	}
	tmp := examPDFFile() + ".tmp"
	if err := os.WriteFile(tmp, pdf, 0o644); err != nil {
		return err
	}
	if err := os.Rename(tmp, examPDFFile()); err != nil {
		return err
	}
	log.Printf("[EXAMS] Saved NZQA's exam timetable from %s (%d KB)", path, len(pdf)/1024)
	return nil
}

// ensureExamPDF makes sure there is a copy, refreshing it when it is a day old.
// A failed refresh keeps the old copy. It reports whether there is a copy to serve.
func ensureExamPDF() bool {
	examPDFMu.Lock()
	defer examPDFMu.Unlock()
	if st, err := os.Stat(examPDFFile()); err == nil && time.Since(st.ModTime()) < examPDFFresh {
		return true
	}
	if err := fetchExamPDF(); err != nil {
		log.Printf("[EXAMS] Could not fetch NZQA's exam timetable: %v", err)
	}
	_, err := os.Stat(examPDFFile())
	return err == nil
}

// refreshExamPDFLoop keeps the copy current without anyone asking.
func refreshExamPDFLoop() {
	for {
		ensureExamPDF()
		time.Sleep(6 * time.Hour)
	}
}

// getExamTimetablePDF serves the copy (public: it is NZQA's own page). If the
// server can't get one it sends the person to NZQA's.
func getExamTimetablePDF(c echo.Context) error {
	if !ensureExamPDF() {
		return c.Redirect(http.StatusFound, fmt.Sprintf("%s/assets/NCEA/%d-Exam-Timetable.pdf", examSite, today().Year()))
	}
	f, err := os.Open(examPDFFile())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not read the exam timetable"})
	}
	defer f.Close()
	st, _ := f.Stat()
	c.Response().Header().Set(echo.HeaderContentType, "application/pdf")
	c.Response().Header().Set("Content-Disposition", `inline; filename="Exam-Timetable.pdf"`)
	c.Response().Header().Set("Cache-Control", "public, max-age=3600")
	http.ServeContent(c.Response(), c.Request(), "Exam-Timetable.pdf", st.ModTime(), f)
	return nil
}
