# mirror/widgets/clock_widget.py
import datetime
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer
from .base_widget import Widget

class ClockWidget(Widget):
    """Centered clock matching web .widget-clock (large time + dim date below)."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h, "", chromeless=True)
        
        self.time_label = QLabel(self)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("font-size: 42px; font-weight: 300; color: #ffffff;")
        
        self.date_label = QLabel(self)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 180); font-weight: 500;")
        
        self.main_layout.addWidget(self.time_label)
        self.main_layout.addWidget(self.date_label)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()
        
    def update_time(self):
        now = datetime.datetime.now()
        time_part = now.strftime("%I:%M").lstrip("0")
        ampm = now.strftime("%p").lower()
        self.time_label.setText(f"{time_part} {ampm}")
        self.date_label.setText(now.strftime("%A, %d %B"))
