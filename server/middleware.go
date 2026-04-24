package main

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt"
	echojwt "github.com/labstack/echo-jwt/v4"
	"github.com/labstack/echo/v4"
)

// CustomClaims represents JWT claims
type CustomClaims struct {
	Sub   string `json:"sub"`
	Email string `json:"email"`
	jwt.StandardClaims
}

// JWTConfig returns the JWT middleware configuration for Auth0
func JWTConfig() echojwt.Config {
	return echojwt.Config{
		SigningMethod: "RS256",
		KeyFunc: func(token *jwt.Token) (interface{}, error) {
			// TODO: Implement JWKS fetching for Auth0
			// This should fetch the public key from Auth0's JWKS endpoint
			return nil, fmt.Errorf("key not implemented")
		},
		SuccessHandler: func(c echo.Context) {
			// Token is valid, continue to handler
		},
		ErrorHandler: func(c echo.Context, err error) error {
			return echo.ErrUnauthorized
		},
	}
}

// ErrorResponse represents a standard error response
type ErrorResponse struct {
	Error   string `json:"error"`
	Message string `json:"message"`
	Code    int    `json:"code"`
}

// SuccessResponse represents a standard success response
type SuccessResponse struct {
	Data      interface{} `json:"data"`
	Message   string      `json:"message,omitempty"`
	Timestamp time.Time   `json:"timestamp"`
}

// ErrorHandler handles errors in a consistent way
func ErrorHandler(c echo.Context, err error) error {
	code := 500
	message := "Internal Server Error"

	if he, ok := err.(*echo.HTTPError); ok {
		code = he.Code
		message = fmt.Sprintf("%v", he.Message)
	}

	return c.JSON(code, ErrorResponse{
		Error:   fmt.Sprintf("Error %d", code),
		Message: message,
		Code:    code,
	})
}

// SuccessHandler returns a standardized success response
func SuccessHandler(c echo.Context, data interface{}) error {
	return c.JSON(200, SuccessResponse{
		Data:      data,
		Timestamp: time.Now(),
	})
}
