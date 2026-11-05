# mirror/widgets/exam_pdf_viewer.py
"""The school's exam timetable, full screen, for a hand to scroll.

The PDF is NZQA's, which the server fetches from their site each year and serves
at /api/exam-timetable.pdf. The mirror keeps a copy, checks for a newer one every
few hours, and draws its pages with Qt's PDF module. If there is no copy yet (or
the Qt module is missing) it shows assets/exam_timetable.png, a picture of the 2026
timetable that ships with the mirror.

It is drawn as wide as the screen allows so the small print is readable from a
metre away, which makes it taller than the screen: a pinch-and-drag scrolls it,
the same as every other list on the mirror.
"""
import os
import tempfile
import threading

import requests
from PyQt6.QtCore import Qt, QRect, QRectF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

try:
    from PyQt6.QtPdf import QPdfDocument
except ImportError:                       # no PDF module: the bundled picture is used
    QPdfDocument = None

IMAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'assets', 'exam_timetable.png')


class ExamPdfViewer(QWidget):
    closed = pyqtSignal()
    refreshed = pyqtSignal()              # a newer PDF arrived (from the download thread)
    REFRESH_MS = 6 * 3600 * 1000
    PAGE_GAP = 20

    HEADER_H = 110
    MARGIN = 36
    CLOSE_W, CLOSE_H = 280, 76

    def __init__(self, parent=None, image_path=IMAGE_PATH, api_url=None, cache_path=None):
        super().__init__(parent)
        self._image_path = image_path
        self._api_url = api_url
        self._cache = cache_path or os.path.join(tempfile.gettempdir(), 'smartmirror_exam_timetable.pdf')
        self._source = None               # loaded when first opened, not at start-up
        self._source_key = None
        self.refreshed.connect(self._on_refreshed)
        if api_url:
            QTimer.singleShot(20000, self.refresh)      # after start-up has settled
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh)
            self._timer.start(self.REFRESH_MS)
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

    # ── the PDF: fetched from the server, drawn with Qt ──
    def refresh(self):
        """Look for a newer PDF on the server (in the background)."""
        if self._api_url:
            threading.Thread(target=self._download, daemon=True).start()

    def _download(self):
        headers = {}
        if os.path.exists(self._cache):
            from email.utils import formatdate
            headers['If-Modified-Since'] = formatdate(os.path.getmtime(self._cache), usegmt=True)
        try:
            res = requests.get(f"{self._api_url}/api/exam-timetable.pdf", headers=headers, timeout=30)
            if res.status_code == 200 and res.content.startswith(b'%PDF'):
                tmp = self._cache + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(res.content)
                os.replace(tmp, self._cache)
                self.refreshed.emit()
        except Exception as e:
            print(f"[EXAMS] Could not fetch the exam timetable: {e}", flush=True)

    def _on_refreshed(self):
        self._scaled = None                # redrawn from the new file next time
        self.update()

    def _render_pdf(self, width):
        """Every page of the cached PDF, stacked, width pixels wide (None if it can't be drawn)."""
        if QPdfDocument is None or not os.path.exists(self._cache):
            return None
        doc = QPdfDocument(self)
        try:
            if doc.load(self._cache) != QPdfDocument.Error.None_ or doc.pageCount() < 1:
                return None
            images = []
            for i in range(doc.pageCount()):
                size = doc.pagePointSize(i)
                if size.width() <= 0:
                    return None
                images.append(doc.render(i, QSize(width, max(1, int(width * size.height() / size.width())))))
            total = sum(img.height() for img in images) + self.PAGE_GAP * (len(images) - 1)
            pm = QPixmap(width, total)
            pm.fill(QColor('#ffffff'))
            p = QPainter(pm)
            y = 0
            for img in images:
                p.drawImage(0, y, img)
                y += img.height() + self.PAGE_GAP
            p.end()
            return pm
        finally:
            doc.close()
            doc.deleteLater()

    def _page(self):
        """The pages scaled to the screen's width (kept until the size or the file changes)."""
        w = max(1, self.width() - 2 * self.MARGIN)
        stamp = os.path.getmtime(self._cache) if os.path.exists(self._cache) else None
        if self._scaled is None or self._scaled_w != w or self._source_key != stamp:
            pm = self._render_pdf(w)
            if pm is None:
                if self._source is None:
                    self._source = QPixmap(self._image_path)
                pm = (self._source.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)
                      if not self._source.isNull() else QPixmap())
            self._scaled, self._scaled_w, self._source_key = pm, w, stamp
        return self._scaled

    def scroll_max(self):
        return max(0.0, self._page().height() + self.MARGIN - self.area().height())

    def scroll_by(self, delta):
        self._scroll = max(0.0, min(self.scroll_max(), self._scroll + delta))
        self.update()

    def open(self):
        self.refresh()                     # next time it opens it will be the newest
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
