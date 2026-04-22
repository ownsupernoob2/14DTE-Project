# Widgets Package

This package contains all the widget implementations for the Smart Mirror application. Each widget is in its own file for better organization and maintainability.

## Available Widgets

### Base Widget (`base_widget.py`)
- **Purpose**: Base class providing common functionality for all widgets
- **Features**:
  - Position and size management
  - Drag and drop functionality
  - Grid snapping
  - Fade-in animations
  - Rounded corner backgrounds
  - Title bars

### Clock Widget (`clock_widget.py`)
- **Purpose**: Displays current time and date
- **Features**:
  - Large, bold time display (12-hour format)
  - AM/PM indicator
  - Full date (Day, Month Date)
  - Automatic updates every minute
  - Clean, modern design

### Weather Widget (`weather_widget.py`)
- **Purpose**: Shows current weather information
- **Features**:
  - Large temperature display
  - Placeholder for weather data integration
  - Extensible for weather icons, conditions, etc.

### Google Calendar Widget (`google_calendar_widget.py`)
- **Purpose**: Displays upcoming Google Calendar events
- **Features**:
  - Shows next 5 upcoming events
  - User-specific calendar integration
  - Automatic refresh every 5 minutes
  - Date and event title display
  - Handles authentication and API calls

## Usage

```python
from widgets import ClockWidget, WeatherWidget, GoogleCalendarWidget

# Create widgets
clock = ClockWidget(50, 50, 400, 200)
weather = WeatherWidget(50, 270, 300, 200)
calendar = GoogleCalendarWidget(370, 270, 400, 300, user_name="john")

# Update and draw in main loop
for widget in [clock, weather, calendar]:
    widget.update(scroll_y)
    widget.draw(surface, font_title, font_content, scroll_y)
```

## Customization

Each widget can be customized by:
- **Colors**: Modify `config.py` color constants
- **Fonts**: Change font sizes in widget `__init__` methods
- **Layout**: Adjust positioning and spacing in `draw` methods
- **Behavior**: Override `update` methods for custom logic

## Adding New Widgets

To create a new widget:

1. Create a new file `widgets/new_widget.py`
2. Inherit from the `Widget` base class
3. Implement `__init__`, `update`, and `draw` methods
4. Add import to `widgets/__init__.py`
5. Update `smart_mirror_pro.py` to handle the new widget type

Example structure:
```python
from .base_widget import Widget
from utils.fonts import get_font
from config import *

class NewWidget(Widget):
    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h, "Title")
        # Initialize your widget

    def update(self, scroll_y=0):
        super().update(scroll_y)
        # Update logic

    def draw(self, surface, font_title, font_content, scroll_y=0):
        super().draw(surface, font_title, font_content, scroll_y)
        # Custom drawing logic
```
