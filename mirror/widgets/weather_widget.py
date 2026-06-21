# mirror/widgets/weather_widget.py
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt
from .base_widget import Widget

class WeatherWidget(Widget):
    """Widget displaying current weather temperature."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h, "Weather")
        self.temp = "72°"
        
        self.temp_label = QLabel(self.temp, self)
        self.temp_label.setStyleSheet("font-size: 56px; font-weight: 300; color: #ffffff;")
        self.temp_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.main_layout.addWidget(self.temp_label)
        self.main_layout.addStretch()

    def set_temperature(self, temp):
        if self.temp != temp:
            self.temp = temp
            self.temp_label.setText(temp)
