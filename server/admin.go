package main

// admin.go — the admin's view of who has signed up, and removing their data.

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/labstack/echo/v4"
)

type adminUserRow struct {
	ID            string `json:"id"`
	Email         string `json:"email"`
	Name          string `json:"name"`
	Provider      string `json:"provider"`
	HasBarcode    bool   `json:"has_barcode"`
	Barcode       string `json:"barcode"`
	HasFace       bool   `json:"has_face"`
	FaceTrainedAt int64  `json:"face_trained_at"`
	HasTimetable  bool   `json:"has_timetable"`
	Sessions      int    `json:"sessions"`
	LastSessionAt int64  `json:"last_session_at"`
	CreatedAt     int64  `json:"created_at"`
	LastSeenAt    int64  `json:"last_seen_at"`
}

// GET /api/admin/users?q= — everyone who has signed up, newest first.
// q matches name, email, student ID or user ID.
func adminListUsers(c echo.Context) error {
	q := strings.ToLower(strings.TrimSpace(c.QueryParam("q")))
	like := "%" + strings.NewReplacer(`\`, `\\`, "%", `\%`, "_", `\_`).Replace(q) + "%"
	rows, err := db.Query(`
		SELECT u.id, u.email, u.name, u.provider, COALESCE(u.barcode, ''), u.ics_url != '',
		       COALESCE(f.trained_at, 0), u.created_at, u.last_seen_at,
		       (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id),
		       (SELECT COALESCE(MAX(created_at), 0) FROM sessions s WHERE s.user_id = u.id)
		FROM users u LEFT JOIN faces f ON f.user_id = u.id
		WHERE ? = '' OR lower(u.email) LIKE ? ESCAPE '\' OR lower(u.name) LIKE ? ESCAPE '\'
		      OR lower(COALESCE(u.barcode, '')) LIKE ? ESCAPE '\' OR lower(u.id) LIKE ? ESCAPE '\'
		ORDER BY u.created_at DESC`, q, like, like, like, like)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not list users"})
	}
	defer rows.Close()
	users := []adminUserRow{}
	for rows.Next() {
		var u adminUserRow
		var hasTT int
		if err := rows.Scan(&u.ID, &u.Email, &u.Name, &u.Provider, &u.Barcode, &hasTT, &u.FaceTrainedAt,
			&u.CreatedAt, &u.LastSeenAt, &u.Sessions, &u.LastSessionAt); err != nil {
			continue
		}
		u.HasBarcode, u.HasFace, u.HasTimetable = u.Barcode != "", u.FaceTrainedAt > 0, hasTT == 1
		users = append(users, u)
	}

	var total, withFace, withBarcode int
	db.QueryRow(`SELECT COUNT(*), COALESCE(SUM(barcode IS NOT NULL), 0) FROM users`).Scan(&total, &withBarcode)
	db.QueryRow(`SELECT COUNT(*) FROM faces`).Scan(&withFace)
	return c.JSON(http.StatusOK, map[string]interface{}{
		"users": users,
		"totals": map[string]int{
			"users": total, "with_face": withFace, "with_barcode": withBarcode,
		},
	})
}

func removalMessage(what string) string {
	return fmt.Sprintf("Your %s was removed from Smart Mirror by an administrator. If this is a mistake, contact %s.", what, ContactEmail)
}

// DELETE /api/admin/users/:id/:kind — kind is face | barcode | timetable | dashboard.
func adminRemoveUserData(c echo.Context) error {
	id, _ := url.PathUnescape(c.Param("id"))
	kind := c.Param("kind")
	var email string
	if err := db.QueryRow(`SELECT email FROM users WHERE id = ?`, id).Scan(&email); err != nil {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No such user"})
	}

	var res sql.Result
	var err error
	var what string
	switch kind {
	case "face":
		res, err = db.Exec(`DELETE FROM faces WHERE user_id = ?`, id)
		what = "face scan"
	case "barcode":
		res, err = db.Exec(`UPDATE users SET barcode = NULL WHERE id = ? AND barcode IS NOT NULL`, id)
		what = "student ID"
	case "timetable":
		res, err = db.Exec(`UPDATE users SET ics_url = '' WHERE id = ? AND ics_url != ''`, id)
		what = "timetable link"
	case "dashboard":
		res, err = db.Exec(`UPDATE users SET dashboard = '' WHERE id = ? AND dashboard != ''`, id)
		what = "mirror layout"
	default:
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Unknown data type"})
	}
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not remove it"})
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "That user has no " + what})
	}
	notifyUser(id, "", removalMessage(what))
	auditAdmin(c, "remove_"+kind, id, email)
	return c.JSON(http.StatusOK, map[string]string{"message": strings.ToUpper(what[:1]) + what[1:] + " removed. The user will be told next time they sign in."})
}

// DELETE /api/admin/users/:id — delete the account and everything linked to it.
// Their past mirror sessions stay in analytics, no longer tied to them.
func adminDeleteUser(c echo.Context) error {
	id, _ := url.PathUnescape(c.Param("id"))
	if id == getUserIDFromToken(c) {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "You can't delete your own admin account here."})
	}
	var email string
	if err := db.QueryRow(`SELECT email FROM users WHERE id = ?`, id).Scan(&email); err != nil {
		return c.JSON(http.StatusNotFound, map[string]string{"error": "No such user"})
	}

	tx, err := db.Begin()
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete user"})
	}
	defer tx.Rollback()
	for _, stmt := range []string{
		`UPDATE sessions SET user_id = NULL WHERE user_id = ?`,
		`DELETE FROM user_messages WHERE user_id = ?`,
		`DELETE FROM faces WHERE user_id = ?`,
		`DELETE FROM users WHERE id = ?`,
	} {
		if _, err := tx.Exec(stmt, id); err != nil {
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete user"})
		}
	}
	if err := tx.Commit(); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not delete user"})
	}

	// If they sign up again with the same email, tell them what happened.
	if email != "" {
		notifyUser("", email, removalMessage("account and all its data (face scan, student ID, timetable and layout)"))
	}
	auth0Note := deleteAuth0User(id)
	auditAdmin(c, "delete_user", id, email+" "+auth0Note)
	return c.JSON(http.StatusOK, map[string]string{"message": "User deleted. " + auth0Note})
}

// GET /api/admin/face-audit — duplicate-face attempts.
func getFaceAuditLog(c echo.Context) error {
	rows, err := db.Query(`SELECT c.at, c.attempted_user, COALESCE(a.email, ''), c.matched_user, COALESCE(m.email, ''), c.distance
		FROM face_collisions c
		LEFT JOIN users a ON a.id = c.attempted_user
		LEFT JOIN users m ON m.id = c.matched_user
		ORDER BY c.at DESC LIMIT 200`)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not read the audit log"})
	}
	defer rows.Close()
	collisions := []map[string]interface{}{}
	for rows.Next() {
		var at int64
		var attempted, attemptedEmail, matched, matchedEmail string
		var dist float64
		if rows.Scan(&at, &attempted, &attemptedEmail, &matched, &matchedEmail, &dist) != nil {
			continue
		}
		collisions = append(collisions, map[string]interface{}{
			"timestamp":      time.Unix(at, 0).UTC().Format(time.RFC3339),
			"attempted_user": firstNonEmpty(attemptedEmail, attempted),
			"matched_user":   firstNonEmpty(matchedEmail, matched),
			"min_distance":   math2(dist),
			"action":         "BLOCKED",
			"contact_email":  ContactEmail,
		})
	}
	var enrolled int
	db.QueryRow(`SELECT COUNT(*) FROM faces`).Scan(&enrolled)
	return c.JSON(http.StatusOK, map[string]interface{}{
		"total_enrolled": enrolled,
		"collisions":     collisions,
		"contact_email":  ContactEmail,
	})
}

func math2(v float64) float64 { return float64(int(v*10000+0.5)) / 10000 }

// ── Auth0 Management API (optional) ─────────────────────────────────────────
//
// With AUTH0_MGMT_CLIENT_ID / AUTH0_MGMT_CLIENT_SECRET set (a machine-to-machine
// app allowed the delete:users scope), deleting a user here also removes their
// Auth0 login. Without them, only the Smart Mirror data is deleted.

var (
	mgmtMu      sync.Mutex
	mgmtToken   string
	mgmtExpires time.Time
)

func auth0ManagementToken() (string, error) {
	mgmtMu.Lock()
	defer mgmtMu.Unlock()
	if mgmtToken != "" && time.Now().Before(mgmtExpires) {
		return mgmtToken, nil
	}
	id, secret := os.Getenv("AUTH0_MGMT_CLIENT_ID"), os.Getenv("AUTH0_MGMT_CLIENT_SECRET")
	domain := auth0Domain()
	if id == "" || secret == "" || domain == "" {
		return "", fmt.Errorf("not configured")
	}
	form := url.Values{
		"grant_type":    {"client_credentials"},
		"client_id":     {id},
		"client_secret": {secret},
		"audience":      {domain + "api/v2/"},
	}
	resp, err := userInfoClient.PostForm(domain+"oauth/token", form)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	var body struct {
		AccessToken string `json:"access_token"`
		ExpiresIn   int    `json:"expires_in"`
	}
	if resp.StatusCode != 200 || json.NewDecoder(resp.Body).Decode(&body) != nil || body.AccessToken == "" {
		return "", fmt.Errorf("token request returned HTTP %d", resp.StatusCode)
	}
	mgmtToken = body.AccessToken
	mgmtExpires = time.Now().Add(time.Duration(body.ExpiresIn-60) * time.Second)
	return mgmtToken, nil
}

func deleteAuth0User(id string) string {
	token, err := auth0ManagementToken()
	if err != nil {
		return "Their Auth0 login was kept (Auth0 management access is not configured)."
	}
	req, _ := http.NewRequest("DELETE", auth0Domain()+"api/v2/users/"+url.PathEscape(id), nil)
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := userInfoClient.Do(req)
	if err != nil {
		log.Printf("[ADMIN] Auth0 delete %s: %v", id, err)
		return "Their Auth0 login could not be deleted; remove it in the Auth0 dashboard."
	}
	resp.Body.Close()
	if resp.StatusCode != 204 && resp.StatusCode != 200 && resp.StatusCode != 404 {
		log.Printf("[ADMIN] Auth0 delete %s: HTTP %d", id, resp.StatusCode)
		return "Their Auth0 login could not be deleted; remove it in the Auth0 dashboard."
	}
	return "Their Auth0 login was deleted too."
}
