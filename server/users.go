package main

import (
	"database/sql"
	"net/http"
	"time"

	"github.com/labstack/echo/v4"
)

type userMessage struct {
	ID        int64  `json:"id"`
	Message   string `json:"message"`
	CreatedAt int64  `json:"created_at"`
}

// GET /api/users/me — the signed-in user, whether they are an admin, and any
// messages waiting for them (e.g. "your student ID was removed").
func getCurrentUser(c echo.Context) error {
	sub := getUserIDFromToken(c)
	syncProfile(c, sub)

	var email, name, provider, language string
	var barcode sql.NullString
	var created int64
	err := db.QueryRow(`SELECT email, name, provider, language, barcode, created_at FROM users WHERE id = ?`, sub).
		Scan(&email, &name, &provider, &language, &barcode, &created)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not load your account"})
	}
	var hasFace int
	db.QueryRow(`SELECT COUNT(*) FROM faces WHERE user_id = ?`, sub).Scan(&hasFace)

	messages := []userMessage{}
	rows, err := db.Query(`SELECT id, message, created_at FROM user_messages
		WHERE seen_at IS NULL AND (user_id = ? OR (user_id = '' AND email != '' AND email = ?))
		ORDER BY created_at`, sub, email)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var m userMessage
			if rows.Scan(&m.ID, &m.Message, &m.CreatedAt) == nil {
				messages = append(messages, m)
			}
		}
	}

	return c.JSON(http.StatusOK, map[string]interface{}{
		"id":            sub,
		"email":         email,
		"name":          name,
		"provider":      provider,
		"language":      language,
		"has_face":      hasFace > 0,
		"has_barcode":   barcode.Valid && barcode.String != "",
		"is_admin":      isAdmin(c),
		"created_at":    created,
		"messages":      messages,
		"contact_email": ContactEmail,
	})
}

// POST /api/users/me/messages/seen — dismiss the messages the user has read.
func markMessagesSeen(c echo.Context) error {
	sub := getUserIDFromToken(c)
	var email string
	db.QueryRow(`SELECT email FROM users WHERE id = ?`, sub).Scan(&email)
	_, err := db.Exec(`UPDATE user_messages SET seen_at = ?
		WHERE seen_at IS NULL AND (user_id = ? OR (user_id = '' AND email != '' AND email = ?))`,
		time.Now().Unix(), sub, email)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not update messages"})
	}
	return c.JSON(http.StatusOK, map[string]string{"status": "ok"})
}

// notifyUser queues a message the user will see next time they open the site.
func notifyUser(userID, email, message string) {
	db.Exec(`INSERT INTO user_messages(user_id, email, message, created_at) VALUES(?, ?, ?, ?)`,
		userID, email, message, time.Now().Unix())
}

// DELETE /api/users/me/data — the student wipes everything they have given us:
// face scan, student ID, timetable link, mirror layout and language.
func deleteMyData(c echo.Context) error {
	sub := getUserIDFromToken(c)
	tx, err := db.Begin()
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete your data"})
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`DELETE FROM faces WHERE user_id = ?`, sub); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete your data"})
	}
	if _, err := tx.Exec(`UPDATE users SET barcode = NULL, ics_url = '', dashboard = '', language = 'en-NZ' WHERE id = ?`, sub); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete your data"})
	}
	if err := tx.Commit(); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete your data"})
	}
	return c.JSON(http.StatusOK, map[string]string{"message": "Your data was deleted"})
}
