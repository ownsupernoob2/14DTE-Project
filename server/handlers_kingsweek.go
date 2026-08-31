package main

import (
	"encoding/json"
	"fmt"
	"html"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/labstack/echo/v4"
)

// King's Week is published weekly as a Hail publication. Two pages are involved:
//
//   1. The school's own page lists every edition as a slider of covers. It is
//      plain server-rendered HTML, so goquery can read it.
//   2. Each edition lives on hail.to, which is a Vue app — the rendered HTML
//      contains no articles at all. The data is in an inline script as
//      `window.HAIL.articles = [...]`, so that JSON is pulled out directly
//      instead of trying to parse the page.
const (
	kingsWeekPageURL = "https://www.kingshigh.school.nz/whats-on/kings-week/"
	kingsWeekOutFile = "data/kings_week.json"

	// The school page carries every edition ever published (40+). Only a
	// handful are of any use on a mirror.
	kingsWeekMaxEditions = 12

	// Long enough for a plain-text article body to be worth reading in a modal,
	// short enough that one runaway page can't bloat the cache file.
	kingsWeekMaxBody = 4000

	kingsWeekUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
		"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

// KingsWeekEdition is one weekly issue as advertised on the school's page.
type KingsWeekEdition struct {
	ImageURL string `json:"imageUrl"`
	Title    string `json:"title"`
	Edition  string `json:"edition"`
	Date     string `json:"date"`
	Link     string `json:"link"`
}

// KingsWeekArticle is one story inside an edition. Body is plain text: the
// mirror renders into a QLabel, and the web app has no King's Week view.
type KingsWeekArticle struct {
	ID       string   `json:"id"`
	Title    string   `json:"title"`
	Summary  string   `json:"summary"`
	Body     string   `json:"body"`
	Author   string   `json:"author"`
	Date     string   `json:"date"`
	Link     string   `json:"link"`
	ImageURL string   `json:"imageUrl"`      // card-sized
	LargeURL string   `json:"largeImageUrl"` // modal-sized
	Images   []string `json:"images"`
}

// KingsWeekItem is the latest edition, the stories inside it, and the back
// catalogue. KingsWeekEdition is embedded so the original single-cover payload
// (title / edition / date / imageUrl / link at the top level) still parses.
type KingsWeekItem struct {
	KingsWeekEdition
	Articles  []KingsWeekArticle `json:"articles"`
	Editions  []KingsWeekEdition `json:"editions"`
	FetchedAt string             `json:"fetchedAt"`
}

var (
	kingsWeekCache KingsWeekItem
	kingsWeekMutex sync.RWMutex
)

// init loads any cached Kings Week data on startup, so a mirror booting before
// the first scrape completes still has something to show.
func init() {
	data, err := os.ReadFile(kingsWeekOutFile)
	if err == nil {
		var item KingsWeekItem
		if json.Unmarshal(data, &item) == nil {
			kingsWeekMutex.Lock()
			kingsWeekCache = item
			kingsWeekMutex.Unlock()
		}
	}
}

// StartKingsWeekFetcher runs a background loop to scrape Kings Week data.
func StartKingsWeekFetcher() {
	go func() {
		for {
			log.Println("[kings-week] Fetching latest issue...")
			if err := fetchKingsWeekLogic(); err != nil {
				log.Printf("[kings-week] Fetch failed: %v\n", err)
			}
			time.Sleep(1 * time.Hour)
		}
	}()
}

// ─────────────────────────────────────────────────────────────────────────────
// Fetching
// ─────────────────────────────────────────────────────────────────────────────

func fetchKingsWeekPage(url string) ([]byte, error) {
	client := &http.Client{Timeout: 20 * time.Second}
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	// Both hosts serve a different (or no) page to an unrecognised agent.
	req.Header.Set("User-Agent", kingsWeekUserAgent)

	res, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()

	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET %s: %s", url, res.Status)
	}
	// Cap the read: an unexpectedly huge page shouldn't be able to exhaust memory.
	return io.ReadAll(io.LimitReader(res.Body, 8<<20))
}

