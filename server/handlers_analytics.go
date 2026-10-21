package main

import (
	"database/sql"
	"math"
	"net/http"
	"strings"
	"time"

	"github.com/labstack/echo/v4"
)

// SessionAnalyticsEvent is one mirror session, sent by the mirror when it ends.
type SessionAnalyticsEvent struct {
	SessionID            string  `json:"session_id"`
	UserID               string  `json:"user_id,omitempty"`
	MirrorID             string  `json:"mirror_id,omitempty"`
	MirrorVersion        string  `json:"mirror_version,omitempty"`
	ClientTimestamp      float64 `json:"client_timestamp"`
	Variant              string  `json:"variant"`      // "A" or "B"
	SessionType          string  `json:"session_type"` // "user", "guest", or "passerby" (got the teaser, walked on)
	AuthMethod           string  `json:"auth_method"`  // "face", "barcode", "presence"
	ScreensaverMode      string  `json:"screensaver_mode,omitempty"`
	DurationSec          float64 `json:"duration_sec"`
	TimeToAuthSec        float64 `json:"time_to_auth_sec"`
	HasGesture           bool    `json:"has_gesture"`
	TimeToFirstGesture   float64 `json:"time_to_first_gesture_sec"`
	HandSeen             bool    `json:"hand_seen"`
	GestureScrollCount   int     `json:"gesture_scroll_count"`
	GestureTapCount      int     `json:"gesture_tap_count"`
	TimetableToggleCount int     `json:"timetable_toggle_count"`
	DwellCompletedCount  int     `json:"dwell_completed_count"`
	DwellAbandonedCount  int     `json:"dwell_abandoned_count"`
	ArticleModalOpens    int     `json:"article_modal_opens"`
	NoticeOpens          int     `json:"notice_opens"`
	ModalReadTimeSec     float64 `json:"modal_read_time_sec"`
	KingsExpands         int     `json:"kings_expands"`
	TutorialShown        int     `json:"tutorial_shown"`
	TutorialDismissed    int     `json:"tutorial_dismissed"`
	PracticeShown        int     `json:"practice_shown"`
	PracticeCompleted    int     `json:"practice_completed"`
	PracticeSkipped      int     `json:"practice_skipped"`
	PracticeSteps        int     `json:"practice_steps"`
	PracticeSec          float64 `json:"practice_sec"`
	AfterTeaser          bool    `json:"after_teaser"`
	FromScreensaver      bool    `json:"from_screensaver"`
	CreatedAt            string  `json:"created_at"`
}

type VariantStats struct {
	TotalSessions       int     `json:"total_sessions"`
	SessionsWithGesture int     `json:"sessions_with_gesture"`
	GestureAdoptionRate float64 `json:"gesture_adoption_rate"` // %
	ZeroInteractionRate float64 `json:"zero_interaction_rate"` // % sessions with no gesture
	HandSeenRate        float64 `json:"hand_seen_rate"`        // % sessions where a hand was raised at all
	TimetableToggles    int     `json:"timetable_toggles"`
	TimetableToggleRate float64 `json:"timetable_toggle_rate"`
	AvgDurationSec      float64 `json:"avg_duration_sec"`
	AvgTimeToFirstGest  float64 `json:"avg_time_to_first_gesture_sec"`
	TotalScrollCount    int     `json:"total_scroll_count"`
	TotalTapCount       int     `json:"total_tap_count"`
	DwellCompletedCount int     `json:"dwell_completed_count"`
	DwellAbandonedCount int     `json:"dwell_abandoned_count"`
	DwellSuccessRate    float64 `json:"dwell_success_rate"`
	ArticleModalOpens   int     `json:"article_modal_opens"`
	NoticeOpens         int     `json:"notice_opens"`
	AvgModalReadSec     float64 `json:"avg_modal_read_sec"`
	KingsExpands        int     `json:"kings_expands"`
	TutorialShown       int     `json:"tutorial_shown"`
	TutorialDismissed   int     `json:"tutorial_dismissed"`
	TutorialDismissRate float64 `json:"tutorial_dismiss_rate"`
	// Variant B's practice
	PracticeShown          int     `json:"practice_shown"`
	PracticeCompleted      int     `json:"practice_completed"`
	PracticeSkipped        int     `json:"practice_skipped"`
	PracticeCompletionRate float64 `json:"practice_completion_rate"`
	AvgPracticeSec         float64 `json:"avg_practice_sec"`
	// Brief encounters: how many people who got the hint stayed for a visit
	Passersby            int     `json:"passersby"`
	TeaserVisits         int     `json:"teaser_visits"`
	TeaserConversionRate float64 `json:"teaser_conversion_rate"`
}

