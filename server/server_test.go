package main

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/auth0/go-jwt-middleware/v2/validator"
	"github.com/labstack/echo/v4"
)

// newTestDB gives each test an empty database in a throwaway working directory.
func newTestDB(t *testing.T) {
	t.Helper()
	chdirTemp(t)
	if err := openDatabase(dataPath("test.db")); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
}

// addUser inserts a user whose profile counts as already synced from Auth0.
func addUser(t *testing.T, id, email string) {
	t.Helper()
	now := time.Now().Unix()
	_, err := db.Exec(`INSERT INTO users(id, email, email_verified, name, provider, created_at, last_seen_at, profile_synced)
		VALUES(?, ?, 1, ?, ?, ?, ?, ?)`, id, email, strings.Split(email, "@")[0], providerFromSubject(id), now, now, now)
	if err != nil {
		t.Fatal(err)
	}
}

// call runs a handler as the given signed-in user ("" = nobody).
func call(t *testing.T, h echo.HandlerFunc, method, path, body, sub string, params ...string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
	rec := httptest.NewRecorder()
	c := echo.New().NewContext(req, rec)
	if len(params) > 0 {
		var names, values []string
		for i := 0; i+1 < len(params); i += 2 {
			names, values = append(names, params[i]), append(values, params[i+1])
		}
		c.SetParamNames(names...)
		c.SetParamValues(values...)
	}
	if sub != "" {
		c.Set("user", &validator.ValidatedClaims{RegisteredClaims: validator.RegisteredClaims{Subject: sub}})
	}
	if err := h(c); err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	return rec
}

func decode(t *testing.T, rec *httptest.ResponseRecorder, out interface{}) {
	t.Helper()
	if err := json.Unmarshal(rec.Body.Bytes(), out); err != nil {
		t.Fatalf("bad JSON %q: %v", rec.Body.String(), err)
	}
}

const (
	adminID   = "google-oauth2|admin"
	studentID = "auth0|student"
)

// ── Access rules ─────────────────────────────────────────────────────────────

func TestRoutesRefuseCallersWithoutTheRightCredentials(t *testing.T) {
	newTestDB(t)
	os.Setenv("MIRROR_API_KEY", "mirror-secret")
	defer os.Unsetenv("MIRROR_API_KEY")
	e := newServer()

	cases := []struct {
		method, path string
		header       map[string]string
		want         int
	}{
		{"GET", "/api/admin/analytics", nil, 401},
		{"GET", "/api/admin/users", nil, 401},
		{"DELETE", "/api/admin/users/x", nil, 401},
		{"POST", "/api/analytics/config", nil, 401},
		{"POST", "/api/notices/config", nil, 401},
		{"POST", "/api/admin/screensaver", nil, 401},
		{"POST", "/api/admin/banner", nil, 401},
		{"POST", "/api/admin/banner", map[string]string{"X-Admin-Email": "marminamina3@gmail.com"}, 401}, // header alone is not proof
		{"GET", "/api/users/me", nil, 401},
		{"GET", "/api/download-index", nil, 401},
		{"GET", "/api/download-index", map[string]string{"X-Mirror-Key": "wrong"}, 401},
		{"GET", "/api/download-index", map[string]string{"X-Mirror-Key": "mirror-secret"}, 200},
		{"POST", "/api/verify-face", nil, 401},
		{"POST", "/api/analytics/events", nil, 401},
		{"GET", "/api/timetable?user_id=x", nil, 401},
		{"GET", "/api/screensaver", nil, 200},
		{"GET", "/api/banner", nil, 200},
	}
	for _, tc := range cases {
		req := httptest.NewRequest(tc.method, tc.path, strings.NewReader("{}"))
		req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
		for k, v := range tc.header {
			req.Header.Set(k, v)
		}
		rec := httptest.NewRecorder()
		e.ServeHTTP(rec, req)
		if rec.Code != tc.want {
			t.Errorf("%s %s %v = %d, want %d", tc.method, tc.path, tc.header, rec.Code, tc.want)
		}
	}
}

