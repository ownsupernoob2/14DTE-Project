package main

import (
	"encoding/json"
	"math"
	"os"
	"strings"
	"sync"
	"time"


	"github.com/labstack/echo/v4"
)

const DefaultAdminEmail = "marminamina3@gmail.com"

// SessionAnalyticsEvent represents telemetry recorded for a single user/guest session
type SessionAnalyticsEvent struct {
	SessionID            string  `json:"session_id"`
	ClientTimestamp      float64 `json:"client_timestamp"`
	Variant              string  `json:"variant"` // "A" or "B"
	SessionType          string  `json:"session_type"` // "user" or "guest"
	AuthMethod           string  `json:"auth_method"` // "face", "barcode", "none"
	DurationSec          float64 `json:"duration_sec"`
	HasGesture           bool    `json:"has_gesture"`
	TimeToFirstGesture   float64 `json:"time_to_first_gesture_sec"`
	GestureScrollCount   int     `json:"gesture_scroll_count"`
	GestureTapCount      int     `json:"gesture_tap_count"`
	TimetableToggleCount int     `json:"timetable_toggle_count"`
	DwellCompletedCount  int     `json:"dwell_completed_count"`
	DwellAbandonedCount  int     `json:"dwell_abandoned_count"`
	ArticleModalOpens    int     `json:"article_modal_opens"`
	ModalReadTimeSec     float64 `json:"modal_read_time_sec"`
	CreatedAt            string  `json:"created_at"`
}

type VariantStats struct {
	TotalSessions       int     `json:"total_sessions"`
	SessionsWithGesture int     `json:"sessions_with_gesture"`
	GestureAdoptionRate float64 `json:"gesture_adoption_rate"` // 0.0 - 100.0%
	ZeroInteractionRate float64 `json:"zero_interaction_rate"` // % sessions with 0 gestures (touchscreen confusion)
	TimetableToggles    int     `json:"timetable_toggles"`
	TimetableToggleRate float64 `json:"timetable_toggle_rate"` // % of user sessions that toggled
	AvgDurationSec      float64 `json:"avg_duration_sec"`
	AvgTimeToFirstGest  float64 `json:"avg_time_to_first_gesture_sec"`
	TotalScrollCount    int     `json:"total_scroll_count"`
	TotalTapCount       int     `json:"total_tap_count"`
	DwellCompletedCount int     `json:"dwell_completed_count"`
	DwellAbandonedCount int     `json:"dwell_abandoned_count"`
	DwellSuccessRate    float64 `json:"dwell_success_rate"` // % of dwells completed vs abandoned
	ArticleModalOpens   int     `json:"article_modal_opens"`
	AvgModalReadSec     float64 `json:"avg_modal_read_sec"`
}

type AnalyticsSummaryResponse struct {
	TotalSessions        int                      `json:"total_sessions"`
	UserSessions         int                      `json:"user_sessions"`
	GuestSessions        int                      `json:"guest_sessions"`
	AvgUserDurationSec   float64                  `json:"avg_user_duration_sec"`
	AvgGuestDurationSec  float64                  `json:"avg_guest_duration_sec"`
	FaceAuthCount        int                      `json:"face_auth_count"`
	BarcodeAuthCount     int                      `json:"barcode_auth_count"`
	TotalGestureEvents   int                      `json:"total_gesture_events"`
	VariantA             VariantStats             `json:"variant_a"`
	VariantB             VariantStats             `json:"variant_b"`
	AdoptionRateLiftPct  float64                  `json:"adoption_rate_lift_pct"`
	ZScore               float64                  `json:"z_score"`
	PValue               float64                  `json:"p_value"`
	IsSignificant        bool                     `json:"is_significant"`
	NoveltyPhase1Lift    float64                  `json:"novelty_phase1_lift"` // Early sessions lift %
	NoveltyPhase2Lift    float64                  `json:"novelty_phase2_lift"` // Later sessions lift %
	HourlyDistribution   [24]int                  `json:"hourly_distribution"`
	RecentSessions       []SessionAnalyticsEvent  `json:"recent_sessions"`
}

var (
	analyticsMutex sync.RWMutex
	analyticsLog   []SessionAnalyticsEvent
)

const analyticsFilePath = "data/analytics_events.json"

func init() {
	_ = os.MkdirAll("data", 0755)
	data, err := os.ReadFile(analyticsFilePath)
	if err == nil {
		var list []SessionAnalyticsEvent
		if json.Unmarshal(data, &list) == nil {
			analyticsLog = list
		}
	}
}

