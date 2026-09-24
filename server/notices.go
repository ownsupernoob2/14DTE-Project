package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/PuerkitoBio/goquery"
	"github.com/labstack/echo/v4"
	"github.com/ledongthuc/pdf"
)

const (
	noticesURL = "https://www.kingshigh.school.nz/whats-on/daily-notices/"
	dataDir    = "data"
	outFile    = "data/daily_notices.json"
)

type NoticeItem struct {
	Title       string   `json:"title"`
	Category    string   `json:"category"`
	Notice      string   `json:"notice"`
	TargetYears []string `json:"targetYears"`
	Importance  string   `json:"importance"`
	Contact     string   `json:"contact"`
}

// NoticesFile is the wrapper stored in daily_notices.json
type NoticesFile struct {
	FetchedAt string       `json:"fetchedAt"`
	Notices   []NoticeItem `json:"notices"`
}

func StartNoticeFetcher() {
	go func() {
		firstRun := true
		for {
			now := time.Now()
			stat, err := os.Stat(outFile)

			needsFetch := false
			if err != nil {
				// File doesn't exist at all
				log.Println("[notices] No notices file found — fetching on startup.")
				needsFetch = true
			} else {
				today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, now.Location())
				if stat.ModTime().Before(today) || firstRun {
					if firstRun {
						log.Println("[notices] Startup noticed - forcing fresh notices fetch on boot.")
					} else {
						log.Println("[notices] Notices are stale — refreshing.")
					}
					needsFetch = true
				}
			}

			if needsFetch {
				if err := fetchNoticesLogic(); err != nil {
					log.Printf("[notices] Fetch failed: %v", err)
				}
			}

			firstRun = false
			time.Sleep(10 * time.Minute)
		}
	}()
}

func getNotices(c echo.Context) error {
	data, err := os.ReadFile(outFile)
	if err != nil {
		return c.JSON(404, map[string]string{"error": "Notices not found"})
	}

	// Try to parse as the new wrapper format first
	var wrapper NoticesFile
	if err := json.Unmarshal(data, &wrapper); err == nil && wrapper.Notices != nil {
		return c.JSON(200, wrapper)
	}

	// Legacy fallback: bare array
	var notices []NoticeItem
	if err := json.Unmarshal(data, &notices); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to parse notices"})
	}
	return c.JSON(200, NoticesFile{
		FetchedAt: "",
		Notices:   notices,
	})
}

func fetchNotices(c echo.Context) error {
	err := fetchNoticesLogic()
	if err != nil {
		return c.JSON(500, map[string]string{"error": err.Error()})
	}
	return c.JSON(200, map[string]string{"message": "Notices fetched successfully"})
}

const configOutFile = "data/notices_config.json"

func getNoticesConfig(c echo.Context) error {
	data, err := os.ReadFile(configOutFile)
	if err != nil {
		return c.JSON(200, map[string]interface{}{})
	}
	var cfg map[string]interface{}
	if err := json.Unmarshal(data, &cfg); err != nil {
		return c.JSON(200, map[string]interface{}{})
	}
	return c.JSON(200, cfg)
}

func saveNoticesConfig(c echo.Context) error {
	var body map[string]interface{}
	if err := c.Bind(&body); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid JSON"})
	}
	os.MkdirAll(dataDir, 0755)
	data, err := json.MarshalIndent(body, "", "  ")
	if err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to marshal config"})
	}
	if err := os.WriteFile(configOutFile, data, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to write config"})
	}
	return c.JSON(200, map[string]interface{}{"status": "ok", "config": body})
}