type AnalyticsSummaryResponse struct {
	TotalSessions       int                     `json:"total_sessions"`
	UserSessions        int                     `json:"user_sessions"`
	GuestSessions       int                     `json:"guest_sessions"`
	AvgUserDurationSec  float64                 `json:"avg_user_duration_sec"`
	AvgGuestDurationSec float64                 `json:"avg_guest_duration_sec"`
	AvgTimeToAuthSec    float64                 `json:"avg_time_to_auth_sec"`
	FaceAuthCount       int                     `json:"face_auth_count"`
	BarcodeAuthCount    int                     `json:"barcode_auth_count"`
	FromScreensaver     int                     `json:"from_screensaver_count"`
	ScreensaverModes    map[string]int          `json:"screensaver_modes"`
	TotalGestureEvents  int                     `json:"total_gesture_events"`
	VariantA            VariantStats            `json:"variant_a"`
	VariantB            VariantStats            `json:"variant_b"`
	AdoptionRateLiftPct float64                 `json:"adoption_rate_lift_pct"`
	ZScore              float64                 `json:"z_score"`
	PValue              float64                 `json:"p_value"`
	IsSignificant       bool                    `json:"is_significant"`
	NoveltyPhase1Lift   float64                 `json:"novelty_phase1_lift"`
	NoveltyPhase2Lift   float64                 `json:"novelty_phase2_lift"`
	HourlyDistribution  [24]int                 `json:"hourly_distribution"`
	RecentSessions      []SessionAnalyticsEvent `json:"recent_sessions"`
}