func TestBannerAcceptsTheUpdaterToken(t *testing.T) {
	newTestDB(t)
	os.Setenv("ADMIN_TOKEN", "updater-secret")
	defer os.Unsetenv("ADMIN_TOKEN")
	req := httptest.NewRequest("POST", "/api/admin/banner", strings.NewReader(`{"message":"Updating"}`))
	req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
	req.Header.Set("X-Admin-Token", "updater-secret")
	rec := httptest.NewRecorder()
	newServer().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("updater banner = %d", rec.Code)
	}
	var b BannerResponse
	getSetting("banner", &b)
	if b.Message != "Updating" {
		t.Errorf("banner = %q", b.Message)
	}
}

func TestOnlyVerifiedListedEmailsAreAdmins(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`INSERT INTO users(id, email, email_verified, created_at, last_seen_at, profile_synced)
		VALUES('auth0|unverified', 'marminamina3@gmail.com', 0, 0, 0, ?)`, time.Now().Unix())

	for sub, want := range map[string]bool{adminID: true, studentID: false, "auth0|unverified": false} {
		rec := call(t, getCurrentUser, "GET", "/api/users/me", "", sub)
		var me struct {
			IsAdmin bool `json:"is_admin"`
		}
		decode(t, rec, &me)
		if me.IsAdmin != want {
			t.Errorf("%s is_admin = %v, want %v", sub, me.IsAdmin, want)
		}
	}
}

func TestProviderComesFromTheAuth0Subject(t *testing.T) {
	for sub, want := range map[string]string{"google-oauth2|1": "google", "auth0|2": "email", "windowslive|3": "windowslive"} {
		if got := providerFromSubject(sub); got != want {
			t.Errorf("providerFromSubject(%q) = %q, want %q", sub, got, want)
		}
	}
}

// ── Student IDs ──────────────────────────────────────────────────────────────

func TestStudentIDsAreLinkedOncePerAccount(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	addUser(t, "auth0|other", "other@kingshigh.school.nz")

	if rec := call(t, saveBarcode, "PUT", "/", `{"barcode":" kh-18234\n"}`, studentID); rec.Code != 200 {
		t.Fatalf("link = %d %s", rec.Code, rec.Body)
	}
	if got := findUserByBarcode("KH-18234"); got != studentID {
		t.Errorf("findUserByBarcode = %q", got)
	}
	if rec := call(t, saveBarcode, "PUT", "/", `{"barcode":"KH-18234"}`, "auth0|other"); rec.Code != 409 {
		t.Errorf("second account claiming the ID = %d, want 409", rec.Code)
	}
	call(t, deleteBarcode, "DELETE", "/", "", studentID)
	if got := findUserByBarcode("KH-18234"); got != "" {
		t.Errorf("unlinked ID still resolves to %q", got)
	}
}

func TestVerifyBarcodeReturnsTheDashboard(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`UPDATE users SET barcode = 'KH-1', language = 'mi-NZ' WHERE id = ?`, studentID)
	rec := call(t, verifyBarcode, "POST", "/", `{"barcode":"kh-1"}`, "")
	var out map[string]interface{}
	decode(t, rec, &out)
	if out["user_id"] != studentID || out["auth_method"] != "barcode" || out["language"] != "mi-NZ" {
		t.Errorf("payload = %v", out)
	}
	if rec := call(t, verifyBarcode, "POST", "/", `{"barcode":"KH-2"}`, ""); rec.Code != 404 {
		t.Errorf("unknown ID = %d", rec.Code)
	}
}

// ── Admin: users table, removals and messages ────────────────────────────────