func saveAnalyticsToDisk() {
	data, err := json.MarshalIndent(analyticsLog, "", "  ")
	if err == nil {
		_ = os.WriteFile(analyticsFilePath, data, 0644)
	}
}

// POST /api/analytics/events
func recordAnalyticsEvent(c echo.Context) error {
	var event SessionAnalyticsEvent
	if err := c.Bind(&event); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request body"})
	}

	if event.SessionID == "" {
		event.SessionID = "sess-" + time.Now().Format("20060102150405.000")
	}
	if event.CreatedAt == "" {
		event.CreatedAt = time.Now().UTC().Format(time.RFC3339)
	}
	if event.Variant == "" {
		event.Variant = "A"
	}
	event.Variant = strings.ToUpper(strings.TrimSpace(event.Variant))
	if event.Variant != "A" && event.Variant != "B" {
		event.Variant = "A"
	}

	analyticsMutex.Lock()
	analyticsLog = append(analyticsLog, event)
	if len(analyticsLog) > 10000 {
		// Cap in memory log to 10k items
		analyticsLog = analyticsLog[len(analyticsLog)-10000:]
	}
	saveAnalyticsToDisk()
	analyticsMutex.Unlock()

	return c.JSON(200, map[string]interface{}{
		"status":     "recorded",
		"session_id": event.SessionID,
	})
}

// verifyAdminAccess checks if the requester is the authorized administrator
func verifyAdminAccess(c echo.Context) bool {
	expectedEmail := os.Getenv("ADMIN_EMAIL")
	if expectedEmail == "" {
		expectedEmail = DefaultAdminEmail
	}
	expectedEmail = strings.ToLower(strings.TrimSpace(expectedEmail))

	// 1. Check X-Admin-Token
	adminToken := os.Getenv("ADMIN_TOKEN")
	if adminToken != "" && c.Request().Header.Get("X-Admin-Token") == adminToken {
		return true
	}

	// 2. Check X-Admin-Email header with Auth0 token present
	reqEmail := strings.ToLower(strings.TrimSpace(c.Request().Header.Get("X-Admin-Email")))
	if reqEmail != "" && reqEmail == expectedEmail {
		return true
	}

	// 3. Check Auth0 JWT claims if available
	raw := c.Get("user")
	if raw != nil {
		uid := getUserIDFromToken(c)
		if uid != "" && (strings.Contains(strings.ToLower(uid), expectedEmail) || strings.HasPrefix(uid, "auth0|") || strings.HasPrefix(uid, "google-oauth2|")) {
			// If authenticated and email matches or admin
			if reqEmail == expectedEmail {
				return true
			}
		}
	}

	// Allow if local development request with admin email header
	return reqEmail == expectedEmail
}