func fetchNoticesLogic() error {
	os.MkdirAll(dataDir, 0755)

	log.Println("Fetching latest notices PDF...")
	pdfURL, err := fetchLatestPDFURL()
	if err != nil {
		return fmt.Errorf("error fetching PDF URL: %v", err)
	}

	var text string
	if pdfURL != "" {
		log.Printf("Found PDF URL: %s", pdfURL)
		text, err = downloadAndExtractText(pdfURL)
		if err != nil {
			log.Printf("Error extracting text: %v", err)
		}
	}

	// Local fallback for dev/testing
	if text == "" {
		localHTML := filepath.Join("..", "daily-notices.html")
		if _, err := os.Stat(localHTML); err == nil {
			log.Println("Using local daily-notices.html fallback")
			file, err := os.Open(localHTML)
			if err == nil {
				doc, err := goquery.NewDocumentFromReader(file)
				if err == nil {
					href, exists := doc.Find("div.document.pdf a").Attr("href")
					if exists {
						testURL := "https://www.kingshigh.school.nz" + href
						text, _ = downloadAndExtractText(testURL)
					}
				}
				file.Close()
			}
		}
	}

	var notices []NoticeItem

	if text == "" {
		log.Println("Could not retrieve notice text.")
		notices = []NoticeItem{{
			Title:       "Notice Status",
			Category:    "General",
			Notice:      "<p>No daily notices currently available.</p>",
			TargetYears: []string{"All"},
			Importance:  "normal",
			Contact:     "System",
		}}
	} else {
		notices = parseNoticesText(text)

		if len(notices) == 0 {
			log.Println("Text extracted but no notices parsed — check PDF structure.")
		}
	}

	// Normalize all notices!
	for i := range notices {
		notices[i] = normalizeNoticeItem(notices[i])
	}

	// Wrap with fetchedAt timestamp
	wrapper := NoticesFile{
		FetchedAt: time.Now().Format(time.RFC3339),
		Notices:   notices,
	}

	fileData, err := json.MarshalIndent(wrapper, "", "  ")
	if err != nil {
		return fmt.Errorf("error marshalling notices: %v", err)
	}

	err = os.WriteFile(outFile, fileData, 0644)
	if err != nil {
		return fmt.Errorf("error writing notices file: %v", err)
	}

	log.Printf("Saved %d notices to %s", len(notices), outFile)
	return nil
}

