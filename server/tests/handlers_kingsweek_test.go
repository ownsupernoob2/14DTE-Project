package main

import (
	"strings"
	"testing"
)

// A trimmed copy of the school's King's Week slider. Whitespace, the "Up"
// marker and the escaped apostrophes are all reproduced from the real page,
// because those are exactly what the parser has to cope with.
const schoolSliderHTML = `
<html><body>
<h3 class="article_heading">King&#039;s Week</h3>
<div class="flexslider"><ul class="slides">
  <li class="article slide pos-1 first">
    <a href="https://hail.to/kings-high-school/publication/GkAuf2N" target="_blank">
      <div class="banner" style="background-image:url( https://assets.hail-cdn.com/uploads/1000-a8d58548.jpg )"></div>
      <h3>
        <span class="sub">King&#039;s Week #1338 Up</span>
        King&#039;s Week - 21 August 2026
      </h3>
      <div class="date">Friday, 21st August 2026</div>
    </a>
  </li>
  <li class="article slide pos-2">
    <a href="https://hail.to/kings-high-school/publication/OLDER01" target="_blank">
      <div class="banner" style="background-image:url('https://assets.hail-cdn.com/uploads/1000-b7.jpg')"></div>
      <h3><span class="sub">King&#039;s Week #1337</span> King&#039;s Week - 14 August 2026</h3>
      <div class="date">Friday, 14th August 2026</div>
    </a>
  </li>
</ul></div>
</body></html>`

func TestParseKingsWeekEditionsNewestFirst(t *testing.T) {
	editions, err := parseKingsWeekEditions(strings.NewReader(schoolSliderHTML))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(editions) != 2 {
		t.Fatalf("want 2 editions, got %d: %+v", len(editions), editions)
	}

	latest := editions[0]
	if latest.Title != "King's Week - 21 August 2026" {
		t.Errorf("title = %q", latest.Title)
	}
	// The sub-heading must lose the slider's "Up" marker but keep the number.
	if latest.Edition != "King's Week #1338" {
		t.Errorf("edition = %q", latest.Edition)
	}
	if latest.Date != "Friday, 21st August 2026" {
		t.Errorf("date = %q", latest.Date)
	}
	if latest.Link != "https://hail.to/kings-high-school/publication/GkAuf2N" {
		t.Errorf("link = %q", latest.Link)
	}
	if latest.ImageURL != "https://assets.hail-cdn.com/uploads/1000-a8d58548.jpg" {
		t.Errorf("imageUrl = %q", latest.ImageURL)
	}
	if editions[1].Edition != "King's Week #1337" {
		t.Errorf("second edition = %q", editions[1].Edition)
	}
}

func TestParseKingsWeekEditionsHandlesQuotedBannerURL(t *testing.T) {
	editions, _ := parseKingsWeekEditions(strings.NewReader(schoolSliderHTML))
	if got := editions[1].ImageURL; got != "https://assets.hail-cdn.com/uploads/1000-b7.jpg" {
		t.Errorf("quoted url = %q, want the bare URL", got)
	}
}

func TestParseKingsWeekEditionsCaps(t *testing.T) {
	var b strings.Builder
	b.WriteString("<ul class='slides'>")
	for i := 0; i < kingsWeekMaxEditions+8; i++ {
		b.WriteString(`<li class="article slide"><a href="https://hail.to/p/x"><h3>Ed</h3></a></li>`)
	}
	b.WriteString("</ul>")

	editions, err := parseKingsWeekEditions(strings.NewReader(b.String()))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(editions) != kingsWeekMaxEditions {
		t.Errorf("want the list capped at %d, got %d", kingsWeekMaxEditions, len(editions))
	}
}

func TestParseKingsWeekEditionsEmptyPage(t *testing.T) {
	editions, err := parseKingsWeekEditions(strings.NewReader("<html><body>nothing</body></html>"))
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if len(editions) != 0 {
		t.Errorf("want no editions, got %+v", editions)
	}
}

// ── window.HAIL extraction ──────────────────────────────────────────────────

func TestExtractHailAssignmentSkipsBracketsInsideStrings(t *testing.T) {
	// This is the whole reason for a bracket walker: a regex stopping at the
	// first "];" would truncate the array here.
	page := `<script type="text/javascript">
window.HAIL = {};
window.HAIL.articles = [{"body":"<p>see the list [1] here];</p>","id":"a1"}];
window.HAIL.publication = {"id":"GkAuf2N"};
</script>`

	raw, err := extractHailAssignment(page, "articles")
	if err != nil {
		t.Fatalf("extract: %v", err)
	}
	if !strings.HasPrefix(raw, "[{") || !strings.HasSuffix(raw, "}]") {
		t.Fatalf("value not bracket-balanced: %q", raw)
	}
	if !strings.Contains(raw, `"id":"a1"`) {
		t.Errorf("value was truncated: %q", raw)
	}
}

