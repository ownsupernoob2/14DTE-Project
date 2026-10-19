package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/labstack/echo/v4"
)

var (
	refreshMutex sync.Mutex
	lastRefresh  time.Time
)

// triggerServerRefresh runs notice and content scraping in the background.
// It uses a mutex and brief debounce to prevent overlapping duplicate fetches.
func triggerServerRefresh(source string) {
	go func() {
		refreshMutex.Lock()
		defer refreshMutex.Unlock()

		// Debounce: if refreshed less than 5 seconds ago, skip
		if time.Since(lastRefresh) < 5*time.Second {
			log.Printf("[refresh] Trigger from %s skipped (already refreshed %v ago)", source, time.Since(lastRefresh))
			return
		}
		lastRefresh = time.Now()

		log.Printf("[refresh] Starting server content refresh (triggered by %s)...", source)

		// 1. Redo Daily Notices pull
		if err := fetchNoticesLogic(); err != nil {
			log.Printf("[refresh] Daily notices pull failed: %v", err)
		} else {
			log.Println("[refresh] Daily notices successfully re-pulled and cached.")
		}

		// 2. Redo King's Week pull
		if err := fetchKingsWeekLogic(); err != nil {
			log.Printf("[refresh] Kings Week pull failed: %v", err)
		} else {
			log.Println("[refresh] Kings Week successfully re-pulled and cached.")
		}

		log.Printf("[refresh] Content refresh complete for trigger: %s", source)
	}()
}

// verifyGitHubSignature checks HMAC-SHA256 signature if GITHUB_WEBHOOK_SECRET is configured.
func verifyGitHubSignature(secret, signatureHeader string, body []byte) bool {
	if secret == "" {
		// If no secret is configured, allow the webhook
		return true
	}

	if !strings.HasPrefix(signatureHeader, "sha256=") {
		return false
	}

	actualSigHex := strings.TrimPrefix(signatureHeader, "sha256=")
	actualSig, err := hex.DecodeString(actualSigHex)
	if err != nil {
		return false
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(body)
	expectedSig := mac.Sum(nil)

	return hmac.Equal(actualSig, expectedSig)
}

// handleGitHubWebhook processes webhook events sent by GitHub on repo push.
// Route: POST /api/webhook/github
func handleGitHubWebhook(c echo.Context) error {
	secret := os.Getenv("GITHUB_WEBHOOK_SECRET")

	body, err := io.ReadAll(c.Request().Body)
	if err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Failed to read request body"})
	}

	// Validate HMAC signature if secret is set
	if secret != "" {
		sigHeader := c.Request().Header.Get("X-Hub-Signature-256")
		if !verifyGitHubSignature(secret, sigHeader, body) {
			log.Println("[webhook] Invalid GitHub signature received")
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "Invalid signature"})
		}
	}

	event := c.Request().Header.Get("X-GitHub-Event")
	if event == "" {
		event = "push"
	}

	// Respond to ping event immediately
	if event == "ping" {
		log.Println("[webhook] Received GitHub ping event. Webhook is connected successfully.")
		return c.JSON(http.StatusOK, map[string]string{"status": "pong", "message": "Webhook connection active"})
	}

	// Extract pusher / ref information if available
	var payload struct {
		Ref        string `json:"ref"`
		Repository struct {
			FullName string `json:"full_name"`
		} `json:"repository"`
		Pusher struct {
			Name  string `json:"name"`
			Email string `json:"email"`
		} `json:"pusher"`
	}
	_ = json.Unmarshal(body, &payload)

	repoInfo := payload.Repository.FullName
	if repoInfo == "" {
		repoInfo = "repository"
	}
	pusher := payload.Pusher.Name
	if pusher == "" {
		pusher = "github"
	}

	log.Printf("[webhook] GitHub '%s' event received for %s from %s (ref: %s)", event, repoInfo, pusher, payload.Ref)

	// Trigger notice pull and data refresh in the background
	triggerServerRefresh("github-webhook:" + event)

	return c.JSON(http.StatusOK, map[string]interface{}{
		"status":  "ok",
		"message": "Notice pull and content refresh triggered",
		"event":   event,
		"ref":     payload.Ref,
	})
}

// handleDeployWebhook allows deployment workflows or local scripts to trigger a refresh.
// Route: POST /api/webhook/deploy
func handleDeployWebhook(c echo.Context) error {
	triggerServerRefresh("deploy-script")
	return c.JSON(http.StatusOK, map[string]string{
		"status":  "ok",
		"message": "Notice pull and content refresh triggered by deploy",
	})
}

// handleRefreshAll is a simple endpoint to manually trigger a refresh of notices and King's Week.
// Route: POST /api/refresh and GET /api/refresh
func handleRefreshAll(c echo.Context) error {
	triggerServerRefresh("manual-refresh-endpoint")
	return c.JSON(http.StatusOK, map[string]string{
		"status":  "ok",
		"message": "Notice pull and content refresh triggered",
	})
}
