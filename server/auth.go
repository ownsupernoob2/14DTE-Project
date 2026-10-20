package main

// auth.go — Auth0 token validation, the users table, admin and mirror access.
//
// Who someone is comes only from a signature-checked Auth0 access token. Their
// email (needed to decide who is an admin) comes from Auth0's /userinfo, called
// with that same token, never from anything the browser claims about itself.

import (
	"context"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/auth0/go-jwt-middleware/v2/jwks"
	"github.com/auth0/go-jwt-middleware/v2/validator"
	"github.com/labstack/echo/v4"
)

// ContactEmail is who students are told to write to about their data.
const ContactEmail = "minali39@kingshigh.school.nz"

// DefaultAdminEmails is used when ADMIN_EMAILS is not set in .env.
const DefaultAdminEmails = "marminamina3@gmail.com"

type CustomClaims struct {
	Scope string `json:"scope"`
}

func (c CustomClaims) Validate(ctx context.Context) error { return nil }

var (
	jwtValidatorOnce sync.Once
	jwtValidator     *validator.Validator
	auth0Issuer      string
)

func auth0Domain() string {
	domain := strings.TrimSpace(os.Getenv("AUTH0_DOMAIN"))
	if domain == "" {
		return ""
	}
	if !strings.HasPrefix(domain, "http") {
		domain = "https://" + domain
	}
	if !strings.HasSuffix(domain, "/") {
		domain += "/"
	}
	return domain
}

func getValidator() *validator.Validator {
	jwtValidatorOnce.Do(func() {
		domain := auth0Domain()
		audience := os.Getenv("AUTH0_AUDIENCE")
		if domain == "" || audience == "" {
			log.Println("WARNING: AUTH0_DOMAIN or AUTH0_AUDIENCE is not set — every signed-in request will be refused")
			return
		}
		issuerURL, err := url.Parse(domain)
		if err != nil {
			log.Fatalf("Invalid AUTH0_DOMAIN: %v", err)
		}
		auth0Issuer = issuerURL.String()
		provider := jwks.NewCachingProvider(issuerURL, 5*time.Minute)
		v, err := validator.New(
			provider.KeyFunc,
			validator.RS256,
			auth0Issuer,
			[]string{audience},
			validator.WithCustomClaims(func() validator.CustomClaims { return &CustomClaims{} }),
			validator.WithAllowedClockSkew(time.Minute),
		)
		if err != nil {
			log.Fatalf("Failed to set up the JWT validator: %v", err)
		}
		jwtValidator = v
	})
	return jwtValidator
}

func bearerToken(c echo.Context) string {
	h := c.Request().Header.Get("Authorization")
	if !strings.HasPrefix(h, "Bearer ") {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
}

func validateRequestToken(c echo.Context) error {
	token := bearerToken(c)
	if token == "" {
		return errors.New("missing token")
	}
	v := getValidator()
	if v == nil {
		return errors.New("authentication is not configured")
	}
	parsed, err := v.ValidateToken(c.Request().Context(), token)
	if err != nil {
		return err
	}
	claims := parsed.(*validator.ValidatedClaims)
	c.Set("user", claims)
	return touchUser(claims.RegisteredClaims.Subject)
}

// EnsureValidToken requires a valid Auth0 token and makes sure the user has a row.
func EnsureValidToken() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if err := validateRequestToken(c); err != nil {
				return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Please sign in again."})
			}
			return next(c)
		}
	}
}

// getUserIDFromToken returns the Auth0 subject of the validated token, or "".
func getUserIDFromToken(c echo.Context) string {
	claims, ok := c.Get("user").(*validator.ValidatedClaims)
	if !ok || claims == nil {
		return ""
	}
	return claims.RegisteredClaims.Subject
}

// ── Users ────────────────────────────────────────────────────────────────────

func providerFromSubject(sub string) string {
	switch {
	case strings.HasPrefix(sub, "google-oauth2|"):
		return "google"
	case strings.HasPrefix(sub, "auth0|"):
		return "email"
	case strings.Contains(sub, "|"):
		return strings.SplitN(sub, "|", 2)[0]
	default:
		return "other"
	}
}

// touchUser creates the user's row on first sight and records activity.
func touchUser(sub string) error {
	if sub == "" {
		return errors.New("token has no subject")
	}
	now := time.Now().Unix()
	_, err := db.Exec(`INSERT INTO users(id, provider, created_at, last_seen_at) VALUES(?, ?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET last_seen_at = excluded.last_seen_at
		WHERE users.last_seen_at < excluded.last_seen_at - 60`,
		sub, providerFromSubject(sub), now, now)
	return err
}

type userInfo struct {
	Sub           string `json:"sub"`
	Email         string `json:"email"`
	EmailVerified bool   `json:"email_verified"`
	Name          string `json:"name"`
}

