package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

type User struct {
	ID    string `json:"id"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

type Widget struct {
	ID   string      `json:"id"`
	Type string      `json:"type"`
	X    float64     `json:"x"`
	Y    float64     `json:"y"`
	Data interface{} `json:"data,omitempty"`
}

type Dashboard struct {
	ID      string   `json:"id"`
	UserID  string   `json:"user_id"`
	Widgets []Widget `json:"widgets"`
}

// FaceRequest is used by the legacy single-image upload and verify endpoints.
type FaceRequest struct {
	Image string `json:"image"`
}

// TrainRequest accepts a batch of up to 10 base64-encoded images.
type TrainRequest struct {
	Images []string `json:"images"`
}

func init() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}
	os.MkdirAll("faces", 0755)
	os.MkdirAll("temp", 0755)
	os.MkdirAll("encodings", 0755)
}

func main() {
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

	// Fetch parsed AI notices
	e.GET("/api/notices", getNotices)

	// Protected routes (JWT middleware)
	protected := e.Group("/api")
	protected.Use(EnsureValidToken())

	// User routes
	protected.GET("/users/me", getCurrentUser)
	protected.PUT("/users/:id", updateUser)
	protected.GET("/users/:id", getUser)

	// Face training route — replaces the old single-image upload
	protected.POST("/faces/train", trainFace)

	// Legacy single-image face upload (kept for backward compatibility)
	protected.POST("/users/me/face", uploadFace)

	// Dashboard/Widget routes
	protected.GET("/dashboard", getDashboard)
	protected.POST("/dashboard/widgets", addWidget)
	protected.PUT("/dashboard/widgets/:id", updateWidget)
	protected.DELETE("/dashboard/widgets/:id", deleteWidget)
	protected.GET("/dashboard/widgets", getWidgets)

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

func login(c echo.Context) error {
	return c.JSON(200, map[string]string{"message": "Login endpoint"})
}

type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

func register(c echo.Context) error {
	var req RegisterRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	if !strings.HasSuffix(req.Email, "@kingshigh.school.nz") {
		return c.JSON(403, map[string]string{"error": "Only @kingshigh.school.nz email addresses are allowed to register"})
	}

	return c.JSON(200, map[string]string{"message": "Registration successful"})
}

func refreshToken(c echo.Context) error {
	return c.JSON(200, map[string]string{"message": "Token refresh endpoint"})
}

func getCurrentUser(c echo.Context) error {
	userID := getUserIDFromToken(c)
	return c.JSON(200, User{
		ID:    userID,
		Email: "user@example.com",
		Name:  "Student",
	})
}

func getUser(c echo.Context) error {
	id := c.Param("id")
	return c.JSON(200, User{
		ID:    id,
		Email: "user@example.com",
		Name:  "Student",
	})
}

func updateUser(c echo.Context) error {
	id := c.Param("id")
	var user User
	if err := c.Bind(&user); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	user.ID = id
	return c.JSON(200, user)
}

// trainFace receives up to 10 base64 images, saves them temporarily, runs train.py
// to build a face encoding pickle, then deletes the raw images.
// The encoding is saved to encodings/<user_id>.pickle.
func trainFace(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Could not identify user from token"})
	}

	var req TrainRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request body"})
	}

	if len(req.Images) == 0 {
		return c.JSON(400, map[string]string{"error": "No images provided"})
	}

	// Sanitise userID for use as a directory name (Auth0 sub looks like "auth0|abc123")
	safeUserID := strings.ReplaceAll(userID, "|", "_")
	safeUserID = strings.ReplaceAll(safeUserID, "/", "_")

	tempDir := fmt.Sprintf("temp/%s", safeUserID)
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return c.JSON(500, map[string]string{"error": "Could not create temp directory"})
	}
	// Always clean up temp images when we're done
	defer os.RemoveAll(tempDir)

	// Decode and save each image
	saved := 0
	for i, img := range req.Images {
		b64data := img
		if idx := strings.Index(b64data, ","); idx != -1 {
			b64data = b64data[idx+1:]
		}
		imgBytes, err := base64.StdEncoding.DecodeString(b64data)
		if err != nil {
			log.Printf("Skipping image %d: base64 decode error: %v", i, err)
			continue
		}
		filepath := fmt.Sprintf("%s/frame_%d.jpg", tempDir, i)
		if err := os.WriteFile(filepath, imgBytes, 0644); err != nil {
			log.Printf("Skipping image %d: write error: %v", i, err)
			continue
		}
		saved++
	}

	if saved == 0 {
		return c.JSON(400, map[string]string{"error": "No valid images could be decoded"})
	}

	outputPickle := fmt.Sprintf("encodings/%s.pickle", safeUserID)

	// Run the Python training script
	cmd := exec.Command(getPythonCmd(), "train.py", tempDir, outputPickle)
	var out bytes.Buffer
	var errOut bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errOut

	if err := cmd.Run(); err != nil {
		log.Printf("train.py error: %v, stderr: %s", err, errOut.String())
		return c.JSON(500, map[string]string{"error": "Training failed: " + strings.TrimSpace(out.String())})
	}

	output := strings.TrimSpace(out.String())
	if !strings.HasPrefix(output, "OK:") {
		msg := strings.TrimPrefix(output, "ERROR:")
		return c.JSON(500, map[string]string{"error": "Training failed: " + msg})
	}

	framesUsed := 0
	fmt.Sscanf(strings.TrimPrefix(output, "OK:"), "%d", &framesUsed)

	log.Printf("Face training complete for user %s: %d frames used, pickle at %s", safeUserID, framesUsed, outputPickle)

	return c.JSON(200, map[string]interface{}{
		"status":      "trained",
		"frames_used": framesUsed,
		"user_id":     safeUserID,
	})
}

// uploadFace is the legacy single-image face upload, kept for backward compat.
func uploadFace(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = "user-123"
	}

	var req FaceRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	b64data := req.Image
	if idx := strings.Index(b64data, ","); idx != -1 {
		b64data = b64data[idx+1:]
	}

	imgBytes, err := base64.StdEncoding.DecodeString(b64data)
	if err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid base64 image"})
	}

	filepath := fmt.Sprintf("faces/%s.jpg", userID)
	if err := os.WriteFile(filepath, imgBytes, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save image"})
	}

	return c.JSON(200, map[string]string{"message": "Face registered successfully"})
}

func verifyFace(c echo.Context) error {
	var req FaceRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	b64data := req.Image
	if idx := strings.Index(b64data, ","); idx != -1 {
		b64data = b64data[idx+1:]
	}

	imgBytes, err := base64.StdEncoding.DecodeString(b64data)
	if err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid base64 image"})
	}

	tempPath := "temp/verify.jpg"
	if err := os.WriteFile(tempPath, imgBytes, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save temp image"})
	}
	defer os.Remove(tempPath)

	// Run Python verification script against the encodings directory
	cmd := exec.Command(getPythonCmd(), "verify.py", tempPath, "encodings")
	var out bytes.Buffer
	cmd.Stdout = &out
	err = cmd.Run()
	if err != nil {
		log.Println("Python verify error:", err)
		return c.JSON(500, map[string]string{"error": "Verification failed"})
	}

	output := strings.TrimSpace(out.String())

	if output == "NO_FACE" {
		return c.JSON(401, map[string]string{"error": "No face detected"})
	}

	if strings.HasPrefix(output, "MATCH:") {
		matchedUserID := strings.TrimPrefix(output, "MATCH:")
		if matchedUserID == "unknown" {
			return c.JSON(401, map[string]string{"error": "Face not recognised"})
		}

		return c.JSON(200, map[string]interface{}{
			"user_id": matchedUserID,
			"widgets": getWidgetsForUser(matchedUserID),
		})
	}

	return c.JSON(401, map[string]string{"error": "Face not recognised"})
}

func getDashboard(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = c.QueryParam("user_id")
	}
	return c.JSON(200, Dashboard{
		ID:      "dashboard-" + userID,
		UserID:  userID,
		Widgets: getWidgetsForUser(userID),
	})
}

// In-memory cache + file sync per user
func getSafeUserID(userID string) string {
	safeUserID := strings.ReplaceAll(userID, "|", "_")
	safeUserID = strings.ReplaceAll(safeUserID, "/", "_")
	return safeUserID
}

func getUserWidgetsPath(userID string) string {
	return fmt.Sprintf("data/%s_widgets.json", getSafeUserID(userID))
}

func getWidgetsForUser(userID string) []Widget {
	if userID == "" {
		return []Widget{}
	}
	path := getUserWidgetsPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return []Widget{}
	}
	var widgets []Widget
	// Use standard json logic via decoding
	json.Unmarshal(data, &widgets)
	return widgets
}

func saveWidgetsForUser(userID string, widgets []Widget) {
	if userID == "" {
		return
	}
	path := getUserWidgetsPath(userID)
	data, err := json.MarshalIndent(widgets, "", "  ")
	if err == nil {
		os.WriteFile(path, data, 0644)
	}
}

func getWidgets(c echo.Context) error {
	userID := getUserIDFromToken(c)
	return c.JSON(200, getWidgetsForUser(userID))
}

func addWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	if widget.ID == "" {
		widget.ID = "widget-" + strconv.FormatInt(time.Now().UnixNano(), 10)
	}
	widgets := getWidgetsForUser(userID)
	widgets = append(widgets, widget)
	saveWidgetsForUser(userID, widgets)

	return c.JSON(201, widget)
}

func updateWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	id := c.Param("id")
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	widget.ID = id

	widgets := getWidgetsForUser(userID)
	for i, w := range widgets {
		if w.ID == id {
			widgets[i] = widget
			saveWidgetsForUser(userID, widgets)
			return c.JSON(200, widget)
		}
	}
	return c.JSON(404, map[string]string{"error": "Widget not found"})
}

func deleteWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	id := c.Param("id")

	widgets := getWidgetsForUser(userID)
	newWidgets := []Widget{}
	for _, w := range widgets {
		if w.ID != id {
			newWidgets = append(newWidgets, w)
		}
	}
	saveWidgetsForUser(userID, newWidgets)

	return c.JSON(200, map[string]string{"message": "Widget deleted", "id": id})
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

func getPythonCmd() string {
	if _, err := exec.LookPath("python3"); err == nil {
		return "python3"
	}
	return "python"
}


// getNotices serves the daily_notices.json created by the Python AI scraper
func getNotices(c echo.Context) error {
	dataFile := "./data/daily_notices.json"
	
	// Read the JSON file
	fileData, err := os.ReadFile(dataFile)
	if err != nil {
		return c.JSON(404, map[string]string{"error": "Notices not available yet."})
	}

	return c.JSONBlob(200, fileData)
}