func TestExtractHailAssignmentHandlesEscapedQuotes(t *testing.T) {
	page := `window.HAIL.articles = [{"title":"He said \"hi\" }]","id":"a1"}];`
	raw, err := extractHailAssignment(page, "articles")
	if err != nil {
		t.Fatalf("extract: %v", err)
	}
	if !strings.Contains(raw, `"id":"a1"`) {
		t.Errorf("escaped quote ended the scan early: %q", raw)
	}
}

func TestExtractHailAssignmentObject(t *testing.T) {
	page := `window.HAIL.publication = {"id":"GkAuf2N","title":"King's Week"};`
	raw, err := extractHailAssignment(page, "publication")
	if err != nil {
		t.Fatalf("extract: %v", err)
	}
	if raw != `{"id":"GkAuf2N","title":"King's Week"}` {
		t.Errorf("raw = %q", raw)
	}
}

func TestExtractHailAssignmentErrors(t *testing.T) {
	cases := map[string]string{
		"missing key":  `window.HAIL.publication = {};`,
		"not assigned": `window.HAIL.articles.length`,
		"unterminated": `window.HAIL.articles = [{"id":"a1"}`,
		"not a literal": `window.HAIL.articles = buildArticles();`,
	}
	for name, page := range cases {
		if _, err := extractHailAssignment(page, "articles"); err == nil {
			t.Errorf("%s: want an error", name)
		}
	}
}

// ── Article mapping ─────────────────────────────────────────────────────────

const hailPageHTML = `<script type="text/javascript">
window.HAIL = {};
window.HAIL.articles = [
  {
    "id": "second",
    "order": 2,
    "status": "published",
    "title": "Welcome new Director of Sport",
    "lead": null,
    "author": "Ms Smith",
    "date": "2026-08-18 02:57:21",
    "url": "https://hail.to/kings-high-school/article/second",
    "body": "<p>First paragraph about the appointment.</p><p>Second paragraph &amp; more.</p>",
    "hero_image": {
      "file_500_url": "https://cdn/500-b.jpg",
      "file_1000_url": "https://cdn/1000-b.jpg",
      "file_2000_url": "https://cdn/2000-b.jpg"
    },
    "images": []
  },
  {
    "id": "first",
    "order": "1",
    "status": "published",
    "title": "Under 15 Cup Champions",
    "lead": "  A hard-fought <b>final</b>.  ",
    "author": null,
    "date": "2026-08-17 23:34:01",
    "url": "https://hail.to/kings-high-school/article/first",
    "body": "<p>Line one.<br>Line two.</p>",
    "hero_image": {
      "file_500_url": "https://cdn/500-a.jpg",
      "file_1000_url": "https://cdn/1000-a.jpg"
    },
    "images": [
      {"file_500_url": "https://cdn/500-g1.jpg", "file_1000_url": "https://cdn/1000-g1.jpg"},
      {"file_500_url": "https://cdn/500-g2.jpg"}
    ]
  },
  {
    "id": "draft",
    "order": 3,
    "status": "draft",
    "title": "Not ready yet",
    "body": "<p>Hidden.</p>",
    "hero_image": null,
    "images": []
  },
  {
    "id": "nohero",
    "order": 4,
    "status": "published",
    "title": "Choir sings",
    "body": "<p>Short one.</p>",
    "hero_image": null,
    "images": [{"file_500_url": "https://cdn/500-c.jpg", "file_1000_url": "https://cdn/1000-c.jpg"}]
  }
];
</script>`

func TestParseHailArticles(t *testing.T) {
	articles, err := parseHailArticles(hailPageHTML)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	// The draft must not reach a public display board.
	if len(articles) != 3 {
		t.Fatalf("want 3 published articles, got %d", len(articles))
	}

	// order 1 wins even though it appeared second in the array and as a string.
	if articles[0].ID != "first" {
		t.Errorf("first article = %q, want the one with order 1", articles[0].ID)
	}
	if articles[1].ID != "second" || articles[2].ID != "nohero" {
		t.Errorf("order = %q, %q", articles[1].ID, articles[2].ID)
	}

	first := articles[0]
	if first.Summary != "A hard-fought final." {
		t.Errorf("summary = %q, want the lead stripped of tags and padding", first.Summary)
	}
	if first.Body != "Line one.\nLine two." {
		t.Errorf("body = %q, want the <br> kept as a newline", first.Body)
	}
	if first.Date != "17 Aug 2026" {
		t.Errorf("date = %q", first.Date)
	}
	if first.Author != "" {
		t.Errorf("author = %q, want empty for a null author", first.Author)
	}
	if first.ImageURL != "https://cdn/500-a.jpg" {
		t.Errorf("card image = %q, want the 500px rendition", first.ImageURL)
	}
	if first.LargeURL != "https://cdn/1000-a.jpg" {
		t.Errorf("modal image = %q, want the 1000px rendition", first.LargeURL)
	}
	if len(first.Images) != 2 {
		t.Fatalf("want 2 gallery images, got %d", len(first.Images))
	}
	// The second gallery entry only has a 500px file, so that has to do.
	if first.Images[0] != "https://cdn/1000-g1.jpg" || first.Images[1] != "https://cdn/500-g2.jpg" {
		t.Errorf("gallery = %v", first.Images)
	}
}