func TestAdminSeesWhoSignedUpAndWhatTheyLinked(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`UPDATE users SET barcode = 'KH-1' WHERE id = ?`, studentID)
	db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, '[[0]]', 1, 5)`, studentID)
	for i := 0; i < 3; i++ {
		db.Exec(`INSERT INTO sessions(id, user_id, variant, session_type, created_at) VALUES(?, ?, 'A', 'user', ?)`,
			"s"+string(rune('a'+i)), studentID, 100+i)
	}

	rec := call(t, adminListUsers, "GET", "/api/admin/users?q=KID", "", adminID)
	var out struct {
		Users  []adminUserRow  `json:"users"`
		Totals map[string]int `json:"totals"`
	}
	decode(t, rec, &out)
	if len(out.Users) != 1 {
		t.Fatalf("search for KID found %d users", len(out.Users))
	}
	u := out.Users[0]
	if u.Email != "kid@kingshigh.school.nz" || u.Provider != "email" || !u.HasBarcode || !u.HasFace || u.Sessions != 3 || u.LastSessionAt != 102 {
		t.Errorf("row = %+v", u)
	}
	if out.Totals["users"] != 2 || out.Totals["with_face"] != 1 || out.Totals["with_barcode"] != 1 {
		t.Errorf("totals = %v", out.Totals)
	}
	// Search by student ID too.
	rec = call(t, adminListUsers, "GET", "/api/admin/users?q=kh-1", "", adminID)
	decode(t, rec, &out)
	if len(out.Users) != 1 {
		t.Errorf("search by student ID found %d", len(out.Users))
	}
}

func TestRemovingAFaceScanTellsTheStudent(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, '[[0]]', 1, 5)`, studentID)

	rec := call(t, adminRemoveUserData, "DELETE", "/", "", adminID, "id", studentID, "kind", "face")
	if rec.Code != 200 {
		t.Fatalf("remove face = %d %s", rec.Code, rec.Body)
	}
	var n int
	db.QueryRow(`SELECT COUNT(*) FROM faces`).Scan(&n)
	if n != 0 {
		t.Error("face still stored")
	}

	var me struct {
		HasFace  bool          `json:"has_face"`
		Messages []userMessage `json:"messages"`
	}
	decode(t, call(t, getCurrentUser, "GET", "/", "", studentID), &me)
	if me.HasFace || len(me.Messages) != 1 || !strings.Contains(me.Messages[0].Message, "face scan") ||
		!strings.Contains(me.Messages[0].Message, ContactEmail) {
		t.Fatalf("student sees %+v", me)
	}
	call(t, markMessagesSeen, "POST", "/", "", studentID)
	decode(t, call(t, getCurrentUser, "GET", "/", "", studentID), &me)
	if len(me.Messages) != 0 {
		t.Error("message still shown after it was read")
	}

	if rec := call(t, adminRemoveUserData, "DELETE", "/", "", adminID, "id", studentID, "kind", "face"); rec.Code != 404 {
		t.Errorf("removing a face that isn't there = %d", rec.Code)
	}
	var audits int
	db.QueryRow(`SELECT COUNT(*) FROM admin_audit WHERE action = 'remove_face'`).Scan(&audits)
	if audits != 1 {
		t.Errorf("audit rows = %d", audits)
	}
}

func TestDeletingAUserKeepsAnonymousAnalyticsAndWarnsThemOnReturn(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`UPDATE users SET barcode = 'KH-1' WHERE id = ?`, studentID)
	db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, '[[0]]', 1, 5)`, studentID)
	db.Exec(`INSERT INTO sessions(id, user_id, variant, session_type, created_at) VALUES('s1', ?, 'A', 'user', 1)`, studentID)

	if rec := call(t, adminDeleteUser, "DELETE", "/", "", adminID, "id", studentID); rec.Code != 200 {
		t.Fatalf("delete = %d %s", rec.Code, rec.Body)
	}
	if userExists(studentID) || findUserByBarcode("KH-1") != "" {
		t.Error("user data survived")
	}
	var sessions, linked int
	db.QueryRow(`SELECT COUNT(*), COUNT(user_id) FROM sessions`).Scan(&sessions, &linked)
	if sessions != 1 || linked != 0 {
		t.Errorf("sessions=%d still linked=%d", sessions, linked)
	}

	// They sign up again with the same email and are told what happened.
	addUser(t, "auth0|student-again", "kid@kingshigh.school.nz")
	var me struct {
		Messages []userMessage `json:"messages"`
	}
	decode(t, call(t, getCurrentUser, "GET", "/", "", "auth0|student-again"), &me)
	if len(me.Messages) != 1 || !strings.Contains(me.Messages[0].Message, "account") {
		t.Errorf("returning user sees %+v", me.Messages)
	}

	if rec := call(t, adminDeleteUser, "DELETE", "/", "", adminID, "id", adminID); rec.Code != 400 {
		t.Errorf("admin deleting themselves = %d", rec.Code)
	}
}

// ── Faces ────────────────────────────────────────────────────────────────────

func TestFaceIndexAndCollisions(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	addUser(t, "auth0|other", "other@kingshigh.school.nz")
	enc := make([]float64, 128)
	raw, _ := json.Marshal([][]float64{enc, enc})
	db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, ?, 2, 5)`, studentID, string(raw))

	var idx struct {
		Vectors [][]float64 `json:"vectors"`
		UserMap []string    `json:"user_map"`
	}
	decode(t, call(t, downloadIndex, "GET", "/", "", ""), &idx)
	if len(idx.Vectors) != 2 || idx.UserMap[1] != studentID {
		t.Errorf("index = %d vectors, map %v", len(idx.Vectors), idx.UserMap)
	}

	near := make([]float64, 128)
	near[0] = 0.1
	if who, d := closestOtherFace("auth0|other", near); who != studentID || d > 0.11 {
		t.Errorf("closest = %q at %f", who, d)
	}
	if who, _ := closestOtherFace(studentID, near); who != "" {
		t.Errorf("a user collided with themselves: %q", who)
	}

	if rec := call(t, verifyFace, "POST", "/", `{"user_id":"`+studentID+`"}`, ""); rec.Code != 200 {
		t.Errorf("verify enrolled = %d", rec.Code)
	}
	if rec := call(t, verifyFace, "POST", "/", `{"user_id":"auth0|other"}`, ""); rec.Code != 401 {
		t.Errorf("verify without a face = %d", rec.Code)
	}
}

