package main

import (
	"io"
	"log"
	"os"
	"strings"
	"time"

	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

const AppVersion = "v3.0.0"

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}
	logToFile()
	if err := openDatabase(dataPath("smartmirror.db")); err != nil {
		log.Fatalf("Could not open the database: %v", err)
	}
	go facePython() // find Python early so the first face scan isn't slow

	StartNoticeFetcher()
	StartKingsWeekFetcher()

	e := newServer()
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	e.Logger.Fatal(e.Start(":" + port))
}

// logToFile copies the server's log lines (not every request) to
// data/server.log, which admins can read on the Logs page. Kept under ~2 MB.
func logToFile() {
	os.MkdirAll("data", 0700)
	path := serverLogPath()
	if info, err := os.Stat(path); err == nil && info.Size() > 2<<20 {
		os.Rename(path, path+".1")
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		log.Printf("Could not open %s: %v", path, err)
		return
	}
	log.SetOutput(io.MultiWriter(os.Stderr, f))
	log.Printf("Smart Mirror API %s starting", AppVersion)
}

func serverLogPath() string { return dataPath("server.log") }

func newServer() *echo.Echo {
	e := echo.New()
	e.HideBanner = true
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())
	e.Use(middleware.Secure())
	e.Use(middleware.BodyLimit("30M"))
	origins := []string{"*"}
	if raw := os.Getenv("CORS_ORIGINS"); raw != "" {
		origins = strings.Split(raw, ",")
	}
	e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: origins,
		AllowHeaders: []string{"Authorization", "Content-Type", "X-Mirror-Key", "X-Admin-Token"},
	}))

	// ── Public ───────────────────────────────────────────────────────────
	e.GET("/health", health)
	e.GET("/api/health", health)
	e.GET("/api/version", version)
	e.GET("/api/notices", getNotices)
	e.GET("/api/notices/config", getNoticesConfig)
	e.GET("/api/kings-week", getKingsWeek)
	e.GET("/api/banner", getAdminBanner)
	e.GET("/api/analytics/config", getAnalyticsConfig)
	e.GET("/api/screensaver", getScreensaver)
	e.GET("/api/screensaver/files/:name", getScreensaverFile)
	// Signed-in users read their own; mirrors (with their key) any user's.
	e.GET("/api/timetable", getTimetable)

	// ── Mirrors (X-Mirror-Key) ───────────────────────────────────────────
	mirror := e.Group("/api", RequireMirror())
	mirror.POST("/verify-face", verifyFace)
	mirror.GET("/download-index", downloadIndex)
	mirror.POST("/analytics/events", recordAnalyticsEvent)
	mirror.GET("/users/language", getPublicUserLanguage)
	mirror.POST("/logs", receiveMirrorLogs)
	// A student ID is guessable in a way a face is not, so cap attempts per IP.
	mirror.POST("/verify-barcode", verifyBarcode, middleware.RateLimiterWithConfig(middleware.RateLimiterConfig{
		Store: middleware.NewRateLimiterMemoryStoreWithConfig(middleware.RateLimiterMemoryStoreConfig{
			Rate: 1, Burst: 10, ExpiresIn: time.Minute,
		}),
	}))

	// ── Signed-in users (Auth0) ──────────────────────────────────────────
	user := e.Group("/api", EnsureValidToken())
	user.GET("/users/me", getCurrentUser)
	user.POST("/users/me/messages/seen", markMessagesSeen)
	user.DELETE("/users/me/data", deleteMyData)
	user.POST("/faces/train", trainFace)
	user.GET("/faces/train/:id", getFaceTrainJob)
	user.DELETE("/faces/me", deleteFace)
	user.PUT("/users/me/barcode", saveBarcode)
	user.GET("/users/me/barcode", getBarcode)
	user.DELETE("/users/me/barcode", deleteBarcode)
	user.PUT("/users/me/language", saveUserLanguage)
	user.POST("/users/me/language", saveUserLanguage)
	user.GET("/users/me/language", getUserLanguage)
	user.GET("/dashboard", getDashboard)
	user.GET("/dashboard/widgets", getWidgets)
	user.POST("/dashboard/widgets", addWidget)
	user.PUT("/dashboard/widgets/bulk", updateWidgetsBulk)
	user.PUT("/dashboard/widgets/:id", updateWidget)
	user.DELETE("/dashboard/widgets/:id", deleteWidget)
	user.POST("/timetable/ics", setTimetableURL)
	user.GET("/timetable/ics", getMyTimetableURL)
	user.DELETE("/timetable/ics", deleteMyTimetableURL)

	// ── Admins (Auth0 + verified email in ADMIN_EMAILS) ──────────────────
	admin := e.Group("/api", EnsureValidToken(), RequireAdmin())
	admin.GET("/admin/analytics", getAdminAnalytics)
	admin.DELETE("/admin/analytics", adminWipeAnalytics)
	admin.GET("/admin/face-audit", getFaceAuditLog)
	admin.GET("/admin/users", adminListUsers)
	admin.DELETE("/admin/users/:id", adminDeleteUser)
	admin.DELETE("/admin/users/:id/:kind", adminRemoveUserData)
	admin.POST("/analytics/config", updateAnalyticsConfig)
	admin.POST("/notices/config", saveNoticesConfig)
	admin.POST("/notices/fetch", fetchNotices)
	admin.POST("/admin/screensaver", setScreensaverConfig)
	admin.POST("/admin/screensaver/images", uploadScreensaverImages)
	admin.DELETE("/admin/screensaver/images/:id", deleteScreensaverImage)
	admin.GET("/admin/logs", getAdminLogs)
	// The Windows updater posts "updating" notices with ADMIN_TOKEN.
	e.POST("/api/admin/banner", setAdminBanner, RequireAdminOrUpdater())

	return e
}

func health(c echo.Context) error {
	return c.JSON(200, map[string]interface{}{"status": "ok", "version": AppVersion})
}

func version(c echo.Context) error {
	return c.JSON(200, map[string]string{"version": AppVersion, "service": "smart-mirror-api"})
}