func TestParseHailArticlesSummaryFallsBackToBody(t *testing.T) {
	articles, err := parseHailArticles(hailPageHTML)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	second := articles[1]
	// lead was null, so the first paragraph stands in — not the whole body.
	if second.Summary != "First paragraph about the appointment." {
		t.Errorf("summary = %q", second.Summary)
	}
	if !strings.Contains(second.Body, "Second paragraph & more.") {
		t.Errorf("body lost the second paragraph: %q", second.Body)
	}
	if !strings.Contains(second.Body, "\n\n") {
		t.Errorf("body lost its paragraph break: %q", second.Body)
	}
}

func TestParseHailArticlesUsesFirstImageWithoutAHero(t *testing.T) {
	articles, _ := parseHailArticles(hailPageHTML)
	last := articles[2]
	if last.ImageURL != "https://cdn/500-c.jpg" {
		t.Errorf("card image = %q, want the first inline image", last.ImageURL)
	}
	if last.LargeURL != "https://cdn/1000-c.jpg" {
		t.Errorf("modal image = %q", last.LargeURL)
	}
}

func TestParseHailArticlesRejectsAPageWithoutData(t *testing.T) {
	if _, err := parseHailArticles("<html><body>Loading…</body></html>"); err == nil {
		t.Error("want an error when the page carries no article JSON")
	}
}

func TestFlexIntTolerance(t *testing.T) {
	// A silent type change upstream must cost the ordering, not the whole fetch.
	page := `window.HAIL.articles = [
	  {"id":"a","order":{"weird":true},"status":"published","title":"A","body":"<p>x</p>"},
	  {"id":"b","order":1,"status":"published","title":"B","body":"<p>y</p>"}
	];`
	articles, err := parseHailArticles(page)
	if err != nil {
		t.Fatalf("an unusable order field should not fail the parse: %v", err)
	}
	if len(articles) != 2 {
		t.Fatalf("got %d articles", len(articles))
	}
	// "b" has a real order, so it sorts ahead of the unnumbered "a".
	if articles[0].ID != "b" {
		t.Errorf("unnumbered article should fall to the back, got %q first", articles[0].ID)
	}
}

// ── Text helpers ────────────────────────────────────────────────────────────

func TestHTMLToPlainText(t *testing.T) {
	cases := []struct{ in, want string }{
		{"", ""},
		{"<p>One</p><p>Two</p>", "One\n\nTwo"},
		{"<p>A<br/>B</p>", "A\nB"},
		{"<p>Tom &amp; Jerry &#39;s</p>", "Tom & Jerry 's"},
		{"<p>lots   of\t spaces</p>", "lots of spaces"},
		{"<p>a</p><p></p><p></p><p>b</p>", "a\n\nb"},
		{`<p><a href="x">link</a> text</p>`, "link text"},
	}
	for _, c := range cases {
		if got := htmlToPlainText(c.in); got != c.want {
			t.Errorf("htmlToPlainText(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestTruncateWordsBreaksOnAWord(t *testing.T) {
	got := truncateWords("the quick brown fox jumps over", 14)
	if strings.Contains(got, "bro…") {
		t.Errorf("cut mid-word: %q", got)
	}
	if !strings.HasSuffix(got, "…") {
		t.Errorf("want an ellipsis, got %q", got)
	}
	if len(got) > 15 {
		t.Errorf("too long: %q", got)
	}
	if unchanged := truncateWords("short", 50); unchanged != "short" {
		t.Errorf("short strings must pass through, got %q", unchanged)
	}
}

func TestFormatHailDate(t *testing.T) {
	cases := map[string]string{
		"2026-08-17 23:34:01": "17 Aug 2026",
		"2026-08-17":          "17 Aug 2026",
		"":                    "",
		"next Tuesday":        "next Tuesday", // unrecognised input is left alone
	}
	for in, want := range cases {
		if got := formatHailDate(in); got != want {
			t.Errorf("formatHailDate(%q) = %q, want %q", in, got, want)
		}
	}
}