func fetchKingsWeekLogic() error {
	page, err := fetchKingsWeekPage(kingsWeekPageURL)
	if err != nil {
		return err
	}

	editions, err := parseKingsWeekEditions(strings.NewReader(string(page)))
	if err != nil {
		return err
	}
	if len(editions) == 0 {
		return fmt.Errorf("no King's Week editions found on %s", kingsWeekPageURL)
	}

	item := KingsWeekItem{
		KingsWeekEdition: editions[0],
		Editions:         editions,
		FetchedAt:        time.Now().Format(time.RFC3339),
	}

	// The edition list is the useful half; if hail.to is down we still publish it.
	if item.Link != "" {
		pub, err := fetchKingsWeekPage(item.Link)
		if err != nil {
			log.Printf("[kings-week] Could not read %s: %v\n", item.Link, err)
		} else {
			articles, err := parseHailArticles(string(pub))
			if err != nil {
				log.Printf("[kings-week] Could not parse articles: %v\n", err)
			} else {
				item.Articles = articles
			}
		}
	}

	// Keep whatever articles we already had rather than replacing a good grid
	// with an empty one because hail.to happened to be unreachable this hour.
	kingsWeekMutex.Lock()
	if len(item.Articles) == 0 && kingsWeekCache.Link == item.Link {
		item.Articles = kingsWeekCache.Articles
	}
	kingsWeekCache = item
	kingsWeekMutex.Unlock()

	if data, err := json.MarshalIndent(item, "", "  "); err == nil {
		_ = os.WriteFile(kingsWeekOutFile, data, 0644)
		log.Printf("[kings-week] Updated: %q, %d editions, %d articles\n",
			item.Title, len(item.Editions), len(item.Articles))
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────────────────
// The school's edition slider
// ─────────────────────────────────────────────────────────────────────────────

var kingsWeekBannerRe = regexp.MustCompile(`url\(\s*['"]?(.*?)['"]?\s*\)`)

// parseKingsWeekEditions reads the covers out of the school's King's Week page.
// The slides are already newest-first, and that order is preserved.
func parseKingsWeekEditions(r io.Reader) ([]KingsWeekEdition, error) {
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}

	var editions []KingsWeekEdition
	doc.Find("li.article.slide").EachWithBreak(func(_ int, slide *goquery.Selection) bool {
		ed := parseKingsWeekSlide(slide)
		if ed.Link != "" || ed.Title != "" {
			editions = append(editions, ed)
		}
		return len(editions) < kingsWeekMaxEditions
	})
	return editions, nil
}

func parseKingsWeekSlide(slide *goquery.Selection) KingsWeekEdition {
	var ed KingsWeekEdition

	if style, ok := slide.Find(".banner").Attr("style"); ok {
		if m := kingsWeekBannerRe.FindStringSubmatch(style); len(m) > 1 {
			ed.ImageURL = strings.TrimSpace(m[1])
		}
	}

	h3 := slide.Find("h3").First()
	sub := h3.Find(".sub").Text()

	// The heading holds both strings ("King's Week #1338 Up" + the real title),
	// so the sub-heading has to be cut out of the combined text.
	title := h3.Text()
	if sub != "" {
		title = strings.Replace(title, sub, "", 1)
	}
	ed.Title = collapseSpaces(title)

	// "Up" is the slider's own up-next marker, not part of the edition name.
	ed.Edition = collapseSpaces(strings.TrimSuffix(collapseSpaces(sub), "Up"))

	ed.Date = collapseSpaces(slide.Find(".date").First().Text())
	ed.Link = strings.TrimSpace(slide.Find("a").First().AttrOr("href", ""))
	return ed
}

// ─────────────────────────────────────────────────────────────────────────────
// hail.to's embedded article JSON
// ─────────────────────────────────────────────────────────────────────────────

// flexInt accepts a number or a numeric string, and treats anything else as 0.
// Hail's ordering field is not part of a documented API, so a type change there
// must not throw away the whole publication.
type flexInt int

func (f *flexInt) UnmarshalJSON(b []byte) error {
	s := strings.Trim(strings.TrimSpace(string(b)), `"`)
	if s == "" || s == "null" {
		return nil
	}
	if n, err := strconv.Atoi(s); err == nil {
		*f = flexInt(n)
	}
	return nil
}

type hailImage struct {
	Caption     string `json:"caption"`
	File500URL  string `json:"file_500_url"`
	File1000URL string `json:"file_1000_url"`
	File2000URL string `json:"file_2000_url"`
}

// card returns the smallest usable rendition, modal the largest.
func (h hailImage) card() string {
	return firstNonEmpty(h.File500URL, h.File1000URL, h.File2000URL)
}

func (h hailImage) modal() string {
	return firstNonEmpty(h.File1000URL, h.File2000URL, h.File500URL)
}

type hailArticle struct {
	ID        string      `json:"id"`
	Title     string      `json:"title"`
	Lead      *string     `json:"lead"`
	Body      string      `json:"body"`
	Author    *string     `json:"author"`
	Date      *string     `json:"date"`
	URL       string      `json:"url"`
	Status    string      `json:"status"`
	Order     flexInt     `json:"order"`
	HeroImage *hailImage  `json:"hero_image"`
	Images    []hailImage `json:"images"`
}

// parseHailArticles pulls window.HAIL.articles out of a publication page and
// flattens it into the shape the mirror needs.
func parseHailArticles(page string) ([]KingsWeekArticle, error) {
	raw, err := extractHailAssignment(page, "articles")
	if err != nil {
		return nil, err
	}

	var parsed []hailArticle
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		return nil, fmt.Errorf("decoding window.HAIL.articles: %w", err)
	}

	// Hail's own running order, with anything unnumbered left at the back in
	// the order the page listed it.
	sort.SliceStable(parsed, func(i, j int) bool {
		oi, oj := parsed[i].Order, parsed[j].Order
		if (oi == 0) != (oj == 0) {
			return oj == 0
		}
		return oi < oj
	})

	articles := make([]KingsWeekArticle, 0, len(parsed))
	for _, a := range parsed {
		if a.Status != "" && a.Status != "published" {
			continue
		}
		if a.Title == "" {
			continue
		}
		articles = append(articles, buildKingsWeekArticle(a))
	}
	return articles, nil
}

