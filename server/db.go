package main

// db.go — the server's single SQLite database.
//
// Everything that belongs to a user (profile, student ID, face encodings,
// dashboard layout, language, timetable link), every mirror session, the
// timetables KAMAR sends, and all admin settings live here. Users authenticate with Auth0; the database only
// keys rows by the Auth0 subject ("google-oauth2|…", "auth0|…") and never holds
// a password.
//
// SQLite through modernc.org/sqlite is pure Go, so the Windows build the
// updater runs needs no C compiler.

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

var db *sql.DB

const schemaVersion = 1

const schemaSQL = `
CREATE TABLE IF NOT EXISTS users (
	id             TEXT PRIMARY KEY,              -- Auth0 subject
	email          TEXT NOT NULL DEFAULT '',
	email_verified INTEGER NOT NULL DEFAULT 0,
	name           TEXT NOT NULL DEFAULT '',
	provider       TEXT NOT NULL DEFAULT '',      -- google | email | other
	language       TEXT NOT NULL DEFAULT 'en-NZ',
	ics_url        TEXT NOT NULL DEFAULT '',
	barcode        TEXT UNIQUE,                   -- normalised student ID, NULL when unset
	dashboard      TEXT NOT NULL DEFAULT '',      -- JSON UserDashboardConfig
	created_at     INTEGER NOT NULL,
	last_seen_at   INTEGER NOT NULL,
	profile_synced INTEGER NOT NULL DEFAULT 0     -- when email/name were last fetched from Auth0
);
CREATE INDEX IF NOT EXISTS users_email ON users(email);

CREATE TABLE IF NOT EXISTS faces (
	user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
	encodings  TEXT NOT NULL,                     -- JSON [[128 floats], ...]
	frames     INTEGER NOT NULL,
	trained_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS face_collisions (
	id             INTEGER PRIMARY KEY AUTOINCREMENT,
	at             INTEGER NOT NULL,
	attempted_user TEXT NOT NULL,
	matched_user   TEXT NOT NULL,
	distance       REAL NOT NULL
);

-- Shown to a user the next time they sign in, e.g. "your face scan was removed".
-- Keyed by email as well as user ID so a deleted account still hears about it.
CREATE TABLE IF NOT EXISTS user_messages (
	id         INTEGER PRIMARY KEY AUTOINCREMENT,
	user_id    TEXT NOT NULL DEFAULT '',
	email      TEXT NOT NULL DEFAULT '',
	message    TEXT NOT NULL,
	created_at INTEGER NOT NULL,
	seen_at    INTEGER
);
CREATE INDEX IF NOT EXISTS user_messages_user ON user_messages(user_id);
CREATE INDEX IF NOT EXISTS user_messages_email ON user_messages(email);

CREATE TABLE IF NOT EXISTS sessions (
	id                     TEXT PRIMARY KEY,
	user_id                TEXT,                 -- NULL for guests (and after the user is deleted)
	mirror_id              TEXT NOT NULL DEFAULT '',
	mirror_version         TEXT NOT NULL DEFAULT '',
	variant                TEXT NOT NULL,
	session_type           TEXT NOT NULL,
	auth_method            TEXT NOT NULL DEFAULT '',
	screensaver_mode       TEXT NOT NULL DEFAULT '',
	duration_sec           REAL NOT NULL DEFAULT 0,
	time_to_auth_sec       REAL NOT NULL DEFAULT 0,
	has_gesture            INTEGER NOT NULL DEFAULT 0,
	time_to_first_gesture  REAL NOT NULL DEFAULT 0,
	hand_seen              INTEGER NOT NULL DEFAULT 0,
	scroll_count           INTEGER NOT NULL DEFAULT 0,
	tap_count              INTEGER NOT NULL DEFAULT 0,
	timetable_toggles      INTEGER NOT NULL DEFAULT 0,
	dwell_completed        INTEGER NOT NULL DEFAULT 0,
	dwell_abandoned        INTEGER NOT NULL DEFAULT 0,
	article_opens          INTEGER NOT NULL DEFAULT 0,
	notice_opens           INTEGER NOT NULL DEFAULT 0,
	modal_read_sec         REAL NOT NULL DEFAULT 0,
	kings_expands          INTEGER NOT NULL DEFAULT 0,
	tutorial_shown         INTEGER NOT NULL DEFAULT 0,
	tutorial_dismissed     INTEGER NOT NULL DEFAULT 0,
	practice_shown         INTEGER NOT NULL DEFAULT 0,   -- A/B variant B's hands-on practice
	practice_completed     INTEGER NOT NULL DEFAULT 0,
	practice_skipped       INTEGER NOT NULL DEFAULT 0,
	practice_steps         INTEGER NOT NULL DEFAULT 0,
	practice_sec           REAL NOT NULL DEFAULT 0,
	after_teaser           INTEGER NOT NULL DEFAULT 0,   -- grew out of a brief encounter's hint
	from_screensaver       INTEGER NOT NULL DEFAULT 0,
	client_started_at      REAL NOT NULL DEFAULT 0,
	created_at             INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_created ON sessions(created_at);

CREATE TABLE IF NOT EXISTS settings (
	key        TEXT PRIMARY KEY,
	value      TEXT NOT NULL,
	updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS screensaver_images (
	id           INTEGER PRIMARY KEY AUTOINCREMENT,
	kind         TEXT NOT NULL,                  -- slide | logo
	sha256       TEXT NOT NULL,
	ext          TEXT NOT NULL,
	content_type TEXT NOT NULL,
	size         INTEGER NOT NULL,
	position     INTEGER NOT NULL DEFAULT 0,
	created_at   INTEGER NOT NULL
);

-- Timetables KAMAR pushes to /api/kamar, one ICS calendar per student.
-- Keyed by the normalised KAMAR ID, which is the number on the student ID card.
CREATE TABLE IF NOT EXISTS kamar_timetables (
	student_id TEXT PRIMARY KEY,
	ics        TEXT NOT NULL,
	grid       TEXT NOT NULL DEFAULT '',          -- timetable year, e.g. 2026TT
	updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_audit (
	id          INTEGER PRIMARY KEY AUTOINCREMENT,
	at          INTEGER NOT NULL,
	admin_email TEXT NOT NULL,
	action      TEXT NOT NULL,
	target      TEXT NOT NULL DEFAULT '',
	detail      TEXT NOT NULL DEFAULT ''
);
`

