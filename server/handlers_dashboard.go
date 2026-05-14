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
	Data interface{} `json:"data,omitempty"`
}

type Dashboard struct {
	ID      string   `json:"id"`
	UserID  string   `json:"user_id"`
	Widgets []Widget `json:"widgets"`
}

func getDashboard(c echo.Context) error {
	userID := getUserIDFromToken(c)
	if userID == "" {
		userID = c.QueryParam("user_id")
	}
	return c.JSON(200, Dashboard{
		ID:      "dashboard-" + userID,
		UserID:  userID,
		Widgets: getWidgetsForUser(userID),
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

func getWidgetsForUser(userID string) []Widget {
	if userID == "" {
		return []Widget{}
	}
	path := getUserWidgetsPath(userID)
	data, err := os.ReadFile(path)
	if err != nil {
		return []Widget{}
	}
	var widgets []Widget
	json.Unmarshal(data, &widgets)
	return widgets
}

func saveWidgetsForUser(userID string, widgets []Widget) {
	if userID == "" {
		return
	}
	path := getUserWidgetsPath(userID)
	data, err := json.MarshalIndent(widgets, "", "  ")
	if err == nil {
		os.WriteFile(path, data, 0644)
	}
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
	widgets := getWidgetsForUser(userID)
	widgets = append(widgets, widget)
	saveWidgetsForUser(userID, widgets)

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

	widgets := getWidgetsForUser(userID)
	for i, w := range widgets {
		if w.ID == id {
			widgets[i] = widget
			saveWidgetsForUser(userID, widgets)
			return c.JSON(200, widget)
		}
	}
	return c.JSON(404, map[string]string{"error": "Widget not found"})
}

func updateWidgetsBulk(c echo.Context) error {
	userID := getUserIDFromToken(c)
	var widgets []Widget
	if err := c.Bind(&widgets); err != nil {
		return c.JSON(400, map[string]string{"error": "Invalid request"})
	}

	saveWidgetsForUser(userID, widgets)
	return c.JSON(200, map[string]string{"message": "Widgets saved successfully"})
}

func deleteWidget(c echo.Context) error {
	userID := getUserIDFromToken(c)
	id := c.Param("id")

	widgets := getWidgetsForUser(userID)
	newWidgets := []Widget{}
	for _, w := range widgets {
		if w.ID != id {
			newWidgets = append(newWidgets, w)
		}
	}
	saveWidgetsForUser(userID, newWidgets)

	return c.JSON(200, map[string]string{"message": "Widget deleted", "id": id})
}