func buildKingsWeekArticle(a hailArticle) KingsWeekArticle {
	body := truncateWords(htmlToPlainText(a.Body), kingsWeekMaxBody)

	summary := collapseSpaces(htmlToPlainText(deref(a.Lead)))
	if summary == "" {
		summary = truncateWords(firstParagraph(body), 220)
	}

	out := KingsWeekArticle{
		ID:      a.ID,
		Title:   collapseSpaces(html.UnescapeString(a.Title)),
		Summary: summary,
		Body:    body,
		Author:  collapseSpaces(deref(a.Author)),
		Date:    formatHailDate(deref(a.Date)),
		Link:    a.URL,
	}

	if a.HeroImage != nil {
		out.ImageURL = a.HeroImage.card()
		out.LargeURL = a.HeroImage.modal()
	}
	for _, img := range a.Images {
		if u := img.modal(); u != "" {
			out.Images = append(out.Images, u)
		}
	}
	// Without a hero, the first inline image stands in as the card art.
	if out.ImageURL == "" && len(a.Images) > 0 {
		out.ImageURL = a.Images[0].card()
		out.LargeURL = a.Images[0].modal()
	}
	return out
}

// extractHailAssignment finds `window.HAIL.<key> = <value>;` and returns the
// value verbatim.
//
// A regex can't be trusted for this: the articles array is ~100 KB of JSON and
// article bodies contain "];" and "};" inside strings. The value is walked
// instead, counting brackets and skipping over string literals.
func extractHailAssignment(page, key string) (string, error) {
	needle := "window.HAIL." + key
	idx := strings.Index(page, needle)
	if idx < 0 {
		return "", fmt.Errorf("window.HAIL.%s not found", key)
	}

	i := idx + len(needle)
	for i < len(page) && (page[i] == ' ' || page[i] == '\t') {
		i++
	}
	if i >= len(page) || page[i] != '=' {
		return "", fmt.Errorf("window.HAIL.%s is not an assignment", key)
	}
	i++
	for i < len(page) && (page[i] == ' ' || page[i] == '\t' || page[i] == '\n' || page[i] == '\r') {
		i++
	}
	if i >= len(page) {
		return "", fmt.Errorf("window.HAIL.%s has no value", key)
	}

	open := page[i]
	var close byte
	switch open {
	case '[':
		close = ']'
	case '{':
		close = '}'
	default:
		return "", fmt.Errorf("window.HAIL.%s is not an array or object", key)
	}

	depth := 0
	inString := false
	escaped := false
	for j := i; j < len(page); j++ {
		c := page[j]
		if inString {
			switch {
			case escaped:
				escaped = false
			case c == '\\':
				escaped = true
			case c == '"':
				inString = false
			}
			continue
		}
		switch c {
		case '"':
			inString = true
		case open:
			depth++
		case close:
			depth--
			if depth == 0 {
				return page[i : j+1], nil
			}
		}
	}
	return "", fmt.Errorf("window.HAIL.%s is unterminated", key)
}