func dataPath(parts ...string) string {
	return filepath.Join(append([]string{"data"}, parts...)...)
}

// openDatabase opens (creating if needed) data/smartmirror.db. path is
// overridable for tests.
func openDatabase(path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	_, statErr := os.Stat(path)
	fresh := os.IsNotExist(statErr)

	dsn := "file:" + filepath.ToSlash(path) +
		"?_pragma=foreign_keys(1)&_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=synchronous(NORMAL)"
	conn, err := sql.Open("sqlite", dsn)
	if err != nil {
		return err
	}
	conn.SetMaxOpenConns(1) // SQLite has one writer; serialising here avoids SQLITE_BUSY
	if _, err := conn.Exec(schemaSQL); err != nil {
		conn.Close()
		return fmt.Errorf("creating schema: %w", err)
	}
	db = conn
	if err := addMissingColumns(); err != nil {
		conn.Close()
		return fmt.Errorf("updating schema: %w", err)
	}
	if fresh {
		setSetting("schema_version", schemaVersion)
		wipeLegacyData()
	}
	return nil
}

// Columns added after the first release. CREATE TABLE IF NOT EXISTS leaves an
// existing table alone, so a database made before them gets them here; nothing
// is wiped.
var addedColumns = []struct{ table, column, def string }{
	{"sessions", "practice_shown", "INTEGER NOT NULL DEFAULT 0"},
	{"sessions", "practice_completed", "INTEGER NOT NULL DEFAULT 0"},
	{"sessions", "practice_skipped", "INTEGER NOT NULL DEFAULT 0"},
	{"sessions", "practice_steps", "INTEGER NOT NULL DEFAULT 0"},
	{"sessions", "practice_sec", "REAL NOT NULL DEFAULT 0"},
	{"sessions", "after_teaser", "INTEGER NOT NULL DEFAULT 0"},
}

func addMissingColumns() error {
	for _, c := range addedColumns {
		var n int
		if err := db.QueryRow(`SELECT COUNT(*) FROM pragma_table_info(?) WHERE name = ?`, c.table, c.column).Scan(&n); err != nil {
			return err
		}
		if n == 0 {
			if _, err := db.Exec(fmt.Sprintf(`ALTER TABLE %s ADD COLUMN %s %s`, c.table, c.column, c.def)); err != nil {
				return err
			}
		}
	}
	return nil
}

// wipeLegacyData deletes everything the file-based server stored before the
// database existed: user files, face encodings, analytics. Runs once, when the
// database is first created — the fresh start the school asked for.
func wipeLegacyData() {
	removed := 0
	remove := func(path string) {
		if err := os.RemoveAll(path); err == nil {
			removed++
		}
	}
	userFileSuffixes := []string{"_barcode.txt", "_widgets.json", "_language.txt", "_ics_url.txt"}
	if entries, err := os.ReadDir("data"); err == nil {
		for _, e := range entries {
			name := e.Name()
			for _, suffix := range userFileSuffixes {
				if strings.HasSuffix(name, suffix) {
					remove(dataPath(name))
				}
			}
		}
	}
	for _, name := range []string{"analytics_events.json", "face_collisions.json", "admin_banner.json", "notices_config.json"} {
		if _, err := os.Stat(dataPath(name)); err == nil {
			remove(dataPath(name))
		}
	}
	for _, dir := range []string{"encodings", "faces", "temp"} {
		if entries, err := os.ReadDir(dir); err == nil {
			for _, e := range entries {
				remove(filepath.Join(dir, e.Name()))
			}
		}
	}
	if removed > 0 {
		log.Printf("[DB] New database: removed %d files of legacy user and analytics data", removed)
	}
}

// ── Settings (JSON values) ───────────────────────────────────────────────────

func getSetting(key string, out interface{}) bool {
	var raw string
	if err := db.QueryRow(`SELECT value FROM settings WHERE key = ?`, key).Scan(&raw); err != nil {
		return false
	}
	return json.Unmarshal([]byte(raw), out) == nil
}

func setSetting(key string, value interface{}) error {
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	_, err = db.Exec(`INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)
		ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
		key, string(raw), time.Now().Unix())
	return err
}

func boolInt(b bool) int {
	if b {
		return 1
	}
	return 0
}