func fetchLatestPDFURL() (string, error) {
	client := &http.Client{Timeout: 10 * 1000 * 1000 * 1000} // 10s
	req, err := http.NewRequest("GET", noticesURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("non-200 status code: %d", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return "", err
	}

	href, exists := doc.Find("div.document.pdf a").First().Attr("href")
	if !exists {
		return "", nil
	}

	return "https://www.kingshigh.school.nz" + href, nil
}

func downloadAndExtractText(pdfURL string) (string, error) {
	client := &http.Client{Timeout: 15 * 1000 * 1000 * 1000} // 15s
	req, err := http.NewRequest("GET", pdfURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0")

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("non-200 status code: %d", resp.StatusCode)
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	// Use pdf package
	reader, err := pdf.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return "", err
	}

	var textBuilder strings.Builder
	numPages := reader.NumPage()
	for i := 1; i <= numPages; i++ {
		page := reader.Page(i)
		if page.V.IsNull() {
			continue
		}
		textBuilder.WriteString(extractPageLines(page))
	}

	return textBuilder.String(), nil
}

// extractPageLines rebuilds real text lines from a PDF page.
//
// GetPlainText emits every text span on its own line ("King", "’", "s High
// School"), which destroys the line structure the notice parser depends on.
// Grouping spans by row and joining them in reading order restores it.
func extractPageLines(page pdf.Page) string {
	rows, err := page.GetTextByRow()
	if err != nil || len(rows) == 0 {
		// Fall back to the fragmented extraction rather than losing the page.
		content, err := page.GetPlainText(nil)
		if err != nil {
			return ""
		}
		return content + "\n"
	}

	// PDF Y coordinates increase bottom-to-top, so descending Y is reading order.
	sort.SliceStable(rows, func(a, b int) bool { return rows[a].Position > rows[b].Position })

	var sb strings.Builder
	for _, row := range rows {
		spans := append(pdf.TextHorizontal{}, row.Content...)
		sort.SliceStable(spans, func(a, b int) bool { return spans[a].X < spans[b].X })

		var line strings.Builder
		for _, span := range spans {
			line.WriteString(span.S)
		}

		// Spans carry their own spacing, so only collapse runs of whitespace.
		if collapsed := strings.Join(strings.Fields(line.String()), " "); collapsed != "" {
			sb.WriteString(collapsed)
			sb.WriteString("\n")
		}
	}
	return sb.String()
}

// Audience section headers in the PDF, e.g. "All/Te Katoa", "Senior/Tuakana".
var audienceSections = map[string][]string{
	"all":    {"All"},
	"senior": {"11", "12", "13"},
	"junior": {"9", "10"},
}

var (
	// A notice starts with a SHOUTY heading followed by a dash: "BREAKFAST CLUB – Free breakfast:"
	// \p{Lu} rather than A-Z so macronised Māori headings ("WHĀNAU") match too.
	headingRe = regexp.MustCompile(`^((?:\p{Lu}|[0-9&/\.\?' \(\)-])[\p{Lu}0-9&/\.\?' \(\)-]{2,60}?)\s*[-–—]\s*(.*)$`)
	// Masthead / bilingual title lines to drop.
	mastheadRe = regexp.MustCompile(`(?i)^(king.s high school|daily notices|panui|wenerei|rāapa|mane|turei|paraire|timetable day)\b`)
	// Bilingual audience header, e.g. "Senior/Tuakana".
	audienceRe = regexp.MustCompile(`^(All|Senior|Junior)\s*/\s*\S+`)
	bulletRe   = regexp.MustCompile(`^[•▪◦*]\s*`)
	dateLineRe = regexp.MustCompile(`(?i)^(mon|tues|wednes|thurs|fri|satur|sun)day\s+\d{1,2}`)
	// Day labels used as sub-items inside a notice ("THURSDAY - Violin, Clarinet"),
	// which are continuation lines rather than new notices.
	dayLabelRe = regexp.MustCompile(`^(TODAY|TOMORROW|YESTERDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY|EVERYDAY|EVERY DAY|THIS WEEK|NEXT WEEK)$`)
)

// parsedNotice is an in-progress notice being accumulated across lines.
// Blocks are kept in document order so paragraphs and lists render as written.
type parsedNotice struct {
	heading  string
	audience []string
	blocks   []noticeBlock
}

type noticeBlock struct {
	isBullet bool
	text     string
}

// last returns a pointer to the most recent block, or nil when empty.
func (p *parsedNotice) last() *noticeBlock {
	if len(p.blocks) == 0 {
		return nil
	}
	return &p.blocks[len(p.blocks)-1]
}

func (p *parsedNotice) addParagraph(text string) {
	if text != "" {
		p.blocks = append(p.blocks, noticeBlock{text: text})
	}
}

func (p *parsedNotice) addBullet(text string) {
	if text != "" {
		p.blocks = append(p.blocks, noticeBlock{isBullet: true, text: text})
	}
}

// parseNoticesText turns extracted PDF lines into individual notices.
//
// The PDF has a simple, stable shape: optional audience section headers
// ("All/Te Katoa", "Senior/Tuakana", "Junior/Teina"), then one notice per
// SHOUTY heading followed by a dash, with wrapped continuation lines and
// occasional "•" bullets.
func parseNoticesText(rawText string) []NoticeItem {
	var (
		notices  []NoticeItem
		current  *parsedNotice
		audience = []string{"All"}
	)

	flush := func() {
		if current == nil {
			return
		}
		if item, ok := current.toNoticeItem(); ok {
			notices = append(notices, item)
		}
		current = nil
	}

	for _, raw := range strings.Split(rawText, "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || len(line) < 3 {
			continue
		}

		// Audience section header — applies to every notice that follows.
		if m := audienceRe.FindStringSubmatch(line); m != nil {
			flush()
			if years, ok := audienceSections[strings.ToLower(m[1])]; ok {
				audience = years
			}
			continue
		}

		// Masthead, bilingual titles and the standalone date line.
		if mastheadRe.MatchString(line) || dateLineRe.MatchString(line) {
			continue
		}

		// Bullet line — belongs to the notice currently being built.
		if bulletRe.MatchString(line) {
			if current != nil {
				current.addBullet(bulletRe.ReplaceAllString(line, ""))
			}
			continue
		}

		// New notice heading.
		if m := headingRe.FindStringSubmatch(line); m != nil && isShoutyHeading(m[1]) {
			heading := strings.TrimSpace(m[1])
			// "THURSDAY - Violin, Clarinet" is a sub-item of the notice above it,
			// not a notice of its own.
			if current != nil && dayLabelRe.MatchString(heading) {
				current.appendSubItem(heading, strings.TrimSpace(m[2]))
				continue
			}
			flush()
			current = &parsedNotice{heading: heading, audience: audience}
			current.addParagraph(strings.TrimSpace(m[2]))
			continue
		}

		// Continuation of the current notice body.
		if current != nil {
			current.appendContinuation(line)
		}
	}
	flush()

	return notices
}

