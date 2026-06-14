package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

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

	var notices interface{}
	if err := json.Unmarshal(data, &notices); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to parse notices"})
	}
	return c.JSON(200, notices)
}

func fetchNotices(c echo.Context) error {
	err := fetchNoticesLogic()
	if err != nil {
		return c.JSON(500, map[string]string{"error": err.Error()})
	}
	return c.JSON(200, map[string]string{"message": "Notices fetched successfully"})
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
		log.Println("Processing text with Gemini...")
		notices = processWithGemini(text)

		if len(notices) == 0 {
			log.Println("Falling back to text cleanup...")
			notices = cleanMessyText(text)
		}
	}

	// Normalize all notices!
	for i := range notices {
		notices[i] = normalizeNoticeItem(notices[i])
	}

	fileData, err := json.MarshalIndent(notices, "", "  ")
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
		content, err := page.GetPlainText(nil)
		if err == nil {
			textBuilder.WriteString(content)
			textBuilder.WriteString("\n")
		}
	}

	return textBuilder.String(), nil
}

func cleanMessyText(rawText string) []NoticeItem {
	lines := strings.Split(rawText, "\n")
	var cleanedLines []string

	spaceRe := regexp.MustCompile(`\s{2,}`)
	for _, line := range lines {
		line = strings.TrimSpace(line)
		line = spaceRe.ReplaceAllString(line, " ")
		if len(line) > 2 {
			cleanedLines = append(cleanedLines, line)
		}
	}

	var notices []NoticeItem
	currentCategory := "General"
	var currentNotice []string

	// Check for Category - Notice text
	noticeRe := regexp.MustCompile(`^([A-Z0-9\s/&,]+?)\s*[-–—]\s*(.+)$`)
	dateRe := regexp.MustCompile(`^(?i)(mon|tue|wed|thu|fri|sat|sun)\w*\s+\d+`)

	dayWords := map[string]bool{
		"TODAY": true, "MONDAY": true, "TUESDAY": true, "WEDNESDAY": true,
		"THURSDAY": true, "FRIDAY": true, "SATURDAY": true, "SUNDAY": true,
		"EVERYDAY": true, "TOMORROW": true,
	}

	for _, line := range cleanedLines {
		upperLine := strings.ToUpper(line)
		if strings.Contains(upperLine, "DAILY NOTICE") {
			continue
		}

		match := noticeRe.FindStringSubmatch(line)
		if len(match) > 0 {
			potentialCategory := strings.TrimSpace(match[1])
			noticeBody := strings.TrimSpace(match[2])

			if dayWords[strings.ToUpper(potentialCategory)] {
				currentNotice = append(currentNotice, fmt.Sprintf("%s - %s", potentialCategory, noticeBody))
			} else {
				if len(currentNotice) > 0 {
					notices = append(notices, NoticeItem{
						Title:    currentCategory,
						Category: currentCategory,
						Notice:   "<p>" + strings.Join(currentNotice, "</p><p>") + "</p>",
					})
				}
				currentCategory = potentialCategory
				currentNotice = []string{noticeBody}
			}
		} else {
			if len(line) < 40 && len(currentNotice) == 0 && dateRe.MatchString(line) {
				continue
			}
			currentNotice = append(currentNotice, line)
		}
	}

	if len(currentNotice) > 0 {
		notices = append(notices, NoticeItem{
			Title:    currentCategory,
			Category: currentCategory,
			Notice:   "<p>" + strings.Join(currentNotice, "</p><p>") + "</p>",
		})
	}

	if len(notices) == 0 && len(cleanedLines) > 0 {
		var htmlParts []string
		for _, line := range cleanedLines {
			htmlParts = append(htmlParts, "<p>"+line+"</p>")
		}
		notices = []NoticeItem{{Title: "Daily Notice", Category: "General", Notice: strings.Join(htmlParts, "")}}
	}

	return notices
}

type geminiRequest struct {
	Contents []geminiContent `json:"contents"`
}

type geminiContent struct {
	Parts []geminiPart `json:"parts"`
}

type geminiPart struct {
	Text string `json:"text"`
}

