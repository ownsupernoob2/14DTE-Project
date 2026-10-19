package main

import (
	"log"
	"os"
	"os/exec"
	"strings"
	"time"
)

// StartAutoGitPuller periodically runs git pull to check for updates from GitHub.
// When changes are detected and pulled, it immediately re-pulls and updates notices.
func StartAutoGitPuller() {
	if os.Getenv("AUTO_PULL") == "false" {
		log.Println("[autopull] Git auto-pull is disabled (AUTO_PULL=false)")
		return
	}

	// Default polling interval: 30 seconds
	interval := 30 * time.Second
	if val := os.Getenv("AUTO_PULL_INTERVAL_SECONDS"); val != "" {
		if d, err := time.ParseDuration(val + "s"); err == nil && d >= 5*time.Second {
			interval = d
		}
	}

	go func() {
		log.Printf("[autopull] Background git auto-puller started (checking GitHub every %v)...", interval)

		// Check if git is available
		if _, err := exec.LookPath("git"); err != nil {
			log.Println("[autopull] 'git' command not found; auto-pull disabled.")
			return
		}

		// Initial warm-up delay on startup
		time.Sleep(10 * time.Second)

		for {
			time.Sleep(interval)

			// Execute git pull
			cmd := exec.Command("git", "pull")
			outputBytes, err := cmd.CombinedOutput()
			if err != nil {
				// Not a git repository or network/auth issue; continue quietly
				continue
			}

			output := strings.TrimSpace(string(outputBytes))
			if output != "" &&
				!strings.Contains(output, "Already up to date.") &&
				!strings.Contains(output, "Already up-to-date.") &&
				!strings.Contains(output, "Current branch main is up to date.") {
				log.Printf("[autopull] Pulled new changes from GitHub: %s", output)
				log.Println("[autopull] Automatically updating daily notices and content...")

				triggerServerRefresh("git-autopull")
			}
		}
	}()
}