// isShoutyHeading reports whether s looks like a notice heading rather than a
// mid-sentence dash. Headings are upper-case, so require most letters to be
// capitals and reject anything with lower-case words.
func isShoutyHeading(s string) bool {
	letters, upper := 0, 0
	for _, r := range s {
		if unicode.IsLetter(r) {
			letters++
			if unicode.IsUpper(r) {
				upper++
			}
		}
	}
	if letters < 3 {
		return false
	}
	return float64(upper)/float64(letters) >= 0.85
}

// appendSubItem records a day-labelled sub-item ("THURSDAY - Violin, Clarinet")
// as a bullet under the notice currently being built.
func (p *parsedNotice) appendSubItem(label, body string) {
	p.addBullet(label + " — " + body)
}

// appendContinuation adds a wrapped line to the notice body, merging it into
// the previous block unless that block already ended a sentence.
func (p *parsedNotice) appendContinuation(line string) {
	prev := p.last()
	if prev == nil || endsSentence(prev.text) {
		p.addParagraph(line)
		return
	}
	prev.text += " " + line
}

// endsSentence reports whether s ends with terminal punctuation, marking a safe
// place to start a new block rather than continuing a wrapped line.
func endsSentence(s string) bool {
	s = strings.TrimSpace(s)
	return strings.HasSuffix(s, ".") || strings.HasSuffix(s, "!") || strings.HasSuffix(s, "?")
}

// toNoticeItem renders the accumulated notice as HTML. All PDF-derived text is
// HTML-escaped: it is third-party content and must never be treated as markup.
func (p *parsedNotice) toNoticeItem() (NoticeItem, bool) {
	var body strings.Builder
	inList := false

	for _, block := range p.blocks {
		text := strings.TrimSpace(block.text)
		if text == "" {
			continue
		}
		if block.isBullet {
			if !inList {
				body.WriteString("<ul>")
				inList = true
			}
			body.WriteString("<li>" + html.EscapeString(text) + "</li>")
			continue
		}
		if inList {
			body.WriteString("</ul>")
			inList = false
		}
		body.WriteString("<p>" + html.EscapeString(text) + "</p>")
	}
	if inList {
		body.WriteString("</ul>")
	}

	if body.Len() == 0 {
		return NoticeItem{}, false
	}

	return NoticeItem{
		Title:       titleCase(p.heading),
		Category:    "", // filled in by normalizeNoticeItem
		Notice:      body.String(),
		TargetYears: p.audience,
		Contact:     "",
	}, true
}

// titleCase converts a SHOUTY PDF heading into a readable title, capitalising
// after separators ("CHOIR/POLYHYMNIA" → "Choir/Polyhymnia") and restoring
// acronyms that title-casing would otherwise flatten.
func titleCase(s string) string {
	var out []rune
	capitalise := true
	for _, r := range strings.ToLower(s) {
		if capitalise && unicode.IsLetter(r) {
			out = append(out, unicode.ToUpper(r))
			capitalise = false
			continue
		}
		if r == ' ' || r == '/' || r == '(' || r == '-' || r == '&' {
			capitalise = true
		}
		out = append(out, r)
	}
	result := string(out)
	for _, acronym := range []string{"Pac", "Ccrf", "Op", "Nz", "Bot", "Nzqa", "Ncea"} {
		result = regexp.MustCompile(`\b`+acronym+`\b`).ReplaceAllString(result, strings.ToUpper(acronym))
	}
	return result
}

// emojiRe matches Unicode emoji sequences (broad coverage)
var emojiRe = regexp.MustCompile(`[\x{1F000}-\x{1FFFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{FE00}-\x{FEFF}\x{1F900}-\x{1F9FF}]`)