type geminiResponse struct {
	Candidates []struct {
		Content struct {
			Parts []struct {
				Text string `json:"text"`
			} `json:"parts"`
		} `json:"content"`
	} `json:"candidates"`
}

func processWithGemini(text string) []NoticeItem {
	apiKey := os.Getenv("GEMINI_API_KEY")
	if apiKey == "" {
		apiKey = "AQ.Ab8RN6JhAURgT__2fy2PxQq3xN1CQujfdFqnOHf8Fbpm2PTdCw"
	}

	url := "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + apiKey

	prompt := `You are an expert school notices parsing assistant.
Analyze the following daily school notices and extract them into a clean JSON array of notice objects.

Strict JSON format requirements:
Each notice object in the array must have EXACTLY these fields:
- "title": A clean, concise headline summarizing the notice (e.g. "Year 12 Geography Field Trip").
- "category": Must be exactly one of: "General", "Meetings", "Sports", "Arts & Culture", "Academic", "Careers", "Service". Choose the most appropriate category based on the content.
- "notice": The body of the notice formatted as clean, well-spaced HTML. Use <p> for paragraphs and <ul><li> for lists. Bold critical details like Date, Time, Location, Cost, and Deadlines using <strong>. Correct any OCR/spelling/spacing errors (e.g., replace "King?s" with "King's", "min utes" with "minutes"). Write complete, readable sentences.
- "targetYears": An array of strings representing the target school year levels, e.g. ["9", "10"], ["12"], or ["All"] if it applies to everyone or is not specified. Extract year level mentions like "Year 9", "Y10", "Juniors" (Year 9 and 10), "Seniors" (Year 11, 12, and 13).
- "importance": Either "high" (use for room changes, time-critical updates, urgent instructions, cancellations) or "normal" (general notices).
- "contact": The name of the teacher, facilitator, or staff member in charge of the event/notice if mentioned (e.g. "Mr Smith"), otherwise an empty string "".

CRITICAL RULES — you must follow these exactly:
- Do NOT use any emoji characters anywhere in any field. Use plain descriptive text only.
- Do NOT use bullet point symbols or dashes as list markers — use proper HTML <ul><li> tags.
- Do NOT start titles or notice bodies with symbols, dashes, or decorative characters.
- Only use these HTML tags: <p>, <ul>, <li>, <strong>. No other tags allowed.
- No markdown formatting (no **, no #, no -) in the notice field — HTML only.
- Respond with ONLY a valid JSON array. No explanation, no markdown code fences.

Text to process:
` + text

	reqBody := geminiRequest{
		Contents: []geminiContent{
			{
				Parts: []geminiPart{
					{Text: prompt},
				},
			},
		},
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return nil
	}

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		log.Printf("Gemini API error: %v", err)
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		log.Printf("Gemini API returned status %d", resp.StatusCode)
		return nil
	}

	var geminiResp geminiResponse
	if err := json.NewDecoder(resp.Body).Decode(&geminiResp); err != nil {
		return nil
	}

	if len(geminiResp.Candidates) == 0 || len(geminiResp.Candidates[0].Content.Parts) == 0 {
		return nil
	}

	respText := geminiResp.Candidates[0].Content.Parts[0].Text

	// Extract JSON — handle markdown fences or bare JSON array
	respText = strings.TrimSpace(respText)
	jsonRe := regexp.MustCompile("(?s)```(?:json)?\\s*(.*?)\\s*```")
	if matches := jsonRe.FindStringSubmatch(respText); len(matches) > 1 {
		respText = strings.TrimSpace(matches[1])
	}
	// Find the outermost JSON array
	arrStart := strings.Index(respText, "[")
	arrEnd := strings.LastIndex(respText, "]")
	if arrStart >= 0 && arrEnd > arrStart {
		respText = respText[arrStart : arrEnd+1]
	}

	var notices []NoticeItem
	if err := json.Unmarshal([]byte(respText), &notices); err != nil {
		log.Printf("Gemini JSON parse error: %v\nResponse was: %.500s", err, respText)
		return nil
	}

	return notices
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
