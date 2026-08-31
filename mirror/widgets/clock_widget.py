# mirror/widgets/clock_widget.py
import datetime
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer


class ClockWidget(QFrame):
    """Header clock row: Date on left, Time on right matching the web screenshot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ClockWidget")
        self.setStyleSheet("""
            #ClockWidget {
                background: transparent;
                border: none;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.date_label = QLabel("", self)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.date_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
            "font-size: 38px; font-weight: 700; color: #ffffff; background: transparent; border: none;"
        )

        self.time_label = QLabel("", self)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', 'Segoe UI', monospace; "
            "font-size: 38px; font-weight: 700; color: #ffffff; background: transparent; border: none;"
        )

        lay.addWidget(self.date_label, 1)
        lay.addWidget(self.time_label, 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        day_str = f"{now.strftime('%a')}, {now.day} {now.strftime('%b')}"
        time_str = now.strftime("%I:%M %p").lstrip('0')

        self.date_label.setText(day_str)
        self.time_label.setText(time_str)



