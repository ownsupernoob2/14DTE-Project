package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/labstack/echo/v4"
)

func TestAnalyticsEndpoints(t *testing.T) {
	e := echo.New()

	// 1. Test POST /api/analytics/events
	eventPayload := SessionAnalyticsEvent{
		SessionID:          "test-sess-001",
		Variant:            "B",
		SessionType:        "user",
		AuthMethod:         "face",
		DurationSec:        45.2,
		HasGesture:         true,
		TimeToFirstGesture: 2.8,
		GestureScrollCount: 4,
		GestureTapCount:    2,
	}
	body, _ := json.Marshal(eventPayload)
	req := httptest.NewRequest(http.MethodPost, "/api/analytics/events", bytes.NewReader(body))
	req.Header.Set(echo.HeaderContentType, echo.MIMEApplicationJSON)
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)

	if err := recordAnalyticsEvent(c); err != nil {
		t.Fatalf("recordAnalyticsEvent returned error: %v", err)
	}
	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	// 2. Test GET /api/admin/analytics without admin header -> should return 403
	reqUnauth := httptest.NewRequest(http.MethodGet, "/api/admin/analytics", nil)
	recUnauth := httptest.NewRecorder()
	cUnauth := e.NewContext(reqUnauth, recUnauth)

	if err := getAdminAnalytics(cUnauth); err != nil {
		t.Fatalf("getAdminAnalytics returned unexpected error: %v", err)
	}
	if recUnauth.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 for unauthorized requester, got %d", recUnauth.Code)
	}

	// 3. Test GET /api/admin/analytics with X-Admin-Email header -> should return 200
	reqAuth := httptest.NewRequest(http.MethodGet, "/api/admin/analytics", nil)
	reqAuth.Header.Set("X-Admin-Email", "marminamina3@gmail.com")
	recAuth := httptest.NewRecorder()
	cAuth := e.NewContext(reqAuth, recAuth)

	if err := getAdminAnalytics(cAuth); err != nil {
		t.Fatalf("getAdminAnalytics returned unexpected error: %v", err)
	}
	if recAuth.Code != http.StatusOK {
		t.Fatalf("expected status 200 for admin requester, got %d", recAuth.Code)
	}

	var resp AnalyticsSummaryResponse
	if err := json.Unmarshal(recAuth.Body.Bytes(), &resp); err != nil {
		t.Fatalf("failed to parse AnalyticsSummaryResponse: %v", err)
	}
	if resp.TotalSessions == 0 {
		t.Errorf("expected total sessions > 0, got %d", resp.TotalSessions)
	}

	// 4. Test GET /api/analytics/config
	reqCfg := httptest.NewRequest(http.MethodGet, "/api/analytics/config", nil)
	recCfg := httptest.NewRecorder()
	cCfg := e.NewContext(reqCfg, recCfg)

	if err := getAnalyticsConfig(cCfg); err != nil {
		t.Fatalf("getAnalyticsConfig returned error: %v", err)
	}
	if recCfg.Code != http.StatusOK {
		t.Fatalf("expected status 200 for config, got %d", recCfg.Code)
	}
}
