package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
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

type UserLayoutConfig struct {
	Layout string `json:"layout"` // "focus" | "bulletin" | "compact"
}

func getPremadeWidgets(layoutName string) []Widget {
	switch layoutName {
	case "bulletin":
		return []Widget{
			{ID: "not-1", Type: "notices", X: 2, Y: 5, W: 58, H: 90},
			{ID: "clk-1", Type: "clock", X: 64, Y: 5, W: 34, H: 15},
			{ID: "tt-1", Type: "timetable", X: 64, Y: 23, W: 34, H: 72},
		}
	case "compact":
		return []Widget{
			{ID: "clk-1", Type: "clock", X: 35, Y: 15, W: 30, H: 15},
			{ID: "tt-1", Type: "timetable", X: 15, Y: 35, W: 70, H: 50, Data: map[string]interface{}{"viewMode": "next"}},
		}
	case "focus":
		fallthrough
	default:
		return []Widget{
			{ID: "clk-1", Type: "clock", X: 38, Y: 5, W: 24, H: 14},
			{ID: "tt-1", Type: "timetable", X: 2, Y: 22, W: 46, H: 72},
			{ID: "not-1", Type: "notices", X: 52, Y: 22, W: 46, H: 72},
		}
	}
}
func getDashboardConfigWithPremadeSlots(userID string, layoutName string) UserDashboardConfig {
	config := getDashboardConfigForUser(userID)
	premadeWidgets := getPremadeWidgets(layoutName)
	slots := []Slot{}
	for i, w := range premadeWidgets {
		orientation := "horizontal"
		if w.Type == "notices" {
			orientation = "vertical"
		}
		slots = append(slots, Slot{
			SlotID:      fmt.Sprintf("slot_%d", i),
			Orientation: orientation,
			Widget:      w,
		})
	}
	config.Slots = slots
	return config
}

func getDashboard(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = c.QueryParam("user_id")
	}

	layoutPath := getUserLayoutPath(userID)
	layoutName := "focus"
	if data, err := os.ReadFile(layoutPath); err == nil {
		var config UserLayoutConfig
		json.Unmarshal(data, &config)
		if config.Layout != "" {
			layoutName = config.Layout
		}
	}

	config := getDashboardConfigWithPremadeSlots(userID, layoutName)
	return c.JSON(200, Dashboard{
		ID:      "dashboard-" + userID,
		UserID:  userID,
		Config:  config,
		Widgets: getPremadeWidgets(layoutName),
	})
}
// In-memory cache + file sync per user
func getSafeUserID(userID string) string {
	safeUserID := strings.ReplaceAll(userID, "|", "_")
	safeUserID = strings.ReplaceAll(safeUserID, "/", "_")
	return safeUserID
}

func getUserWidgetsPath(userID string) string {
	return fmt.Sprintf("data/%s_widgets.json", getSafeUserID(userID))
}

func getDashboardConfigForUser(userID string) UserDashboardConfig {
	if userID == "" {
		return defaultDashboardConfig()
	}
	path := getUserWidgetsPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return defaultDashboardConfig()
	}
	var config UserDashboardConfig
	err = json.Unmarshal(data, &config)
	if err != nil {
		// Fallback to legacy structure
		var widgets []Widget
		if json.Unmarshal(data, &widgets) == nil {
			slots := []Slot{}
			for i, w := range widgets {
				slots = append(slots, Slot{
					SlotID:      fmt.Sprintf("slot_%d", i),
					Orientation: "horizontal",
					Widget:      w,
				})
			}
			return UserDashboardConfig{
				Theme: defaultTheme(),
				Slots: slots,
			}
		}
		return defaultDashboardConfig()
	}
	return config
}

func saveDashboardConfigForUser(userID string, config UserDashboardConfig) {
	if userID == "" {
		return
	}
	path := getUserWidgetsPath(userID)
	data, err := json.MarshalIndent(config, "", "  ")
	if err == nil {
		os.WriteFile(path, data, 0644)
	}
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

func getUserLayoutPath(userID string) string {
	return fmt.Sprintf("data/%s_layout.json", getSafeUserID(userID))
}

func getLayout(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = c.QueryParam("user_id")
	}
	if userID == "" {
		return c.JSON(200, UserLayoutConfig{Layout: "focus"})
	}

	path := getUserLayoutPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return c.JSON(200, UserLayoutConfig{Layout: "focus"}) // default
	}

	var config UserLayoutConfig
	json.Unmarshal(data, &config)
	if config.Layout == "" {
		config.Layout = "focus"
	}
	return c.JSON(200, config)
}

func saveLayout(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		return c.JSON(401, map[string]string{"error": "Unauthorized"})
	}

	var config UserLayoutConfig
	if err := c.Bind(&config); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	if config.Layout != "focus" && config.Layout != "bulletin" && config.Layout != "compact" {
		return c.JSON(400, map[string]string{"error": "Invalid layout selection"})
	}

	path := getUserLayoutPath(userID)
	data, err := json.MarshalIndent(config, "", "  ")
	if err == nil {
		os.WriteFile(path, data, 0644)
	}
	return c.JSON(200, map[string]string{"message": "Layout configuration saved successfully", "layout": config.Layout})
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