// ── Analytics ────────────────────────────────────────────────────────────────

func TestAnalyticsRecordsAndSummarisesSessions(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	events := []SessionAnalyticsEvent{
		{SessionID: "a1", UserID: studentID, Variant: "A", SessionType: "user", AuthMethod: "face", DurationSec: 30, HasGesture: true, TimeToFirstGesture: 4, GestureTapCount: 2, TimeToAuthSec: 2},
		{SessionID: "b1", UserID: "auth0|nobody", Variant: "b", SessionType: "guest", AuthMethod: "none", DurationSec: 10, HandSeen: true, TutorialShown: 1, TutorialDismissed: 1, FromScreensaver: true, ScreensaverMode: "logo"},
		{SessionID: "b2", Variant: "B", SessionType: "weird", DurationSec: -5, GestureScrollCount: -3},
	}
	for _, ev := range events {
		body, _ := json.Marshal(ev)
		if rec := call(t, recordAnalyticsEvent, "POST", "/", string(body), ""); rec.Code != 200 {
			t.Fatalf("record = %d", rec.Code)
		}
	}
	// The same session sent twice (a retry) is stored once.
	body, _ := json.Marshal(events[0])
	call(t, recordAnalyticsEvent, "POST", "/", string(body), "")

	var linked int
	db.QueryRow(`SELECT COUNT(user_id) FROM sessions`).Scan(&linked)
	if linked != 1 {
		t.Errorf("sessions linked to users = %d, want 1 (unknown users are dropped)", linked)
	}

	var sum AnalyticsSummaryResponse
	decode(t, call(t, getAdminAnalytics, "GET", "/", "", ""), &sum)
	if sum.TotalSessions != 3 || sum.UserSessions != 1 || sum.GuestSessions != 2 || sum.FaceAuthCount != 1 {
		t.Errorf("totals = %+v", sum)
	}
	if sum.VariantA.GestureAdoptionRate != 100 || sum.VariantB.TotalSessions != 2 || sum.VariantB.HandSeenRate != 50 {
		t.Errorf("variants A=%+v B=%+v", sum.VariantA, sum.VariantB)
	}
	if sum.VariantB.TutorialDismissRate != 100 || sum.FromScreensaver != 1 || sum.ScreensaverModes["logo"] != 1 {
		t.Errorf("tutorial/screensaver = %+v %v", sum.VariantB, sum.ScreensaverModes)
	}
	if sum.AvgTimeToAuthSec != 2 || len(sum.RecentSessions) != 3 || sum.RecentSessions[0].SessionID != "b2" {
		t.Errorf("auth time %v, recent %d", sum.AvgTimeToAuthSec, len(sum.RecentSessions))
	}
	if sum.RecentSessions[0].DurationSec != 0 || sum.RecentSessions[0].GestureScrollCount != 0 || sum.RecentSessions[0].SessionType != "guest" {
		t.Errorf("bad input was not clamped: %+v", sum.RecentSessions[0])
	}
}

