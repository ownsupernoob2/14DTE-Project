package main

import (
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"github.com/labstack/echo/v4"
)

type Widget struct {
	ID   string      `json:"id"`
	Type string      `json:"type"`
	X    float64     `json:"x"`
	Y    float64     `json:"y"`
	W    float64     `json:"w,omitempty"`
	H    float64     `json:"h,omitempty"`
	Data interface{} `json:"data,omitempty"`
}

type ThemeColors struct {
	Primary    string `json:"primary"`
	Secondary  string `json:"secondary"`
	Background string `json:"background"`
}

type ThemeFonts struct {
	Family       string  `json:"family"`
	SizeModifier float64 `json:"size_modifier"`
}

type Theme struct {
	Colors ThemeColors `json:"colors"`
	Fonts  ThemeFonts  `json:"fonts"`
}

type Slot struct {
	SlotID      string `json:"slot_id"`
	Orientation string `json:"orientation"`
	Widget      Widget `json:"widget"`
}

type UserDashboardConfig struct {
	Theme Theme  `json:"theme"`
	Slots []Slot `json:"slots"`
}

type Dashboard struct {
	ID      string              `json:"id"`
	UserID  string              `json:"user_id"`
	Config  UserDashboardConfig `json:"config"`
	Widgets []Widget            `json:"widgets"` // kept for legacy compatibility
}
func getDashboard(c echo.Context) error {
	userID := getUserIDFromToken(c)
	config := getDashboardConfigForUser(userID)
	widgets := []Widget{}
	for _, slot := range config.Slots {
		widgets = append(widgets, slot.Widget)
	}
	return c.JSON(200, Dashboard{
		ID:      "dashboard-" + userID,
		UserID:  userID,
		Config:  config,
		Widgets: widgets,
	})
}
func getDashboardConfigForUser(userID string) UserDashboardConfig {
	var raw string
	if userID == "" || db.QueryRow(`SELECT dashboard FROM users WHERE id = ?`, userID).Scan(&raw) != nil || raw == "" {
		return defaultDashboardConfig()
	}
	var config UserDashboardConfig
	if err := json.Unmarshal([]byte(raw), &config); err != nil {
		return defaultDashboardConfig()
	}
	return config
}

func saveDashboardConfigForUser(userID string, config UserDashboardConfig) error {
	if userID == "" {
		return nil
	}
	data, err := json.Marshal(config)
	if err != nil {
		return err
	}
	_, err = db.Exec(`UPDATE users SET dashboard = ? WHERE id = ?`, string(data), userID)
	return err
}

func defaultTheme() Theme {
	return Theme{
		Colors: ThemeColors{
			Primary:    "#3b82f6",
			Secondary:  "#10b981",
			Background: "#0a0a0c",
		},
		Fonts: ThemeFonts{
			Family:       "Outfit",
			SizeModifier: 1.0,
		},
	}
}

func defaultDashboardConfig() UserDashboardConfig {
	return UserDashboardConfig{
		Theme: defaultTheme(),
		Slots: []Slot{},
	}
}

func getWidgetsForUser(userID string) []Widget {
	config := getDashboardConfigForUser(userID)
	widgets := []Widget{}
	for _, slot := range config.Slots {
		widgets = append(widgets, slot.Widget)
	}
	return widgets
}

func saveWidgetsForUser(userID string, widgets []Widget) {
	config := getDashboardConfigForUser(userID)
	slots := []Slot{}
	for i, w := range widgets {
		slots = append(slots, Slot{
			SlotID:      fmt.Sprintf("slot_%d", i),
			Orientation: "horizontal",
			Widget:      w,
		})
	}
	config.Slots = slots
	saveDashboardConfigForUser(userID, config)
}

func getWidgets(c echo.Context) error {
	userID := getUserIDFromToken(c)
	return c.JSON(200, getWidgetsForUser(userID))
}

func addWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	if widget.ID == "" {
		widget.ID = "widget-" + strconv.FormatInt(time.Now().UnixNano(), 10)
	}
	config := getDashboardConfigForUser(userID)
	config.Slots = append(config.Slots, Slot{
		SlotID:      "slot_" + widget.ID,
		Orientation: "horizontal",
		Widget:      widget,
	})
	saveDashboardConfigForUser(userID, config)

	return c.JSON(201, widget)
}

func updateWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	id := c.Param("id")
	var widget Widget
	if err := c.Bind(&widget); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}
	widget.ID = id

	config := getDashboardConfigForUser(userID)
	for i, slot := range config.Slots {
		if slot.Widget.ID == id {
			config.Slots[i].Widget = widget
			saveDashboardConfigForUser(userID, config)
			return c.JSON(200, widget)
		}
	}
	return c.JSON(404, map[string]string{"error": "Widget not found"})
}

func updateWidgetsBulk(c echo.Context) error {
	userID := getUserIDFromToken(c)
	
	// Try parsing direct UserDashboardConfig first
	var config UserDashboardConfig
	if err := c.Bind(&config); err != nil || len(config.Slots) == 0 {
		// Fallback: try raw widgets array
		var widgets []Widget
		if err := c.Bind(&widgets); err == nil {
			saveWidgetsForUser(userID, widgets)
			return c.JSON(200, map[string]string{"message": "Widgets saved successfully"})
		}
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	saveDashboardConfigForUser(userID, config)
	return c.JSON(200, map[string]string{"message": "Dashboard config saved successfully"})
}

func deleteWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	id := c.Param("id")

	config := getDashboardConfigForUser(userID)
	newSlots := []Slot{}
	for _, slot := range config.Slots {
		if slot.Widget.ID != id {
			newSlots = append(newSlots, slot)
		}
	}
	config.Slots = newSlots
	saveDashboardConfigForUser(userID, config)

	return c.JSON(200, map[string]string{"message": "Widget deleted", "id": id})
}
