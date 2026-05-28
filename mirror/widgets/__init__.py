# widgets/__init__.py
# Widget package for Smart Mirror

from .base_widget import Widget
from .clock_widget import ClockWidget
from .weather_widget import WeatherWidget
from .google_calendar_widget import GoogleCalendarWidget
from .voice_assistant_widget import VoiceAssistantWidget
from .notices_widget import NoticesWidget
from .timetable_widget import TimetableWidget
from .note_widget import NoteWidget

__all__ = ['Widget', 'ClockWidget', 'WeatherWidget', 'GoogleCalendarWidget', 'VoiceAssistantWidget', 'NoticesWidget', 'TimetableWidget', 'NoteWidget']
