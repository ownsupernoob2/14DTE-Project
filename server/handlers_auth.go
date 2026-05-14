package main

import (
	"strings"
	"github.com/labstack/echo/v4"
)

type User struct {
	ID    string `json:"id"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name"`
}

func login(c echo.Context) error {
	return c.JSON(200, map[string]string{"message": "Login endpoint"})
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