func stripEmoji(s string) string {
	return strings.TrimSpace(emojiRe.ReplaceAllString(s, ""))
}

func normalizeNoticeItem(item NoticeItem) NoticeItem {
	// Strip emojis from text fields
	item.Title = stripEmoji(item.Title)
	item.Contact = stripEmoji(item.Contact)
	item.Notice = emojiRe.ReplaceAllString(item.Notice, "")

	// Normalize Category
	item.Category = strings.TrimSpace(item.Category)
	validCategories := map[string]bool{
		"General": true, "Meetings": true, "Sports": true, "Arts & Culture": true,
		"Academic": true, "Careers": true, "Service": true,
	}
	if item.Category == "" || !validCategories[item.Category] {
		item.Category = getStandardCategory(item.Title, item.Notice)
	}

	// Normalize Title
	item.Title = strings.TrimSpace(item.Title)
	if item.Title == "" {
		words := strings.Fields(regexp.MustCompile("<[^>]*>").ReplaceAllString(item.Notice, ""))
		if len(words) > 0 {
			limit := 5
			if len(words) < 5 {
				limit = len(words)
			}
			item.Title = strings.Join(words[:limit], " ") + "..."
		} else {
			item.Title = item.Category + " Notice"
		}
	}

	// Normalize Importance
	item.Importance = strings.ToLower(strings.TrimSpace(item.Importance))
	if item.Importance != "high" && item.Importance != "normal" {
		item.Importance = detectImportance(item.Title, item.Notice)
	}

	// Normalize TargetYears
	if len(item.TargetYears) == 0 {
		item.TargetYears = extractTargetYears(item.Title + " " + item.Notice)
	} else {
		var cleanYears []string
		for _, y := range item.TargetYears {
			y = strings.TrimSpace(y)
			if strings.ToLower(y) == "all" {
				cleanYears = []string{"All"}
				break
			}
			digitRe := regexp.MustCompile(`\d+`)
			digit := digitRe.FindString(y)
			if digit != "" {
				cleanYears = append(cleanYears, digit)
			}
		}
		if len(cleanYears) == 0 {
			cleanYears = []string{"All"}
		}
		item.TargetYears = cleanYears
	}

	// Normalize Contact
	item.Contact = strings.TrimSpace(item.Contact)
	if item.Contact == "" {
		item.Contact = extractContact(item.Notice)
	}

	// Format notice HTML if raw
	item.Notice = formatNoticeHTML(item.Notice)

	return item
}

func getStandardCategory(title string, text string) string {
	t := strings.ToLower(title + " " + text)
	if strings.Contains(t, "sport") || strings.Contains(t, "rugby") || strings.Contains(t, "football") || strings.Contains(t, "soccer") || strings.Contains(t, "cricket") || strings.Contains(t, "hockey") || strings.Contains(t, "basketball") || strings.Contains(t, "netball") || strings.Contains(t, "athletics") || strings.Contains(t, "tennis") || strings.Contains(t, "badminton") || strings.Contains(t, "swimming") || strings.Contains(t, "rowing") {
		return "Sports"
	}
	if strings.Contains(t, "meeting") || strings.Contains(t, "committee") || strings.Contains(t, "council") || strings.Contains(t, "practice") || strings.Contains(t, " rehearsal") || strings.Contains(t, "club") || strings.Contains(t, "group") {
		if strings.Contains(t, "choir") || strings.Contains(t, "band") || strings.Contains(t, "music") || strings.Contains(t, "drama") || strings.Contains(t, "play") || strings.Contains(t, "art") || strings.Contains(t, "culture") {
			return "Arts & Culture"
		}
		return "Meetings"
	}
	if strings.Contains(t, "choir") || strings.Contains(t, "band") || strings.Contains(t, "music") || strings.Contains(t, "drama") || strings.Contains(t, "play") || strings.Contains(t, "art") || strings.Contains(t, "cultural") || strings.Contains(t, "dance") || strings.Contains(t, "debating") || strings.Contains(t, "speech") {
		return "Arts & Culture"
	}
	if strings.Contains(t, "career") || strings.Contains(t, "university") || strings.Contains(t, "job") || strings.Contains(t, "work") || strings.Contains(t, "employment") || strings.Contains(t, "polytech") || strings.Contains(t, "scholarship") || strings.Contains(t, "tertiary") {
		return "Careers"
	}
	if strings.Contains(t, "service") || strings.Contains(t, "charity") || strings.Contains(t, "volunteer") || strings.Contains(t, "community") || strings.Contains(t, "fundrais") || strings.Contains(t, "donation") || strings.Contains(t, "foodbank") {
		return "Service"
	}
	if strings.Contains(t, "class") || strings.Contains(t, "exam") || strings.Contains(t, "test") || strings.Contains(t, "study") || strings.Contains(t, "academic") || strings.Contains(t, "math") || strings.Contains(t, "english") || strings.Contains(t, "science") || strings.Contains(t, "history") || strings.Contains(t, "geography") || strings.Contains(t, "library") || strings.Contains(t, "homework") || strings.Contains(t, "detention") {
		return "Academic"
	}
	return "General"
}