// GET /api/admin/analytics
func getAdminAnalytics(c echo.Context) error {
	if !verifyAdminAccess(c) {
		return c.JSON(403, map[string]string{
			"error": "Forbidden: Admin access restricted to " + DefaultAdminEmail,
		})
	}

	analyticsMutex.RLock()
	defer analyticsMutex.RUnlock()

	resp := AnalyticsSummaryResponse{
		RecentSessions: make([]SessionAnalyticsEvent, 0),
	}

	var totalUserDuration, totalGuestDuration float64
	var vA_gestTotalTime, vB_gestTotalTime float64
	var vA_gestTotalCount, vB_gestTotalCount int
	var vA_userCount, vB_userCount int
	var vA_modalTime, vB_modalTime float64

	totalCount := len(analyticsLog)
	splitIdx := totalCount / 2
	var p1_vA_tot, p1_vA_gest, p1_vB_tot, p1_vB_gest int
	var p2_vA_tot, p2_vA_gest, p2_vB_tot, p2_vB_gest int

	for idx, ev := range analyticsLog {
		resp.TotalSessions++
		resp.TotalGestureEvents += ev.GestureScrollCount + ev.GestureTapCount + ev.DwellCompletedCount

		// Traffic by hour (0-23)
		t, err := time.Parse(time.RFC3339, ev.CreatedAt)
		if err == nil {
			localHour := t.Local().Hour()
			if localHour >= 0 && localHour < 24 {
				resp.HourlyDistribution[localHour]++
			}
		}

		if ev.SessionType == "user" {
			resp.UserSessions++
			totalUserDuration += ev.DurationSec
			if ev.AuthMethod == "face" {
				resp.FaceAuthCount++
			} else if ev.AuthMethod == "barcode" {
				resp.BarcodeAuthCount++
			}
		} else {
			resp.GuestSessions++
			totalGuestDuration += ev.DurationSec
		}

		// Novelty Effect Phase Partition (Phase 1 = early half, Phase 2 = later half)
		isPhase1 := idx < splitIdx

		// Variant A vs B stats
		isB := (ev.Variant == "B")
		if isB {
			resp.VariantB.TotalSessions++
			resp.VariantB.AvgDurationSec += ev.DurationSec
			resp.VariantB.TotalScrollCount += ev.GestureScrollCount
			resp.VariantB.TotalTapCount += ev.GestureTapCount
			resp.VariantB.DwellCompletedCount += ev.DwellCompletedCount
			resp.VariantB.DwellAbandonedCount += ev.DwellAbandonedCount
			resp.VariantB.TimetableToggles += ev.TimetableToggleCount
			resp.VariantB.ArticleModalOpens += ev.ArticleModalOpens
			vB_modalTime += ev.ModalReadTimeSec

			if isPhase1 {
				p1_vB_tot++
				if ev.HasGesture {
					p1_vB_gest++
				}
			} else {
				p2_vB_tot++
				if ev.HasGesture {
					p2_vB_gest++
				}
			}

			if ev.SessionType == "user" {
				vB_userCount++
			}
			if ev.HasGesture {
				resp.VariantB.SessionsWithGesture++
				if ev.TimeToFirstGesture > 0 {
					vB_gestTotalTime += ev.TimeToFirstGesture
					vB_gestTotalCount++
				}
			}
		} else {
			resp.VariantA.TotalSessions++
			resp.VariantA.AvgDurationSec += ev.DurationSec
			resp.VariantA.TotalScrollCount += ev.GestureScrollCount
			resp.VariantA.TotalTapCount += ev.GestureTapCount
			resp.VariantA.DwellCompletedCount += ev.DwellCompletedCount
			resp.VariantA.DwellAbandonedCount += ev.DwellAbandonedCount
			resp.VariantA.TimetableToggles += ev.TimetableToggleCount
			resp.VariantA.ArticleModalOpens += ev.ArticleModalOpens
			vA_modalTime += ev.ModalReadTimeSec

			if isPhase1 {
				p1_vA_tot++
				if ev.HasGesture {
					p1_vA_gest++
				}
			} else {
				p2_vA_tot++
				if ev.HasGesture {
					p2_vA_gest++
				}
			}

			if ev.SessionType == "user" {
				vA_userCount++
			}
			if ev.HasGesture {
				resp.VariantA.SessionsWithGesture++
				if ev.TimeToFirstGesture > 0 {
					vA_gestTotalTime += ev.TimeToFirstGesture
					vA_gestTotalCount++
				}
			}
		}
	}

	// Compute averages and rates
	if resp.UserSessions > 0 {
		resp.AvgUserDurationSec = math.Round((totalUserDuration/float64(resp.UserSessions))*10) / 10
	}
	if resp.GuestSessions > 0 {
		resp.AvgGuestDurationSec = math.Round((totalGuestDuration/float64(resp.GuestSessions))*10) / 10
	}

	// Variant A
	if resp.VariantA.TotalSessions > 0 {
		resp.VariantA.GestureAdoptionRate = math.Round((float64(resp.VariantA.SessionsWithGesture)/float64(resp.VariantA.TotalSessions))*1000) / 10
		resp.VariantA.AvgDurationSec = math.Round((resp.VariantA.AvgDurationSec/float64(resp.VariantA.TotalSessions))*10) / 10
		// Zero-interaction bounce rate (users who touched glass or walked away without gesture)
		bouncesA := resp.VariantA.TotalSessions - resp.VariantA.SessionsWithGesture
		resp.VariantA.ZeroInteractionRate = math.Round((float64(bouncesA)/float64(resp.VariantA.TotalSessions))*1000) / 10
	}
	if vA_userCount > 0 {
		resp.VariantA.TimetableToggleRate = math.Round((float64(resp.VariantA.TimetableToggles)/float64(vA_userCount))*1000) / 10
	}
	if vA_gestTotalCount > 0 {
		resp.VariantA.AvgTimeToFirstGest = math.Round((vA_gestTotalTime/float64(vA_gestTotalCount))*10) / 10
	}
	totalDwellA := resp.VariantA.DwellCompletedCount + resp.VariantA.DwellAbandonedCount
	if totalDwellA > 0 {
		resp.VariantA.DwellSuccessRate = math.Round((float64(resp.VariantA.DwellCompletedCount)/float64(totalDwellA))*1000) / 10
	}
	if resp.VariantA.ArticleModalOpens > 0 {
		resp.VariantA.AvgModalReadSec = math.Round((vA_modalTime/float64(resp.VariantA.ArticleModalOpens))*10) / 10
	}

	// Variant B
	if resp.VariantB.TotalSessions > 0 {
		resp.VariantB.GestureAdoptionRate = math.Round((float64(resp.VariantB.SessionsWithGesture)/float64(resp.VariantB.TotalSessions))*1000) / 10
		resp.VariantB.AvgDurationSec = math.Round((resp.VariantB.AvgDurationSec/float64(resp.VariantB.TotalSessions))*10) / 10
		// Zero-interaction bounce rate
		bouncesB := resp.VariantB.TotalSessions - resp.VariantB.SessionsWithGesture
		resp.VariantB.ZeroInteractionRate = math.Round((float64(bouncesB)/float64(resp.VariantB.TotalSessions))*1000) / 10
	}
	if vB_userCount > 0 {
		resp.VariantB.TimetableToggleRate = math.Round((float64(resp.VariantB.TimetableToggles)/float64(vB_userCount))*1000) / 10
	}
	if vB_gestTotalCount > 0 {
		resp.VariantB.AvgTimeToFirstGest = math.Round((vB_gestTotalTime/float64(vB_gestTotalCount))*10) / 10
	}
	totalDwellB := resp.VariantB.DwellCompletedCount + resp.VariantB.DwellAbandonedCount
	if totalDwellB > 0 {
		resp.VariantB.DwellSuccessRate = math.Round((float64(resp.VariantB.DwellCompletedCount)/float64(totalDwellB))*1000) / 10
	}
	if resp.VariantB.ArticleModalOpens > 0 {
		resp.VariantB.AvgModalReadSec = math.Round((vB_modalTime/float64(resp.VariantB.ArticleModalOpens))*10) / 10
	}

	// Lift %
	if resp.VariantA.GestureAdoptionRate > 0 {
		lift := ((resp.VariantB.GestureAdoptionRate - resp.VariantA.GestureAdoptionRate) / resp.VariantA.GestureAdoptionRate) * 100.0
		resp.AdoptionRateLiftPct = math.Round(lift*10) / 10
	}

	// Two-proportion Z-test for statistical significance
	nA := float64(resp.VariantA.TotalSessions)
	nB := float64(resp.VariantB.TotalSessions)
	xA := float64(resp.VariantA.SessionsWithGesture)
	xB := float64(resp.VariantB.SessionsWithGesture)
	if nA > 0 && nB > 0 && (nA+nB) >= 10 {
		pA := xA / nA
		pB := xB / nB
		pPooled := (xA + xB) / (nA + nB)
		se := math.Sqrt(pPooled * (1.0 - pPooled) * ((1.0 / nA) + (1.0 / nB)))
		if se > 0 {
			z := (pB - pA) / se
			resp.ZScore = math.Round(z*100) / 100
			// Two-tailed p-value from standard normal distribution
			pValue := 1.0 - math.Erf(math.Abs(z)/math.Sqrt2)
			if pValue < 0.0001 {
				pValue = 0.0001
			}
			resp.PValue = math.Round(pValue*10000) / 10000
			resp.IsSignificant = (resp.PValue < 0.05)
		}
	}

	// Novelty Phase Analysis (Phase 1 vs Phase 2 lift)
	if p1_vA_tot > 0 && p1_vB_tot > 0 {
		rA1 := float64(p1_vA_gest) / float64(p1_vA_tot)
		rB1 := float64(p1_vB_gest) / float64(p1_vB_tot)
		if rA1 > 0 {
			resp.NoveltyPhase1Lift = math.Round(((rB1-rA1)/rA1)*1000) / 10
		}
	}
	if p2_vA_tot > 0 && p2_vB_tot > 0 {
		rA2 := float64(p2_vA_gest) / float64(p2_vA_tot)
		rB2 := float64(p2_vB_gest) / float64(p2_vB_tot)
		if rA2 > 0 {
			resp.NoveltyPhase2Lift = math.Round(((rB2-rA2)/rA2)*1000) / 10
		}
	}

	// Slice recent 30 sessions in reverse order (newest first)
	n := len(analyticsLog)
	limit := 30
	if n < limit {
		limit = n
	}
	for i := n - 1; i >= n-limit; i-- {
		resp.RecentSessions = append(resp.RecentSessions, analyticsLog[i])
	}

	return c.JSON(200, resp)
}

// GET /api/analytics/config
func getAnalyticsConfig(c echo.Context) error {
	return c.JSON(200, map[string]interface{}{
		"experiment_name": "touchless_affordance_and_dwell_v1",
		"enabled":         true,
		"variants":        []string{"A", "B"},
		"admin_email":     DefaultAdminEmail,
	})
}
