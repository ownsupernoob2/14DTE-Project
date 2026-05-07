package main

import (
	"context"
	"log"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/auth0/go-jwt-middleware/v2/jwks"
	"github.com/auth0/go-jwt-middleware/v2/validator"
	"github.com/labstack/echo/v4"
)

type CustomClaims struct {
	Scope string `json:"scope"`
}

func (c CustomClaims) Validate(ctx context.Context) error {
	return nil
}

func EnsureValidToken() echo.MiddlewareFunc {
	domain := os.Getenv("AUTH0_DOMAIN")
	audience := os.Getenv("AUTH0_AUDIENCE")

	if domain == "" || audience == "" {
		log.Println("WARNING: AUTH0_DOMAIN or AUTH0_AUDIENCE is not set in .env")
	}

	if !strings.HasPrefix(domain, "http") {
		domain = "https://" + domain
	}
	if !strings.HasSuffix(domain, "/") {
		domain = domain + "/"
	}

	issuerURL, err := url.Parse(domain)
	if err != nil {
		log.Fatalf("Failed to parse the issuer url: %v", err)
	}

	provider := jwks.NewCachingProvider(issuerURL, 5*time.Minute)

	jwtValidator, err := validator.New(
		provider.KeyFunc,
		validator.RS256,
		issuerURL.String(),
		[]string{audience},
		validator.WithCustomClaims(func() validator.CustomClaims {
			return &CustomClaims{}
		}),
		validator.WithAllowedClockSkew(time.Minute),
	)
	if err != nil {
		log.Fatalf("Failed to set up the jwt validator: %v", err)
	}

	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			authHeader := c.Request().Header.Get("Authorization")
			if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
				return echo.NewHTTPError(401, "Missing or malformed Authorization header")
			}

			token := strings.TrimPrefix(authHeader, "Bearer ")

			parsedToken, err := jwtValidator.ValidateToken(c.Request().Context(), token)
			if err != nil {
				log.Printf("Token validation failed: %v", err)
				return echo.NewHTTPError(401, "Invalid token")
			}

			c.Set("user", parsedToken.(*validator.ValidatedClaims))

			return next(c)
		}
	}
}

// getUserIDFromToken extracts the Auth0 'sub' claim (user ID) from the validated
// JWT stored in the echo context. Returns empty string if unavailable.
func getUserIDFromToken(c echo.Context) string {
	raw := c.Get("user")
	if raw == nil {
		return ""
	}
	claims, ok := raw.(*validator.ValidatedClaims)
	if !ok {
		return ""
	}
	return claims.RegisteredClaims.Subject
}
