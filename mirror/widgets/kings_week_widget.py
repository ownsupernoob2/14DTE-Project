# mirror/widgets/kings_week_widget.py
import os
import threading
import requests
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QFont, QImage


class KingsWeekWidget(QFrame):
    """Center-bottom panel: shows the latest King's Week cover image + title."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_url = os.environ.get('API_URL', 'https://api.smartmirror.me') + '/api/kings-week'

        self.setObjectName("KingsWeekWidget")
        self.setStyleSheet("""
            #KingsWeekWidget {
                background-color: rgba(10, 10, 18, 100);
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 15);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Image label — fills the widget, image as background-style pixmap
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setStyleSheet("border-radius: 14px; background: transparent;")
        layout.addWidget(self.image_label, 1)

        # Overlay strip at the bottom
        self.overlay = QFrame()
        self.overlay.setObjectName("KWOverlay")
        self.overlay.setStyleSheet("""
            #KWOverlay {
                background: rgba(5, 5, 10, 180);
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
                border-top: 1px solid rgba(255, 255, 255, 10);
            }
        """)
        self.overlay.setFixedHeight(64)
        layout.addWidget(self.overlay)

        ov_lay = QVBoxLayout(self.overlay)
        ov_lay.setContentsMargins(14, 8, 14, 8)
        ov_lay.setSpacing(2)

        self.edition_label = QLabel("King's Week")
        self.edition_label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #c4b5fd; "
            "letter-spacing: 1px; text-transform: uppercase; background: transparent; border: none;"
        )
        ov_lay.addWidget(self.edition_label)

        self.title_label = QLabel("Loading…")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #ffffff; background: transparent; border: none;"
        )
        ov_lay.addWidget(self.title_label)

        # Fetch on startup, then every hour
        self._fetch()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fetch)
        self._timer.start(3600 * 1000)

    def _fetch(self):
        threading.Thread(target=self._do_fetch, daemon=True).start()

    def _do_fetch(self):
        try:
            res = requests.get(self.api_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                QTimer.singleShot(0, lambda: self._apply_data(data))
        except Exception as e:
            print(f"[KingsWeekWidget] fetch error: {e}")

    def _apply_data(self, data):
        title   = data.get('title', '')
        edition = data.get('edition', '')
        date    = data.get('date', '')
        img_url = data.get('imageUrl', '')

        self.title_label.setText(title)
        self.edition_label.setText(f"{edition}  •  {date}" if edition else date)

        if img_url:
            threading.Thread(target=self._load_image, args=(img_url,), daemon=True).start()

    def _load_image(self, url):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                img = QImage()
                img.loadFromData(r.content)
                QTimer.singleShot(0, lambda: self._set_image(img))
        except Exception as e:
            print(f"[KingsWeekWidget] image error: {e}")

    def _set_image(self, img):
        pixmap = QPixmap.fromImage(img)
        self.image_label.setPixmap(pixmap)
