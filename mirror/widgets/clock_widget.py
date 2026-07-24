# mirror/widgets/clock_widget.py
import datetime
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QFrame, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class ClockWidget(QFrame):
    """Header clock row: Date on left, time on right with bottom line divider matching new-style.html."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ClockWidget")
        self.setStyleSheet("""
            #ClockWidget {
                background: transparent;
                border: none;
                border-bottom: 1px solid #1c1c1c;
                padding-bottom: 12px;
            }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 12)

        self.date_label = QLabel("Wed, 22 Jul", self)
        self.date_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 18px; color: #d0d0d0; background: transparent; border: none;"
        )

        self.time_label = QLabel("10:36", self)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setStyleSheet(
            "font-family: 'Consolas', 'SFMono-Regular', monospace; font-size: 44px; font-weight: 600; color: #ffffff; background: transparent; border: none;"
        )

        lay.addWidget(self.date_label)
        lay.addStretch(1)
        lay.addWidget(self.time_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

    def _tick(self):
        now = datetime.datetime.now()
        # Windows strftime: %#d instead of %-d
        try:
            day_str = now.strftime("%a, %#d %b")
        except ValueError:
            day_str = now.strftime("%a, %d %b")
        time_str = now.strftime("%H:%M")

        self.date_label.setText(day_str)
        self.time_label.setText(time_str)

