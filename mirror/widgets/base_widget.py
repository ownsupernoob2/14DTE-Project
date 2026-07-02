# mirror/widgets/base_widget.py
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont

class Widget(QFrame):
    """Base QFrame widget wrapper supporting layout orientations and theme styling."""
    
    def __init__(self, x, y, w, h, title="", chromeless=False):
        super().__init__()
        self.title = title
        self.chromeless = chromeless
        self.target_pos = [x, y]
        self.orientation = "horizontal" # default
        
        self.setGeometry(x, y, w, h)
        
        self.main_layout = None
        self.setup_container()
        self.drag_position = None

    def setup_container(self):
        if not self.chromeless:
            self.setObjectName("WidgetContainer")
            self.setStyleSheet("""
                #WidgetContainer {
                    background-color: rgba(10, 10, 18, 166);
                    border: 1px solid rgba(255, 255, 255, 18);
                    border-radius: 16px;
                }
                #WidgetContainer:hover {
                    border-color: rgba(59, 130, 246, 97);
                }
            """)
            
            # Setup layout based on orientation
            if self.orientation == "vertical":
                self.main_layout = QVBoxLayout(self)
            else:
                self.main_layout = QHBoxLayout(self)

            self.main_layout.setContentsMargins(16, 16, 16, 16)
            self.main_layout.setSpacing(10)
            
            if self.title:
                self.title_label = QLabel(self.title.upper())
                self.title_label.setStyleSheet("""
                    font-size: 11px;
                    font-weight: bold;
                    color: rgba(255, 255, 255, 115);
                    letter-spacing: 2px;
                """)
                self.main_layout.addWidget(self.title_label)
        else:
            self.setObjectName("ChromelessWidget")
            self.setStyleSheet("#ChromelessWidget { background: transparent; border: none; }")
            if self.orientation == "vertical":
                self.main_layout = QVBoxLayout(self)
            else:
                self.main_layout = QHBoxLayout(self)
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)

    def set_orientation(self, orientation):
        """Dynamically switch widget layout orientation."""
        if self.orientation == orientation:
            return
        self.orientation = orientation
        # Reparent layout
        if self.main_layout is not None:
            # Clear old layout
            QWidget().setLayout(self.main_layout)
        
        if orientation == "vertical":
            self.main_layout = QVBoxLayout(self)
        else:
            self.main_layout = QHBoxLayout(self)
        
        self.main_layout.setContentsMargins(16 if not self.chromeless else 0, 16 if not self.chromeless else 0, 16 if not self.chromeless else 0, 16 if not self.chromeless else 0)
        self.main_layout.setSpacing(10)
        
        if not self.chromeless and self.title:
            self.title_label = QLabel(self.title.upper())
            self.main_layout.addWidget(self.title_label)
        
        self.on_orientation_changed()

    def on_orientation_changed(self):
        """Subclasses override this to reposition child widgets."""
        pass

    def apply_theme(self, primary_color, secondary_color, font_family):
        """Apply dynamic color and font configurations to widget."""
        if not self.chromeless:
            self.setStyleSheet(f"""
                #WidgetContainer {{
                    background-color: rgba(10, 10, 18, 166);
                    border: 1px solid {secondary_color}44;
                    border-radius: 16px;
                }}
                #WidgetContainer:hover {{
                    border-color: {primary_color};
                }}
            """)
        
        font = QFont(font_family)
        self.setFont(font)
        
        if hasattr(self, 'title_label') and self.title_label:
            self.title_label.setFont(font)
            self.title_label.setStyleSheet(f"""
                font-size: 11px;
                font-weight: bold;
                color: {primary_color};
                letter-spacing: 2px;
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        parent = self.parentWidget()
        if parent:
            screen_w = parent.width()
            screen_h = parent.height()
            col_width = screen_w / 12
            row_height = screen_h / 12
            col = round(self.x() / col_width)
            row = round(self.y() / row_height)
            col = max(0, min(col, 11))
            row = max(0, min(row, 11))
            
            target_x = int(col * col_width + 20)
            target_y = int(row * row_height + 20)
            
            self.anim = QPropertyAnimation(self, b"pos")
            self.anim.setDuration(250)
            self.anim.setEndValue(QPoint(target_x, target_y))
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.anim.start()
            event.accept()
