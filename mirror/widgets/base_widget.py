# mirror/widgets/base_widget.py
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve

class Widget(QFrame):
    """Base QFrame widget wrapper supporting absolute position dragging & snapping."""
    
    def __init__(self, x, y, w, h, title="", chromeless=False):
        super().__init__()
        self.title = title
        self.chromeless = chromeless
        self.target_pos = [x, y]
        
        self.setGeometry(x, y, w, h)
        
        # Stylesheet setup
        if not chromeless:
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
            
            # Layout
            self.main_layout = QVBoxLayout(self)
            self.main_layout.setContentsMargins(16, 16, 16, 16)
            self.main_layout.setSpacing(10)
            
            # Title
            if title:
                self.title_label = QLabel(title.upper())
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
            self.main_layout = QVBoxLayout(self)
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)
            
        self.drag_position = None

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
        # Snap to grid
        parent = self.parentWidget()
        if parent:
            screen_w = parent.width()
            screen_h = parent.height()
            col_width = screen_w / 12  # GRID_COLS
            row_height = screen_h / 12  # GRID_ROWS
            col = round(self.x() / col_width)
            row = round(self.y() / row_height)
            col = max(0, min(col, 11))
            row = max(0, min(row, 11))
            
            target_x = int(col * col_width + 20)
            target_y = int(row * row_height + 20)
            
            # Smoothly snap to grid using QPropertyAnimation
            self.anim = QPropertyAnimation(self, b"pos")
            self.anim.setDuration(250)
            self.anim.setEndValue(QPoint(target_x, target_y))
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.anim.start()
            event.accept()
