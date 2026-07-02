package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/labstack/echo/v4"
)

const kingsWeekURL = "https://hail.to/kings-high-school/article-gallery"
const kingsWeekOutFile = "data/kings_week.json"

type KingsWeekItem struct {
	ImageURL string `json:"imageUrl"`
	Title    string `json:"title"`
	Edition  string `json:"edition"`
	Date     string `json:"date"`
	Link     string `json:"link"`
}

var (
	kingsWeekCache KingsWeekItem
	kingsWeekMutex sync.RWMutex
)

// init loads any cached Kings Week data on startup
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

// StartKingsWeekFetcher runs a background loop to scrape Kings Week data
func StartKingsWeekFetcher() {
	go func() {
		for {
			log.Println("[kings-week] Fetching latest issue...")
			if err := fetchKingsWeekLogic(); err != nil {
				log.Printf("[kings-week] Fetch failed: %v\n", err)
			}
			
			// Sleep for 1 hour before checking again
			time.Sleep(1 * time.Hour)
		}
	}()
}

func fetchKingsWeekLogic() error {
	res, err := http.Get(kingsWeekURL)
	if err != nil {
		return err
	}
	defer res.Body.Close()

	if res.StatusCode != 200 {
		log.Printf("[kings-week] Status code error: %d %s\n", res.StatusCode, res.Status)
		return err
	}

	doc, err := goquery.NewDocumentFromReader(res.Body)
	if err != nil {
		return err
	}

	// Find the first slide which contains the most recent issue
	firstSlide := doc.Find("li.article.slide").First()

	var item KingsWeekItem

	// Extract Image URL
	style, _ := firstSlide.Find(".banner").Attr("style")
	urlRegex := regexp.MustCompile(`url\(\s*(.*?)\s*\)`)
	match := urlRegex.FindStringSubmatch(style)
	if len(match) > 1 {
		item.ImageURL = match[1]
	}

	// Extract Title & Edition
	h3 := firstSlide.Find("h3")
	sub := h3.Find(".sub").Text()
	item.Edition = strings.TrimSpace(sub)

	// Clean up title (remove the .sub text and "Up")
	title := h3.Text()
	title = strings.Replace(title, sub, "", 1)
	title = strings.TrimSpace(title)
	item.Title = title

	// Cleanup edition (sometimes contains "Up" at the end due to the DOM structure)
	item.Edition = strings.Replace(item.Edition, "Up", "", -1)
	item.Edition = strings.TrimSpace(item.Edition)

	// Extract Date
	item.Date = strings.TrimSpace(firstSlide.Find(".date").Text())

	// Extract Link
	href, _ := firstSlide.Find("a").Attr("href")
	item.Link = href

	// Update cache & save
	kingsWeekMutex.Lock()
	kingsWeekCache = item
	kingsWeekMutex.Unlock()

	data, err := json.MarshalIndent(item, "", "  ")
	if err == nil {
		_ = os.WriteFile(kingsWeekOutFile, data, 0644)
		log.Println("[kings-week] Successfully updated Kings Week cache")
	}

	return nil
}

// GET /api/kings-week
func getKingsWeek(c echo.Context) error {
	kingsWeekMutex.RLock()
	defer kingsWeekMutex.RUnlock()
	return c.JSON(http.StatusOK, kingsWeekCache)
}