// ─────────────────────────────────────────────────────────────────────────────
// Text helpers
// ─────────────────────────────────────────────────────────────────────────────

var (
	kwBlockEndRe  = regexp.MustCompile(`(?i)</(p|div|h[1-6]|li|blockquote|tr)\s*>`)
	kwLineBreakRe = regexp.MustCompile(`(?i)<br\s*/?>`)
	kwTagRe       = regexp.MustCompile(`(?s)<[^>]*>`)
	kwSpaceRe     = regexp.MustCompile(`[ \t\f\v\x{00a0}]+`)
	kwBlankRe     = regexp.MustCompile(`\n{3,}`)
)

// htmlToPlainText flattens an article body, keeping paragraph breaks so the
// modal doesn't render as one wall of text.
func htmlToPlainText(s string) string {
	if s == "" {
		return ""
	}
	s = kwBlockEndRe.ReplaceAllString(s, "\n\n")
	s = kwLineBreakRe.ReplaceAllString(s, "\n")
	s = kwTagRe.ReplaceAllString(s, "")
	s = html.UnescapeString(s)
	s = strings.ReplaceAll(s, "\r\n", "\n")
	s = strings.ReplaceAll(s, "\r", "\n")

	lines := strings.Split(s, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimSpace(kwSpaceRe.ReplaceAllString(line, " "))
	}
	s = strings.Join(lines, "\n")
	return strings.TrimSpace(kwBlankRe.ReplaceAllString(s, "\n\n"))
}

func collapseSpaces(s string) string {
	s = html.UnescapeString(s)
	s = strings.ReplaceAll(s, "\n", " ")
	s = strings.ReplaceAll(s, "\r", " ")
	return strings.TrimSpace(kwSpaceRe.ReplaceAllString(s, " "))
}

func firstParagraph(s string) string {
	if i := strings.Index(s, "\n\n"); i > 0 {
		return s[:i]
	}
	return s
}

// truncateWords clips to a whole word and marks the cut, so a card summary
// never ends mid-word.
func truncateWords(s string, max int) string {
	if max <= 0 || len(s) <= max {
		return s
	}
	cut := s[:max]
	if i := strings.LastIndexAny(cut, " \n"); i > max/2 {
		cut = cut[:i]
	}
	return strings.TrimRight(cut, " \n.,;:") + "…"
}

// formatHailDate turns "2026-08-17 23:34:01" into "17 Aug 2026", leaving
// anything it doesn't recognise alone.
func formatHailDate(s string) string {
	s = strings.TrimSpace(s)
	if s == "" {
		return ""
	}
	for _, layout := range []string{"2006-01-02 15:04:05", "2006-01-02T15:04:05Z07:00", "2006-01-02"} {
		if t, err := time.Parse(layout, s); err == nil {
			return t.Format("2 Jan 2006")
		}
	}
	return s
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

// ─────────────────────────────────────────────────────────────────────────────
// GET /api/kings-week
// ─────────────────────────────────────────────────────────────────────────────
func getKingsWeek(c echo.Context) error {
	kingsWeekMutex.RLock()
	defer kingsWeekMutex.RUnlock()
	return c.JSON(http.StatusOK, kingsWeekCache)
}