func TestABModeIsSavedAndForced(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	call(t, updateAnalyticsConfig, "POST", "/", `{"mode":"force_b"}`, adminID)
	var cfg map[string]interface{}
	decode(t, call(t, getAnalyticsConfig, "GET", "/", "", ""), &cfg)
	if cfg["mode"] != "force_b" || cfg["active_variant"] != "B" || cfg["updated_by"] != "marminamina3@gmail.com" {
		t.Errorf("config = %v", cfg)
	}
}

// ── Screensaver ──────────────────────────────────────────────────────────────

var tinyPNG = []byte("\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")

func uploadImages(t *testing.T, kind string, files map[string][]byte) *httptest.ResponseRecorder {
	t.Helper()
	var buf bytes.Buffer
	boundary := "XBOUNDARYX"
	for name, data := range files {
		buf.WriteString("--" + boundary + "\r\nContent-Disposition: form-data; name=\"files\"; filename=\"" + name + "\"\r\nContent-Type: application/octet-stream\r\n\r\n")
		buf.Write(data)
		buf.WriteString("\r\n")
	}
	buf.WriteString("--" + boundary + "--\r\n")
	req := httptest.NewRequest("POST", "/api/admin/screensaver/images?kind="+kind, &buf)
	req.Header.Set(echo.HeaderContentType, "multipart/form-data; boundary="+boundary)
	rec := httptest.NewRecorder()
	c := echo.New().NewContext(req, rec)
	c.Set("user", &validator.ValidatedClaims{RegisteredClaims: validator.RegisteredClaims{Subject: adminID}})
	if err := uploadScreensaverImages(c); err != nil {
		t.Fatal(err)
	}
	return rec
}

func TestScreensaverModesImagesAndCleanup(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")

	if rec := call(t, setScreensaverConfig, "POST", "/", `{"mode":"slideshow"}`, adminID); rec.Code != 400 {
		t.Errorf("slideshow with no images = %d, want 400", rec.Code)
	}
	rec := uploadImages(t, "slide", map[string][]byte{"a.png": tinyPNG, "evil.png": []byte("<script>alert(1)</script>")})
	var up struct {
		Rejected []string `json:"rejected"`
	}
	decode(t, rec, &up)
	if rec.Code != 200 || len(up.Rejected) != 1 || !strings.Contains(up.Rejected[0], "evil.png") {
		t.Fatalf("upload = %d %v", rec.Code, up.Rejected)
	}
	if rec := call(t, setScreensaverConfig, "POST", "/", `{"mode":"slideshow","slide_seconds":1}`, adminID); rec.Code != 200 {
		t.Fatalf("set slideshow = %d %s", rec.Code, rec.Body)
	}

	var ss struct {
		Mode         string             `json:"mode"`
		SlideSeconds int                `json:"slide_seconds"`
		Slides       []screensaverImage `json:"slides"`
	}
	decode(t, call(t, getScreensaver, "GET", "/", "", ""), &ss)
	if ss.Mode != "slideshow" || ss.SlideSeconds != 3 || len(ss.Slides) != 1 || ss.Slides[0].Ext != "png" {
		t.Fatalf("screensaver = %+v", ss)
	}
	file := filepath.Join(screensaverDir(), ss.Slides[0].SHA256+".png")
	if _, err := os.Stat(file); err != nil {
		t.Fatal("image not stored")
	}

	// Serving: only <sha256>.<ext> names.
	for name, want := range map[string]int{ss.Slides[0].SHA256 + ".png": 200, "../test.db": 404, "x.png": 404} {
		req := httptest.NewRequest("GET", "/", nil)
		rec := httptest.NewRecorder()
		c := echo.New().NewContext(req, rec)
		c.SetParamNames("name")
		c.SetParamValues(name)
		getScreensaverFile(c)
		if rec.Code != want {
			t.Errorf("file %q = %d, want %d", name, rec.Code, want)
		}
	}

	// Removing the last slide falls back to the demo and deletes the file.
	id := ss.Slides[0].ID
	call(t, deleteScreensaverImage, "DELETE", "/", "", adminID, "id", itoa(id))
	decode(t, call(t, getScreensaver, "GET", "/", "", ""), &ss)
	if ss.Mode != "demo" || len(ss.Slides) != 0 {
		t.Errorf("after delete: %+v", ss)
	}
	if _, err := os.Stat(file); !os.IsNotExist(err) {
		t.Error("image file left behind")
	}

	// A logo upload replaces the previous logo, even when it is the same picture.
	uploadImages(t, "logo", map[string][]byte{"logo.png": tinyPNG})
	uploadImages(t, "logo", map[string][]byte{"logo.png": tinyPNG})
	var logo struct {
		Logo *screensaverImage `json:"logo"`
	}
	decode(t, call(t, getScreensaver, "GET", "/", "", ""), &logo)
	if logo.Logo == nil {
		t.Fatal("no logo")
	}
	if _, err := os.Stat(filepath.Join(screensaverDir(), logo.Logo.SHA256+".png")); err != nil {
		t.Error("re-uploading the same logo lost its file")
	}
	var logos int
	db.QueryRow(`SELECT COUNT(*) FROM screensaver_images WHERE kind = 'logo'`).Scan(&logos)
	if logos != 1 {
		t.Errorf("%d logos stored", logos)
	}
}