var userInfoClient = &http.Client{Timeout: 6 * time.Second}

// syncProfile fetches the user's email and name from Auth0 /userinfo with their
// own token, at most once a day (or whenever the email is still unknown).
func syncProfile(c echo.Context, sub string) {
	var synced int64
	var email string
	if err := db.QueryRow(`SELECT profile_synced, email FROM users WHERE id = ?`, sub).Scan(&synced, &email); err != nil {
		return
	}
	if email != "" && time.Since(time.Unix(synced, 0)) < 24*time.Hour {
		return
	}
	domain := auth0Domain()
	token := bearerToken(c)
	if domain == "" || token == "" {
		return
	}
	req, _ := http.NewRequestWithContext(c.Request().Context(), "GET", domain+"userinfo", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := userInfoClient.Do(req)
	if err != nil {
		log.Printf("[AUTH] userinfo failed: %v", err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		log.Printf("[AUTH] userinfo returned HTTP %d", resp.StatusCode)
		return
	}
	var info userInfo
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil || info.Sub != sub {
		return
	}
	_, err = db.Exec(`UPDATE users SET email = ?, email_verified = ?, name = ?, profile_synced = ? WHERE id = ?`,
		strings.ToLower(strings.TrimSpace(info.Email)), boolInt(info.EmailVerified),
		strings.TrimSpace(info.Name), time.Now().Unix(), sub)
	if err != nil {
		log.Printf("[AUTH] saving profile: %v", err)
	}
}

func adminEmails() map[string]bool {
	raw := os.Getenv("ADMIN_EMAILS")
	if raw == "" {
		raw = os.Getenv("ADMIN_EMAIL") // older .env files
	}
	if raw == "" {
		raw = DefaultAdminEmails
	}
	out := map[string]bool{}
	for _, e := range strings.Split(raw, ",") {
		if e = strings.ToLower(strings.TrimSpace(e)); e != "" {
			out[e] = true
		}
	}
	return out
}

// isAdmin: a verified email from Auth0 that is listed in ADMIN_EMAILS.
func isAdmin(c echo.Context) bool {
	sub := getUserIDFromToken(c)
	if sub == "" {
		return false
	}
	syncProfile(c, sub)
	var email string
	var verified int
	if err := db.QueryRow(`SELECT email, email_verified FROM users WHERE id = ?`, sub).Scan(&email, &verified); err != nil {
		return false
	}
	return verified == 1 && adminEmails()[email]
}

// RequireAdmin must run after EnsureValidToken.
func RequireAdmin() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if !isAdmin(c) {
				return c.JSON(http.StatusForbidden, map[string]string{"error": "This area is for administrators only."})
			}
			return next(c)
		}
	}
}

func adminEmailOf(c echo.Context) string {
	var email string
	db.QueryRow(`SELECT email FROM users WHERE id = ?`, getUserIDFromToken(c)).Scan(&email)
	return email
}

func auditAdmin(c echo.Context, action, target, detail string) {
	db.Exec(`INSERT INTO admin_audit(at, admin_email, action, target, detail) VALUES(?, ?, ?, ?, ?)`,
		time.Now().Unix(), adminEmailOf(c), action, target, detail)
}

// ── Mirror access ────────────────────────────────────────────────────────────
//
// Mirrors have no user to sign in as, so they prove themselves with a shared
// secret: MIRROR_API_KEY in the server's .env, the same value in each mirror's
// environment, sent as X-Mirror-Key. Face vectors, timetables and dashboards
// are only handed out to a mirror (or to the signed-in owner).

var warnMirrorKeyOnce sync.Once

func mirrorKeyValid(c echo.Context) bool {
	want := os.Getenv("MIRROR_API_KEY")
	if want == "" || want == "change-me-to-a-random-secret" {
		warnMirrorKeyOnce.Do(func() {
			log.Println("WARNING: MIRROR_API_KEY is not set — mirror endpoints (face index, dashboards) are open to anyone. Set it in .env and on each mirror.")
		})
		return true
	}
	got := c.Request().Header.Get("X-Mirror-Key")
	return subtle.ConstantTimeCompare([]byte(got), []byte(want)) == 1
}

func RequireMirror() echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if !mirrorKeyValid(c) {
				return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Unknown mirror"})
			}
			return next(c)
		}
	}
}

// userExists reports whether a user row exists.
func userExists(id string) bool {
	var one int
	return db.QueryRow(`SELECT 1 FROM users WHERE id = ?`, id).Scan(&one) == nil
}

func notFoundOr(err error, msg string) string {
	if errors.Is(err, sql.ErrNoRows) {
		return msg
	}
	return fmt.Sprintf("%s (%v)", msg, err)
}
