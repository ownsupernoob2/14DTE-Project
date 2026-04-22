# widgets/__init__.py
# Widget package for Smart Mirror

from .base_widget import Widget
from .clock_widget import ClockWidget
from .weather_widget import WeatherWidget
from .google_calendar_widget import GoogleCalendarWidget
from .voice_assistant_widget import VoiceAssistantWidget

__all__ = ['Widget', 'ClockWidget', 'WeatherWidget', 'GoogleCalendarWidget', 'VoiceAssistantWidget']