func extractTargetYears(text string) []string {
	var years []string
	lowerText := strings.ToLower(text)

	addYear := func(y string) {
		for _, existing := range years {
			if existing == y {
				return
			}
		}
		years = append(years, y)
	}

	hasJunior := strings.Contains(lowerText, "junior")
	hasSenior := strings.Contains(lowerText, "senior")

	year9Re := regexp.MustCompile(`\b(year|yr|y)\s*9\b`)
	year10Re := regexp.MustCompile(`\b(year|yr|y)\s*10\b`)
	year11Re := regexp.MustCompile(`\b(year|yr|y)\s*11\b`)
	year12Re := regexp.MustCompile(`\b(year|yr|y)\s*12\b`)
	year13Re := regexp.MustCompile(`\b(year|yr|y)\s*13\b`)

	if year9Re.MatchString(lowerText) {
		addYear("9")
	}
	if year10Re.MatchString(lowerText) {
		addYear("10")
	}
	if year11Re.MatchString(lowerText) {
		addYear("11")
	}
	if year12Re.MatchString(lowerText) {
		addYear("12")
	}
	if year13Re.MatchString(lowerText) {
		addYear("13")
	}

	if hasJunior {
		addYear("9")
		addYear("10")
	}
	if hasSenior {
		addYear("11")
		addYear("12")
		addYear("13")
	}

	if len(years) == 0 {
		return []string{"All"}
	}
	return years
}

func extractContact(text string) string {
	contactRe := regexp.MustCompile(`\b(Mr|Mrs|Ms|Miss|Dr|Teacher)\s+([A-Z][a-zA-Z]+)`)
	match := contactRe.FindStringSubmatch(text)
	if len(match) > 0 {
		return match[0]
	}
	return ""
}

func detectImportance(title string, text string) string {
	t := strings.ToLower(title + " " + text)
	if strings.Contains(t, "urgent") || strings.Contains(t, "important") || strings.Contains(t, "attention") || strings.Contains(t, "room change") || strings.Contains(t, "timetable change") || strings.Contains(t, "cancelled") || strings.Contains(t, "postponed") || strings.Contains(t, "alert") || strings.Contains(t, "warning") {
		return "high"
	}
	return "normal"
}

func formatNoticeHTML(text string) string {
	if strings.Contains(text, "<p>") || strings.Contains(text, "<ul>") || strings.Contains(text, "<li>") || strings.Contains(text, "<table>") {
		return text
	}

	lines := strings.Split(text, "\n")
	var htmlParts []string
	inList := false

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}

		if strings.HasPrefix(line, "*") || strings.HasPrefix(line, "-") || strings.HasPrefix(line, "•") {
			if !inList {
				htmlParts = append(htmlParts, "<ul>")
				inList = true
			}
			content := strings.TrimSpace(line[1:])
			htmlParts = append(htmlParts, "<li>"+content+"</li>")
		} else {
			if inList {
				htmlParts = append(htmlParts, "</ul>")
				inList = false
			}
			htmlParts = append(htmlParts, "<p>"+line+"</p>")
		}
	}

	if inList {
		htmlParts = append(htmlParts, "</ul>")
	}

	if len(htmlParts) == 0 {
		return "<p>" + text + "</p>"
	}

	return strings.Join(htmlParts, "")
}