func itoa(n int64) string { return strconv.FormatInt(n, 10) }

// ── Fresh start ──────────────────────────────────────────────────────────────

func TestANewDatabaseWipesTheOldFileStore(t *testing.T) {
	chdirTemp(t)
	os.MkdirAll("data", 0755)
	os.MkdirAll("encodings", 0755)
	keep := []string{"data/daily_notices.json", "data/kings_week.json"}
	gone := []string{"data/auth0_x_barcode.txt", "data/auth0_x_widgets.json", "data/auth0_x_language.txt",
		"data/auth0_x_ics_url.txt", "data/analytics_events.json", "data/face_collisions.json", "encodings/auth0_x.pickle"}
	for _, f := range append(keep, gone...) {
		os.WriteFile(f, []byte("x"), 0644)
	}
	if err := openDatabase(dataPath("smartmirror.db")); err != nil {
		t.Fatal(err)
	}
	defer func() { db.Close() }() // whichever handle is open at the end
	for _, f := range gone {
		if _, err := os.Stat(f); !os.IsNotExist(err) {
			t.Errorf("%s survived the wipe", f)
		}
	}
	for _, f := range keep {
		if _, err := os.Stat(f); err != nil {
			t.Errorf("%s (a public cache) was deleted", f)
		}
	}

	// Re-opening an existing database must not wipe anything.
	db.Close()
	os.WriteFile("data/auth0_y_barcode.txt", []byte("x"), 0644)
	if err := openDatabase(dataPath("smartmirror.db")); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat("data/auth0_y_barcode.txt"); err != nil {
		t.Error("an existing database wiped files again")
	}
}

func TestStudentsCanWipeTheirOwnData(t *testing.T) {
	newTestDB(t)
	addUser(t, studentID, "kid@kingshigh.school.nz")
	db.Exec(`UPDATE users SET barcode = 'KH-1', ics_url = 'x', dashboard = '{}', language = 'mi-NZ' WHERE id = ?`, studentID)
	db.Exec(`INSERT INTO faces(user_id, encodings, frames, trained_at) VALUES(?, '[[0]]', 1, 5)`, studentID)
	if rec := call(t, deleteMyData, "DELETE", "/", "", studentID); rec.Code != 200 {
		t.Fatalf("wipe = %d", rec.Code)
	}
	var faces int
	var barcode sql.NullString
	var ics, dash, lang string
	db.QueryRow(`SELECT COUNT(*) FROM faces`).Scan(&faces)
	db.QueryRow(`SELECT barcode, ics_url, dashboard, language FROM users WHERE id = ?`, studentID).Scan(&barcode, &ics, &dash, &lang)
	if faces != 0 || barcode.Valid || ics != "" || dash != "" || lang != "en-NZ" {
		t.Errorf("left behind: faces=%d barcode=%v ics=%q dash=%q lang=%q", faces, barcode, ics, dash, lang)
	}
}

