package main

import (
	"log"
	"os"
	"os/exec"
	"time"

	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

func init() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}
	os.MkdirAll("faces", 0755)
	os.MkdirAll("temp", 0755)
	os.MkdirAll("encodings", 0755)
	// Per-user widget layouts and barcode links live here.
	os.MkdirAll("data", 0755)
}

func main() {
	StartNoticeFetcher()
	StartKingsWeekFetcher()
	e := echo.New()

	// Middleware
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())
	e.Use(middleware.CORS())

	// Public routes
	e.POST("/auth/login", login)
	e.POST("/auth/register", register)
	e.POST("/auth/refresh", refreshToken)

	// Mirror endpoint — no auth needed for the mirror to verify faces
	e.POST("/api/verify-face", verifyFace)
	e.GET("/api/download-index", downloadIndex)

	// Mirror barcode sign-in. Unauthenticated like verify-face, but a barcode is
	// guessable in a way a face is not, so cap attempts per source IP.
	e.POST("/api/verify-barcode", verifyBarcode, middleware.RateLimiterWithConfig(
		middleware.RateLimiterConfig{
			Store: middleware.NewRateLimiterMemoryStoreWithConfig(
				middleware.RateLimiterMemoryStoreConfig{Rate: 1, Burst: 10, ExpiresIn: time.Minute},
			),
		},
	))

	// Protected routes (JWT middleware)
	protected := e.Group("/api")
	protected.Use(EnsureValidToken())

	// User routes
	protected.GET("/users/me", getCurrentUser)
	protected.PUT("/users/:id", updateUser)
	protected.GET("/users/:id", getUser)

	// Face training route — replaces the old single-image upload
	protected.POST("/faces/train", trainFace)
	protected.DELETE("/faces/me", deleteFace)

	// Legacy single-image face upload (kept for backward compatibility)
	protected.POST("/users/me/face", uploadFace)

	// Student ID / barcode sign-in — the web links a code, the mirror resolves it
	protected.PUT("/users/me/barcode", saveBarcode)
	protected.GET("/users/me/barcode", getBarcode)
	protected.DELETE("/users/me/barcode", deleteBarcode)

	// Dashboard/Widget routes
	protected.GET("/dashboard", getDashboard)
	protected.POST("/dashboard/widgets", addWidget)
	protected.PUT("/dashboard/widgets/:id", updateWidget)
	protected.DELETE("/dashboard/widgets/:id", deleteWidget)
	protected.GET("/dashboard/widgets", getWidgets)
	protected.PUT("/dashboard/widgets/bulk", updateWidgetsBulk)

	// Daily Notices routes
	e.GET("/api/notices", getNotices)
	e.GET("/api/notices/config", getNoticesConfig)
	e.POST("/api/notices/config", saveNoticesConfig)
	protected.POST("/notices/fetch", fetchNotices)

	// Kings Week route
	e.GET("/api/kings-week", getKingsWeek)

	// Admin Banner routes
	e.POST("/api/admin/banner", setAdminBanner)
	e.GET("/api/banner", getAdminBanner)

	// Timetable routes
	e.GET("/api/timetable", getTimetable, OptionalEnsureValidToken())          // public – also accepts JWT
	protected.POST("/timetable/ics", setTimetableURL)
	protected.GET("/timetable/ics", getMyTimetableURL)

	// Health check
	e.GET("/health", health)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	e.Logger.Fatal(e.Start(":" + port))
}

// ─── Handlers ────────────────────────────────────────────────────────────────

func health(c echo.Context) error {
	return c.JSON(200, map[string]string{"status": "ok"})
}

func getPythonCmd() string {
	if _, err := exec.LookPath("python3"); err == nil {
		return "python3"
	}
	return "python"
}
