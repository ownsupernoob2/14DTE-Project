import os
import requests
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont, QImage

class KingsWeekWidget(QFrame):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self.api_url = "http://localhost:8080/api/kings-week"
        
        # Styles
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 20, 180);
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        
        self.title_label = QLabel("Loading Kings Week...")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Inter", 18, QFont.Bold))
        self.title_label.setStyleSheet("color: white;")
        
        self.edition_label = QLabel("")
        self.edition_label.setAlignment(Qt.AlignCenter)
        self.edition_label.setFont(QFont("Inter", 14))
        self.edition_label.setStyleSheet("color: #cccccc;")
        
        self.layout.addWidget(self.image_label)
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.edition_label)
        
        # Update timer (every 1 hour)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_data)
        self.timer.start(3600 * 1000)
        
        self.update_data()
        
    def update_data(self):
        try:
            res = requests.get(self.api_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                self.title_label.setText(data.get("title", ""))
                
                date_str = data.get("date", "")
                edition = data.get("edition", "")
                self.edition_label.setText(f"{edition} • {date_str}")
                
                # Fetch image
                img_url = data.get("imageUrl")
                if img_url:
                    img_res = requests.get(img_url, timeout=10)
                    if img_res.status_code == 200:
                        image = QImage()
                        image.loadFromData(img_res.content)
                        pixmap = QPixmap.fromImage(image)
                        
                        # Scale down to fit layout
                        pixmap = pixmap.scaled(550, 350, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.image_label.setPixmap(pixmap)
        except Exception as e:
            print(f"KingsWeekWidget fetch error: {e}")