func TestMirrorNoticeLevelsAndExpiry(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	rec := call(t, setAdminBanner, "POST", "/", `{"message":"  Fire drill\n at 2pm ","level":"urgent","expires_in_minutes":60}`, adminID)
	var b BannerResponse
	decode(t, rec, &b)
	if b.Message != "Fire drill at 2pm" || b.Level != "urgent" || b.ExpiresAt-b.UpdatedAt != 3600 || b.UpdatedBy != "marminamina3@gmail.com" {
		t.Fatalf("banner = %+v", b)
	}
	decode(t, call(t, getAdminBanner, "GET", "/", "", ""), &b)
	if b.Message != "Fire drill at 2pm" {
		t.Errorf("public banner = %+v", b)
	}

	// Once it expires, mirrors stop showing it.
	setSetting("banner", BannerResponse{Message: "old", Level: "warning", ExpiresAt: time.Now().Unix() - 1})
	decode(t, call(t, getAdminBanner, "GET", "/", "", ""), &b)
	if b.Message != "" {
		t.Errorf("expired banner still shown: %+v", b)
	}

	if rec := call(t, setAdminBanner, "POST", "/", `{"message":"`+strings.Repeat("x", 281)+`"}`, adminID); rec.Code != 400 {
		t.Errorf("over-long notice = %d", rec.Code)
	}
	call(t, setAdminBanner, "POST", "/", `{"message":"Hi","level":"bogus"}`, adminID)
	decode(t, call(t, getAdminBanner, "GET", "/", "", ""), &b)
	if b.Level != "notice" || b.ExpiresAt != 0 {
		t.Errorf("defaults = %+v", b)
	}
	var audits int
	db.QueryRow(`SELECT COUNT(*) FROM admin_audit WHERE action = 'banner_set'`).Scan(&audits)
	if audits != 2 {
		t.Errorf("audit rows = %d", audits)
	}
}

func TestMirrorLogsArePerMirrorCappedAndSafe(t *testing.T) {
	newTestDB(t)
	addUser(t, adminID, "marminamina3@gmail.com")
	big := strings.Repeat("line of log text\n", 50000) // ~850 KB
	body, _ := json.Marshal(map[string]interface{}{
		"mirror_id": "../../etc/library mirror",
		"logs":      map[string]string{"mirror": big, "gesture_engine": "[GESTURE] 18 fps", "secrets": "nope"},
	})
	rec := call(t, receiveMirrorLogs, "POST", "/", string(body), "")
	if rec.Code != 200 {
		t.Fatalf("upload = %d %s", rec.Code, rec.Body)
	}
	call(t, receiveMirrorLogs, "POST", "/", `{"mirror_id":"hall","logs":{"face":"[FACES] 3 people"}}`, "")

	var out struct {
		Mirror  string             `json:"mirror"`
		Content string             `json:"content"`
		Mirrors []mirrorLogSummary `json:"mirrors"`
	}
	decode(t, call(t, getAdminLogs, "GET", "/api/admin/logs?mirror=etc-library-mirror&name=mirror", "", adminID), &out)
	if len(out.Content) > mirrorLogMaxBytes || !strings.HasPrefix(out.Content, "line of log") {
		t.Errorf("mirror.log not capped to whole lines: %d bytes", len(out.Content))
	}
	if len(out.Mirrors) != 2 {
		t.Errorf("mirrors = %+v", out.Mirrors)
	}
	decode(t, call(t, getAdminLogs, "GET", "/api/admin/logs?mirror=etc-library-mirror&name=gesture", "", adminID), &out)
	if out.Content != "[GESTURE] 18 fps" {
		t.Errorf("gesture = %q", out.Content)
	}
	decode(t, call(t, getAdminLogs, "GET", "/api/admin/logs?mirror=hall&name=face", "", adminID), &out)
	if out.Content != "[FACES] 3 people" {
		t.Errorf("hall face = %q", out.Content)
	}
	// Nothing escapes data/mirror_logs, and unknown log names are ignored.
	if _, err := os.Stat(filepath.Join(mirrorLogsDir(), "etc-library-mirror", "mirror.log")); err != nil {
		t.Error("log not stored under its sanitised mirror folder")
	}
	if rec := call(t, receiveMirrorLogs, "POST", "/", `{"logs":{"passwd":"x"}}`, ""); rec.Code != 400 {
		t.Errorf("unknown log = %d", rec.Code)
	}
}
