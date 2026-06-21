# mirror/widgets/note_widget.py
import time
from datetime import datetime, timezone
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer
from .base_widget import Widget

def _parse_iso(dt_str):
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).timestamp()
        return dt.timestamp()
    except Exception:
        return None

class NoteWidget(Widget):
    """Plain note text matching web readonly .widget-note-view."""

    def __init__(self, x, y, w, h, data=None):
        super().__init__(x, y, w, h, "", chromeless=True)
        if isinstance(data, dict):
            self.text = data.get('text', '') or ''
            self.expire_at = _parse_iso(data.get('expireAt'))
        elif isinstance(data, str):
            self.text = data or ''
            self.expire_at = None
        else:
            self.text = ''
            self.expire_at = None

        self.body_label = QLabel(self.text if self.text else 'No note written.', self)
        self.body_label.setWordWrap(True)
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body_label.setStyleSheet("font-size: 14px; color: #e6e6e6; line-height: 1.5;")
        
        self.badge_label = QLabel(self)
        self.badge_label.setStyleSheet("font-size: 11px; font-weight: bold; border-radius: 6px; padding: 2px 6px;")
        self.badge_label.hide()
        
        self.main_layout.addWidget(self.body_label, 1)
        self.main_layout.addWidget(self.badge_label)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_expiry)
        self.timer.start(5000)
        self.check_expiry()

    def check_expiry(self):
        if self.expire_at is not None and time.time() >= self.expire_at:
            self.hide()
            return
            
        if self.expire_at is not None:
            diff = self.expire_at - time.time()
            mins_left = 0 if diff <= 0 else int(diff / 60) + 1
            if mins_left <= 10:
                badge_color = "#ef4444" if mins_left <= 2 else "#fbbf24"
                self.badge_label.setText(f"Expires in {mins_left} min" if mins_left > 0 else "Expired")
                self.badge_label.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {badge_color};")
                self.badge_label.show()
