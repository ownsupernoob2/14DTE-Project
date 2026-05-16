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
	Category string `json:"category"`
	Notice   string `json:"notice"`
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
		notices = []NoticeItem{{Category: "System", Notice: "No daily notices currently available."}}
	} else {
		log.Println("Processing text with Gemini...")
		notices = processWithGemini(text)

		if len(notices) == 0 {
			log.Println("Falling back to text cleanup...")
			notices = cleanMessyText(text)
		}
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
						Category: currentCategory,
						Notice:   strings.Join(currentNotice, " "),
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
			Category: currentCategory,
			Notice:   strings.Join(currentNotice, " "),
		})
	}

	if len(notices) == 0 && len(cleanedLines) > 0 {
		notices = []NoticeItem{{Category: "General", Notice: strings.Join(cleanedLines, " ")}}
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
		return nil
	}

	url := "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + apiKey

	prompt := `Extract the following daily school notices into a neat JSON array.
Each object should have "category" and "notice".
Text:
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

	// Extract JSON from markdown
	jsonRe := regexp.MustCompile("(?s)```(?:json)?\\s*(.*?)\\s*```")
	matches := jsonRe.FindStringSubmatch(respText)
	if len(matches) > 1 {
		respText = matches[1]
	}

	var notices []NoticeItem
	if err := json.Unmarshal([]byte(respText), &notices); err != nil {
		log.Printf("Gemini JSON parse error: %v", err)
		return nil
	}

	return notices
}
