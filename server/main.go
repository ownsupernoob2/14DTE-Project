package main

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"strings"

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

type FaceRequest struct {
	Image string `json:"image"`
}

func init() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}
	os.MkdirAll("faces", 0755)
	os.MkdirAll("temp", 0755)
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

	// Mirror endpoint (no auth needed for the mirror to verify, but typically would use an API key)
	e.POST("/api/verify-face", verifyFace)

	// Protected routes (JWT middleware)
	protected := e.Group("/api")
	protected.Use(EnsureValidToken())

	// User routes
	protected.GET("/users/me", getCurrentUser)
	protected.PUT("/users/:id", updateUser)
	protected.GET("/users/:id", getUser)
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

// Handlers

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
	return c.JSON(200, User{
		ID:    "user-123",
		Email: "user@example.com",
		Name:  "John Doe",
	})
}

func getUser(c echo.Context) error {
	id := c.Param("id")
	return c.JSON(200, User{
		ID:    id,
		Email: "user@example.com",
		Name:  "John Doe",
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

func uploadFace(c echo.Context) error {
	// In a real app, extract user ID from JWT claims
	// For now, assume a single user or extract from some context
	userID := "user-123"

	var req FaceRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	// Remove data URI prefix if present
	b64data := req.Image
	if idx := strings.Index(b64data, ","); idx != -1 {
		b64data = b64data[idx+1:]
	}

	imgBytes, err := base64.StdEncoding.DecodeString(b64data)
	if err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid base64 image"})
	}

	filepath := fmt.Sprintf("faces/%s.jpg", userID)
	if err := ioutil.WriteFile(filepath, imgBytes, 0644); err != nil {
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
	if err := ioutil.WriteFile(tempPath, imgBytes, 0644); err != nil {
		return c.JSON(500, map[string]string{"error": "Failed to save temp image"})
	}

	// Run Python script
	cmd := exec.Command("python", "verify.py", tempPath, "faces")
	var out bytes.Buffer
	cmd.Stdout = &out
	err = cmd.Run()
	if err != nil {
		log.Println("Python script error:", err)
		return c.JSON(500, map[string]string{"error": "Verification failed"})
	}

	output := strings.TrimSpace(out.String())
	if strings.HasPrefix(output, "MATCH:") {
		matchedUserID := strings.TrimPrefix(output, "MATCH:")
		if matchedUserID == "unknown" {
			return c.JSON(401, map[string]string{"error": "Face not recognized"})
		}

		// If matched, return user info and widgets
		return c.JSON(200, map[string]interface{}{
			"user_id": matchedUserID,
			"widgets": getWidgetsSlice(), // Ideally fetch based on user_id
		})
	}

	return c.JSON(401, map[string]string{"error": "Face not recognized or no face found"})
}

func getDashboard(c echo.Context) error {
	return c.JSON(200, Dashboard{
		ID:      "dashboard-123",
		UserID:  "user-123",
		Widgets: getWidgetsSlice(),
	})
}

// Simple in-memory store for widgets
var widgetsDB = make(map[string]Widget)

func getWidgetsSlice() []Widget {
	list := make([]Widget, 0, len(widgetsDB))
	for _, w := range widgetsDB {
		list = append(list, w)
	}
	return list
}

func getWidgets(c echo.Context) error {
	return c.JSON(200, getWidgetsSlice())
}

func addWidget(c echo.Context) error {
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	if widget.ID == "" {
		widget.ID = generateID()
	}

	widgetsDB[widget.ID] = widget
	return c.JSON(201, widget)
}

func updateWidget(c echo.Context) error {
	id := c.Param("id")
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	widget.ID = id
	widgetsDB[id] = widget
	return c.JSON(200, widget)
}

func deleteWidget(c echo.Context) error {
	id := c.Param("id")
	delete(widgetsDB, id)
	return c.JSON(200, map[string]string{"message": "Widget deleted", "id": id})
}

// Helpers

func generateID() string {
	return "widget-" + string(rune(len(widgetsDB)+97)) // A simple id
}

func getAuth0PublicKey() interface{} {
	return nil
}
