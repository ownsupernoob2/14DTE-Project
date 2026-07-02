# mirror/widgets/clock_widget.py
import datetime
from PyQt6.QtWidgets import QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from .base_widget import Widget


class ClockWidget(Widget):
    """Large centered clock — big time on top, dimmer date below."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h, "", chromeless=True)

        self.time_label = QLabel(self)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet(
            "font-size: 72px; font-weight: 200; color: #ffffff; letter-spacing: -2px; background: transparent; border: none;"
        )

        self.date_label = QLabel(self)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_label.setStyleSheet(
            "font-size: 16px; color: rgba(255, 255, 255, 140); font-weight: 400; background: transparent; border: none;"
        )

        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(self.time_label)
        self.main_layout.addWidget(self.date_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        self.time_label.setText(now.strftime("%-I:%M %p"))
        self.date_label.setText(now.strftime("%A, %-d %B %Y"))