func clampF(v, lo, hi float64) float64 {
	if math.IsNaN(v) || v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func clampI(v, hi int) int {
	if v < 0 {
		return 0
	}
	if v > hi {
		return hi
	}
	return v
}

func oneOf(v string, allowed ...string) string {
	v = strings.ToLower(strings.TrimSpace(v))
	for _, a := range allowed {
		if v == a {
			return v
		}
	}
	return allowed[0]
}

// POST /api/analytics/events (mirror)
func recordAnalyticsEvent(c echo.Context) error {
	var ev SessionAnalyticsEvent
	if err := c.Bind(&ev); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	if ev.SessionID == "" || len(ev.SessionID) > 64 {
		ev.SessionID = "sess-" + time.Now().Format("20060102150405.000000")
	}
	ev.Variant = strings.ToUpper(strings.TrimSpace(ev.Variant))
	if ev.Variant != "B" {
		ev.Variant = "A"
	}
	ev.SessionType = oneOf(ev.SessionType, "guest", "user", "passerby")
	ev.AuthMethod = oneOf(ev.AuthMethod, "presence", "face", "barcode")
	ev.ScreensaverMode = oneOf(ev.ScreensaverMode, "", "demo", "slideshow", "logo")

	// Only link the session to a real account.
	var userID interface{}
	if ev.UserID != "" && userExists(ev.UserID) {
		userID = ev.UserID
	}

	const day = 86400.0
	_, err := db.Exec(`INSERT OR IGNORE INTO sessions(
		id, user_id, mirror_id, mirror_version, variant, session_type, auth_method, screensaver_mode,
		duration_sec, time_to_auth_sec, has_gesture, time_to_first_gesture, hand_seen,
		scroll_count, tap_count, timetable_toggles, dwell_completed, dwell_abandoned,
		article_opens, notice_opens, modal_read_sec, kings_expands, tutorial_shown, tutorial_dismissed,
		practice_shown, practice_completed, practice_skipped, practice_steps, practice_sec, after_teaser,
		from_screensaver, client_started_at, created_at)
		VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
		ev.SessionID, userID, truncate(ev.MirrorID, 64), truncate(ev.MirrorVersion, 32), ev.Variant, ev.SessionType,
		ev.AuthMethod, ev.ScreensaverMode,
		clampF(ev.DurationSec, 0, day), clampF(ev.TimeToAuthSec, 0, day), boolInt(ev.HasGesture),
		clampF(ev.TimeToFirstGesture, 0, day), boolInt(ev.HandSeen || ev.HasGesture),
		clampI(ev.GestureScrollCount, 10000), clampI(ev.GestureTapCount, 10000),
		clampI(ev.TimetableToggleCount, 10000), clampI(ev.DwellCompletedCount, 10000),
		clampI(ev.DwellAbandonedCount, 10000), clampI(ev.ArticleModalOpens, 10000),
		clampI(ev.NoticeOpens, 10000), clampF(ev.ModalReadTimeSec, 0, day), clampI(ev.KingsExpands, 10000),
		clampI(ev.TutorialShown, 1000), clampI(ev.TutorialDismissed, 1000),
		clampI(ev.PracticeShown, 1), clampI(ev.PracticeCompleted, 1), clampI(ev.PracticeSkipped, 1),
		clampI(ev.PracticeSteps, 10), clampF(ev.PracticeSec, 0, 3600), boolInt(ev.AfterTeaser),
		boolInt(ev.FromScreensaver),
		ev.ClientTimestamp, time.Now().Unix())
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not record session"})
	}
	return c.JSON(http.StatusOK, map[string]interface{}{"status": "recorded", "session_id": ev.SessionID})
}

func truncate(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

const sessionColumns = `id, COALESCE(user_id, ''), mirror_id, mirror_version, variant, session_type, auth_method,
	screensaver_mode, duration_sec, time_to_auth_sec, has_gesture, time_to_first_gesture, hand_seen,
	scroll_count, tap_count, timetable_toggles, dwell_completed, dwell_abandoned, article_opens,
	notice_opens, modal_read_sec, kings_expands, tutorial_shown, tutorial_dismissed, practice_shown,
	practice_completed, practice_skipped, practice_steps, practice_sec, after_teaser, from_screensaver,
	client_started_at, created_at`

func scanSession(rows *sql.Rows) (SessionAnalyticsEvent, error) {
	var ev SessionAnalyticsEvent
	var hasGesture, handSeen, fromSS, afterTeaser int
	var created int64
	err := rows.Scan(&ev.SessionID, &ev.UserID, &ev.MirrorID, &ev.MirrorVersion, &ev.Variant, &ev.SessionType,
		&ev.AuthMethod, &ev.ScreensaverMode, &ev.DurationSec, &ev.TimeToAuthSec, &hasGesture,
		&ev.TimeToFirstGesture, &handSeen, &ev.GestureScrollCount, &ev.GestureTapCount,
		&ev.TimetableToggleCount, &ev.DwellCompletedCount, &ev.DwellAbandonedCount, &ev.ArticleModalOpens,
		&ev.NoticeOpens, &ev.ModalReadTimeSec, &ev.KingsExpands, &ev.TutorialShown, &ev.TutorialDismissed,
		&ev.PracticeShown, &ev.PracticeCompleted, &ev.PracticeSkipped, &ev.PracticeSteps, &ev.PracticeSec,
		&afterTeaser, &fromSS, &ev.ClientTimestamp, &created)
	ev.HasGesture, ev.HandSeen, ev.FromScreensaver = hasGesture == 1, handSeen == 1, fromSS == 1
	ev.AfterTeaser = afterTeaser == 1
	ev.CreatedAt = time.Unix(created, 0).UTC().Format(time.RFC3339)
	return ev, err
}

func round1(v float64) float64 { return math.Round(v*10) / 10 }

func pct(n, d int) float64 {
	if d == 0 {
		return 0
	}
	return round1(100 * float64(n) / float64(d))
}

type variantAcc struct {
	VariantStats
	durationSum, firstGestSum, modalSum, practiceSum float64
	firstGestN, handSeen, userN, practiceN           int
}

// addPasserby counts someone who got the brief-encounter hint and walked on.
// They are not a visit, so nothing else about the variant includes them.
func (a *variantAcc) addPasserby() { a.Passersby++ }

func (a *variantAcc) add(ev SessionAnalyticsEvent) {
	a.TotalSessions++
	a.durationSum += ev.DurationSec
	a.TotalScrollCount += ev.GestureScrollCount
	a.TotalTapCount += ev.GestureTapCount
	a.DwellCompletedCount += ev.DwellCompletedCount
	a.DwellAbandonedCount += ev.DwellAbandonedCount
	a.TimetableToggles += ev.TimetableToggleCount
	a.ArticleModalOpens += ev.ArticleModalOpens
	a.NoticeOpens += ev.NoticeOpens
	a.KingsExpands += ev.KingsExpands
	a.TutorialShown += ev.TutorialShown
	a.TutorialDismissed += ev.TutorialDismissed
	a.PracticeShown += ev.PracticeShown
	a.PracticeCompleted += ev.PracticeCompleted
	a.PracticeSkipped += ev.PracticeSkipped
	if ev.PracticeShown > 0 && ev.PracticeSec > 0 {
		a.practiceSum += ev.PracticeSec
		a.practiceN++
	}
	if ev.AfterTeaser {
		a.TeaserVisits++
	}
	a.modalSum += ev.ModalReadTimeSec
	if ev.SessionType == "user" {
		a.userN++
	}
	if ev.HandSeen {
		a.handSeen++
	}
	if ev.HasGesture {
		a.SessionsWithGesture++
		if ev.TimeToFirstGesture > 0 {
			a.firstGestSum += ev.TimeToFirstGesture
			a.firstGestN++
		}
	}
}

func (a *variantAcc) finish() VariantStats {
	s := a.VariantStats
	if s.TotalSessions > 0 {
		s.GestureAdoptionRate = pct(s.SessionsWithGesture, s.TotalSessions)
		s.ZeroInteractionRate = pct(s.TotalSessions-s.SessionsWithGesture, s.TotalSessions)
		s.HandSeenRate = pct(a.handSeen, s.TotalSessions)
		s.AvgDurationSec = round1(a.durationSum / float64(s.TotalSessions))
	}
	s.TimetableToggleRate = pct(s.TimetableToggles, a.userN)
	if a.firstGestN > 0 {
		s.AvgTimeToFirstGest = round1(a.firstGestSum / float64(a.firstGestN))
	}
	s.DwellSuccessRate = pct(s.DwellCompletedCount, s.DwellCompletedCount+s.DwellAbandonedCount)
	if opens := s.ArticleModalOpens + s.NoticeOpens; opens > 0 {
		s.AvgModalReadSec = round1(a.modalSum / float64(opens))
	}
	s.TutorialDismissRate = pct(s.TutorialDismissed, s.TutorialShown)
	s.PracticeCompletionRate = pct(s.PracticeCompleted, s.PracticeShown)
	if a.practiceN > 0 {
		s.AvgPracticeSec = round1(a.practiceSum / float64(a.practiceN))
	}
	s.TeaserConversionRate = pct(s.TeaserVisits, s.TeaserVisits+s.Passersby)
	return s
}

// GET /api/admin/analytics (admin)
func getAdminAnalytics(c echo.Context) error {
	rows, err := db.Query(`SELECT ` + sessionColumns + ` FROM sessions ORDER BY created_at`)
	if err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not read analytics"})
	}
	var all []SessionAnalyticsEvent
	var accA, accB variantAcc
	for rows.Next() {
		ev, err := scanSession(rows)
		if err != nil {
			continue
		}
		if ev.SessionType == "passerby" {
			if ev.Variant == "B" {
				accB.addPasserby()
			} else {
				accA.addPasserby()
			}
			continue
		}
		all = append(all, ev)
	}
	rows.Close()

	resp := AnalyticsSummaryResponse{RecentSessions: []SessionAnalyticsEvent{}, ScreensaverModes: map[string]int{}}
	var phase [2][2][2]int // [phase][variant A/B][total, with gesture]
	var userDur, guestDur, authSum float64
	var authN int
	nz := nzLocation()

	for i, ev := range all {
		resp.TotalSessions++
		resp.TotalGestureEvents += ev.GestureScrollCount + ev.GestureTapCount + ev.DwellCompletedCount
		if t, err := time.Parse(time.RFC3339, ev.CreatedAt); err == nil {
			resp.HourlyDistribution[t.In(nz).Hour()]++
		}
		if ev.SessionType == "user" {
			resp.UserSessions++
			userDur += ev.DurationSec
			switch ev.AuthMethod {
			case "face":
				resp.FaceAuthCount++
			case "barcode":
				resp.BarcodeAuthCount++
			}
			if ev.TimeToAuthSec > 0 {
				authSum += ev.TimeToAuthSec
				authN++
			}
		} else {
			resp.GuestSessions++
			guestDur += ev.DurationSec
		}
		if ev.FromScreensaver {
			resp.FromScreensaver++
		}
		if ev.ScreensaverMode != "" {
			resp.ScreensaverModes[ev.ScreensaverMode]++
		}
		v := 0
		acc := &accA
		if ev.Variant == "B" {
			v, acc = 1, &accB
		}
		acc.add(ev)
		p := 0
		if i >= len(all)/2 {
			p = 1
		}
		phase[p][v][0]++
		if ev.HasGesture {
			phase[p][v][1]++
		}
	}

	if resp.UserSessions > 0 {
		resp.AvgUserDurationSec = round1(userDur / float64(resp.UserSessions))
	}
	if resp.GuestSessions > 0 {
		resp.AvgGuestDurationSec = round1(guestDur / float64(resp.GuestSessions))
	}
	if authN > 0 {
		resp.AvgTimeToAuthSec = round1(authSum / float64(authN))
	}
	resp.VariantA, resp.VariantB = accA.finish(), accB.finish()

	if resp.VariantA.GestureAdoptionRate > 0 {
		resp.AdoptionRateLiftPct = round1((resp.VariantB.GestureAdoptionRate - resp.VariantA.GestureAdoptionRate) /
			resp.VariantA.GestureAdoptionRate * 100)
	}

	// Two-proportion z-test on gesture adoption.
	nA, nB := float64(resp.VariantA.TotalSessions), float64(resp.VariantB.TotalSessions)
	xA, xB := float64(resp.VariantA.SessionsWithGesture), float64(resp.VariantB.SessionsWithGesture)
	if nA > 0 && nB > 0 && nA+nB >= 10 {
		pooled := (xA + xB) / (nA + nB)
		if se := math.Sqrt(pooled * (1 - pooled) * (1/nA + 1/nB)); se > 0 {
			z := (xB/nB - xA/nA) / se
			resp.ZScore = math.Round(z*100) / 100
			p := math.Max(1-math.Erf(math.Abs(z)/math.Sqrt2), 0.0001)
			resp.PValue = math.Round(p*10000) / 10000
			resp.IsSignificant = resp.PValue < 0.05
		}
	}

	lift := func(ph int) float64 {
		a, b := phase[ph][0], phase[ph][1]
		if a[0] == 0 || b[0] == 0 || a[1] == 0 {
			return 0
		}
		rA, rB := float64(a[1])/float64(a[0]), float64(b[1])/float64(b[0])
		return round1((rB - rA) / rA * 100)
	}
	resp.NoveltyPhase1Lift, resp.NoveltyPhase2Lift = lift(0), lift(1)

	for i := len(all) - 1; i >= 0 && len(resp.RecentSessions) < 50; i-- {
		resp.RecentSessions = append(resp.RecentSessions, all[i])
	}
	return c.JSON(http.StatusOK, resp)
}

// ── A/B experiment configuration ────────────────────────────────────────────

type ABExperimentConfig struct {
	Mode          string `json:"mode"` // auto | force_a | force_b | hourly | daily
	ActiveVariant string `json:"active_variant"`
	UpdatedAt     int64  `json:"updated_at"`
	UpdatedBy     string `json:"updated_by,omitempty"`
}

func loadABConfig() ABExperimentConfig {
	cfg := ABExperimentConfig{Mode: "auto"}
	getSetting("ab_config", &cfg)
	return cfg
}

func computeActiveVariant(cfg ABExperimentConfig) string {
	switch cfg.Mode {
	case "force_a":
		return "A"
	case "force_b":
		return "B"
	case "hourly":
		if (time.Now().Unix()/3600)%2 == 0 {
			return "A"
		}
		return "B"
	case "daily":
		if (time.Now().In(nzLocation()).YearDay())%2 == 0 {
			return "A"
		}
		return "B"
	default: // auto: alternate by visit count
		var n int
		db.QueryRow(`SELECT COUNT(*) FROM sessions WHERE session_type != 'passerby'`).Scan(&n)
		if n%2 == 0 {
			return "A"
		}
		return "B"
	}
}

// GET /api/analytics/config (mirror + admin)
func getAnalyticsConfig(c echo.Context) error {
	cfg := loadABConfig()
	cfg.ActiveVariant = computeActiveVariant(cfg)
	return c.JSON(http.StatusOK, map[string]interface{}{
		"mode":            cfg.Mode,
		"active_variant":  cfg.ActiveVariant,
		"current_variant": cfg.ActiveVariant,
		"updated_at":      cfg.UpdatedAt,
		"updated_by":      cfg.UpdatedBy,
	})
}

// POST /api/analytics/config (admin)
func updateAnalyticsConfig(c echo.Context) error {
	var req struct {
		Mode string `json:"mode"`
	}
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
	}
	cfg := loadABConfig()
	cfg.Mode = oneOf(req.Mode, "auto", "force_a", "force_b", "hourly", "daily")
	cfg.UpdatedAt = time.Now().Unix()
	cfg.UpdatedBy = adminEmailOf(c)
	if err := setSetting("ab_config", cfg); err != nil {
		return c.JSON(http.StatusInternalServerError, map[string]string{"error": "Could not save"})
	}
	auditAdmin(c, "ab_mode", "", cfg.Mode)
	return getAnalyticsConfig(c)
}
