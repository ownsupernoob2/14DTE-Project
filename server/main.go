package main

import (
	"log"
	"os"

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
	ID    string      `json:"id"`
	Type  string      `json:"type"`
	X     float64     `json:"x"`
	Y     float64     `json:"y"`
	Data  interface{} `json:"data,omitempty"`
}

type Dashboard struct {
	ID      string   `json:"id"`
	UserID  string   `json:"user_id"`
	Widgets []Widget `json:"widgets"`
}

func init() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}
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

	// Protected routes (JWT middleware)
	protected := e.Group("/api")
	protected.Use(middleware.JWTWithConfig(middleware.JWTConfig{
		SigningMethod: "RS256",
		SigningKey:    getAuth0PublicKey(),
	}))

	// User routes
	protected.GET("/users/me", getCurrentUser)
	protected.PUT("/users/:id", updateUser)
	protected.GET("/users/:id", getUser)

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
	// TODO: Implement Auth0 login
	return c.JSON(200, map[string]string{"message": "Login endpoint"})
}

func register(c echo.Context) error {
	// TODO: Implement Auth0 registration
	return c.JSON(200, map[string]string{"message": "Register endpoint"})
}

func refreshToken(c echo.Context) error {
	// TODO: Implement token refresh
	return c.JSON(200, map[string]string{"message": "Token refresh endpoint"})
}

func getCurrentUser(c echo.Context) error {
	// TODO: Get user from JWT claims
	return c.JSON(200, User{
		ID:    "user-123",
		Email: "user@example.com",
		Name:  "John Doe",
	})
}

func getUser(c echo.Context) error {
	id := c.Param("id")
	// TODO: Fetch user from database
	return c.JSON(200, User{
		ID:    id,
		Email: "user@example.com",
		Name:  "John Doe",
	})
}

func updateUser(c echo.Context) error {
	id := c.Param("id")
	var user User
	if err := c.BindJSON(&user); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	user.ID = id
	// TODO: Update user in database
	return c.JSON(200, user)
}

func getDashboard(c echo.Context) error {
	// TODO: Fetch dashboard from database
	return c.JSON(200, Dashboard{
		ID:      "dashboard-123",
		UserID:  "user-123",
		Widgets: []Widget{},
	})
}

func getWidgets(c echo.Context) error {
	// TODO: Fetch widgets from database
	return c.JSON(200, []Widget{})
}

func addWidget(c echo.Context) error {
	var widget Widget
	if err := c.BindJSON(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	widget.ID = generateID()
	// TODO: Save widget to database
	return c.JSON(201, widget)
}

func updateWidget(c echo.Context) error {
	id := c.Param("id")
	var widget Widget
	if err := c.BindJSON(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	widget.ID = id
	// TODO: Update widget in database
	return c.JSON(200, widget)
}

func deleteWidget(c echo.Context) error {
	id := c.Param("id")
	// TODO: Delete widget from database
	return c.JSON(200, map[string]string{"message": "Widget deleted", "id": id})
}

// Helpers

func generateID() string {
	return "widget-" + string(rune(len([]rune{})))
}

func getAuth0PublicKey() interface{} {
	// TODO: Fetch Auth0 public key
	return nil
}
