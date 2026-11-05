# mirror/widgets/exam_pdf_viewer.py
"""The school's exam timetable, full screen, for a hand to scroll.

assets/exam_timetable.png is page 1 of the PDF on the website
(web/public/2026-Exam-Timetable.pdf) drawn at 200 dpi; to update it:

    import pymupdf
    pymupdf.open("2026-Exam-Timetable.pdf")[0].get_pixmap(dpi=200).save("mirror/assets/exam_timetable.png")

It is drawn as wide as the screen allows so the small print is readable from a
metre away, which makes it taller than the screen: a pinch-and-drag scrolls it,
the same as every other list on the mirror.
"""
import os

from PyQt6.QtCore import Qt, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

IMAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'assets', 'exam_timetable.png')


class ExamPdfViewer(QWidget):
    closed = pyqtSignal()

    HEADER_H = 110
    MARGIN = 36
    CLOSE_W, CLOSE_H = 280, 76

    def __init__(self, parent=None, image_path=IMAGE_PATH):
        super().__init__(parent)
        self._image_path = image_path
        self._source = None               # loaded when first opened, not at start-up
        self._scaled = None
        self._scaled_w = 0
        self._scroll = 0.0
        self._close_hover = False
        self.hide()

    # ── geometry ──
    def close_rect(self):
        """The CLOSE button, in this widget's coordinates."""
        return QRect(self.width() - self.MARGIN - self.CLOSE_W, (self.HEADER_H - self.CLOSE_H) // 2,
                     self.CLOSE_W, self.CLOSE_H)

    def area(self):
        return QRect(0, self.HEADER_H, self.width(), max(1, self.height() - self.HEADER_H))

    def _page(self):
        """The page scaled to the screen's width (kept until the size changes)."""
        w = max(1, self.width() - 2 * self.MARGIN)
        if self._source is None:
            self._source = QPixmap(self._image_path)
        if self._scaled is None or self._scaled_w != w:
            self._scaled = (self._source.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
                            if not self._source.isNull() else QPixmap())
            self._scaled_w = w
        return self._scaled

    def scroll_max(self):
        return max(0.0, self._page().height() + self.MARGIN - self.area().height())

    def scroll_by(self, delta):
        self._scroll = max(0.0, min(self.scroll_max(), self._scroll + delta))
        self.update()

    def open(self):
        self._scroll = 0.0
        self._close_hover = False
        self.show()
        self.raise_()
        self.update()

    def close_viewer(self):
        self.hide()
        self.closed.emit()

    # ── input: from the hand (a point in this widget, the gesture event, its scroll delta) ──
    def handle(self, point, event, delta=0):
        hover = self.close_rect().adjusted(-24, -24, 24, 24).contains(point)
        if hover != self._close_hover:
            self._close_hover = hover
            self.update()
        if event == "tap" and hover:
            self.close_viewer()
        elif event in ("scroll", "fling") and delta:
            self.scroll_by(delta)

    # ── input: a mouse, for testing at a desk ──
    def wheelEvent(self, e):
        self.scroll_by(-e.angleDelta().y())

    def mousePressEvent(self, e):
        if self.close_rect().contains(e.position().toPoint()):
            self.close_viewer()

    # ── drawing ──
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0))

        page = self._page()
        top = self.HEADER_H
        p.save()
        p.setClipRect(self.area())
        if not page.isNull():
            p.drawPixmap(self.MARGIN, int(top - self._scroll), page)
        else:
            self._text(p, "The exam timetable could not be loaded.", self.area(), 28, QFont.Weight.DemiBold, '#cbd5e1',
                       Qt.AlignmentFlag.AlignCenter)
        p.restore()

        # header, drawn over the page so it never scrolls under
        p.fillRect(0, 0, self.width(), top, QColor(0, 0, 0))
        p.fillRect(0, top - 2, self.width(), 2, QColor(30, 41, 59))
        self._text(p, "EXAM TIMETABLE", QRect(self.MARGIN, 0, self.width() // 2, top), 40, QFont.Weight.Black, '#ffffff',
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, spacing=4)
        self._text(p, "pinch and drag to scroll", QRect(self.MARGIN + 520, 0, 420, top), 20, QFont.Weight.DemiBold,
                   '#94a3b8', Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        r = self.close_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#ffffff') if self._close_hover else QColor('#1e293b'))
        p.drawRoundedRect(QRectF(r), 38, 38)
        self._text(p, "CLOSE  ✕", r, 28, QFont.Weight.Black, '#000000' if self._close_hover else '#e2e8f0',
                   Qt.AlignmentFlag.AlignCenter, spacing=3)

        # how far down you are
        if self.scroll_max() > 0:
            track = QRectF(self.width() - 14, top + 12, 5, self.area().height() - 24)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawRoundedRect(track, 2.5, 2.5)
            thumb_h = max(40.0, track.height() * self.area().height() / (self._page().height() + self.MARGIN))
            y = track.top() + (track.height() - thumb_h) * (self._scroll / self.scroll_max())
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawRoundedRect(QRectF(track.left(), y, 5, thumb_h), 2.5, 2.5)
        p.end()

    @staticmethod
    def _text(p, text, rect, px, weight, color, align, spacing=0):
        font = p.font()
        font.setFamily("Segoe UI")
        font.setPixelSize(px)
        font.setWeight(weight)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(rect, align, text)
