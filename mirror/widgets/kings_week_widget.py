# mirror/widgets/kings_week_widget.py
"""King's Week: the school's weekly publication, as a gesture-driven grid.

The panel lives underneath the timetable peek on the right of the mirror. Once
the timetable slides out of the way this grid takes over the column: the latest
story gets a full-width feature box and the rest follow in pairs beneath it.

There is no cursor on a mirror, so nothing here hovers. The published palm
position picks the *nearest box* — selection is always locked onto one of them —
and the scroll comes to rest aligned to a box rather than halfway through one.
A tap opens the selected story in a modal that grows out of its box.

Data comes from GET /api/kings-week, which the Go server scrapes hourly.
"""

import math
import threading

import requests
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea,
    QGridLayout, QGraphicsOpacityEffect, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QTimer, QObject, QRect, QRectF, QPoint, QPropertyAnimation,
    QEasingCurve, pyqtSignal
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPainterPath, QColor, QPen, QBrush,
    QLinearGradient
)

ACCENT = '#4fc3ff'          # same accent as the timetable peek and notices
CARD_RADIUS = 14

GRID_COLUMNS = 2
FEATURE_MIN_HEIGHT = 210    # the latest story, spanning the full width
CARD_MIN_HEIGHT = 132
GRID_SPACING = 12

SCROLL_SNAP_MS = 260        # quiet time after a scroll before it locks to a box
SCROLL_SNAP_ANIM_MS = 260
MODAL_ANIM_MS = 340
MODAL_MARGIN = 14

REFRESH_MS = 15 * 60 * 1000


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def rect_distance(rect, x, y):
    """Distance from a point to a QRect — 0 when the point is inside it.

    This is what locks the selection onto a box: whatever the hand points at,
    including the gaps between boxes and the margins around them, resolves to
    exactly one box.
    """
    dx = max(rect.left() - x, 0, x - (rect.left() + rect.width()))
    dy = max(rect.top() - y, 0, y - (rect.top() + rect.height()))
    return math.hypot(dx, dy)


# ─────────────────────────────────────────────────────────────────────────────
# Image loading
# ─────────────────────────────────────────────────────────────────────────────

class _ImageStore(QObject):
    """Fetches article art off the GUI thread.

    QImage can be decoded on a worker thread but QPixmap cannot be touched off
    the GUI thread, so the worker emits a QImage and the (queued) slot does the
    conversion.
    """

    ready = pyqtSignal(str, QImage)
    changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps = {}
        self._inflight = set()
        self._lock = threading.Lock()
        self.ready.connect(self._store)

    def pixmap(self, url):
        return self._pixmaps.get(url)

    def request(self, url):
        if not url or url in self._pixmaps:
            return
        with self._lock:
            if url in self._inflight:
                return
            self._inflight.add(url)
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url):
        try:
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                img = QImage()
                if img.loadFromData(res.content):
                    self.ready.emit(url, img)
        except Exception as e:
            print(f"[KingsWeek] image failed ({url}): {e}")
        finally:
            with self._lock:
                self._inflight.discard(url)

    def _store(self, url, img):
        self._pixmaps[url] = QPixmap.fromImage(img)
        self.changed.emit(url)


# ─────────────────────────────────────────────────────────────────────────────
# One grid box
# ─────────────────────────────────────────────────────────────────────────────

class ArticleCard(QFrame):
    """One story. The photo is painted as a cover-fitted background with a
    scrim over it, so the text stays readable whatever the photo looks like."""

    def __init__(self, article, feature=False, parent=None):
        super().__init__(parent)
        self.article = article
        self.feature = feature
        self.image_url = article.get('imageUrl') or ''

        self._pixmap = None
        self._scaled = None
        self._selected = False

        self.setMinimumHeight(FEATURE_MIN_HEIGHT if feature else CARD_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_ui()

    # ── Build ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        pad = 14 if self.feature else 10
        lay.setContentsMargins(pad, pad, pad, pad)
        lay.setSpacing(4)
        lay.addStretch(1)   # push the text block to the bottom, over the scrim

        meta = ' • '.join(x for x in (self.article.get('author', ''),
                                      self.article.get('date', '')) if x)
        if meta:
            self.meta_lbl = QLabel(meta, self)
            self.meta_lbl.setStyleSheet(
                f"font-size: {10 if self.feature else 9}px; font-weight: 700; "
                f"letter-spacing: 1px; color: {ACCENT}; background: transparent; border: none;"
            )
            lay.addWidget(self.meta_lbl)

        self.title_lbl = QLabel(self.article.get('title', ''), self)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            f"font-size: {17 if self.feature else 12}px; font-weight: 700; "
            f"color: #ffffff; background: transparent; border: none;"
        )
        lay.addWidget(self.title_lbl)

        # Only the feature box has the room for a standfirst.
        if self.feature and self.article.get('summary'):
            self.summary_lbl = QLabel(self.article['summary'], self)
            self.summary_lbl.setWordWrap(True)
            self.summary_lbl.setStyleSheet(
                "font-size: 11px; color: #c9c9d4; background: transparent; border: none;"
            )
            lay.addWidget(self.summary_lbl)

    # ── State ────────────────────────────────────────────────────────────────

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self._scaled = None
        self.update()

    def set_selected(self, selected):
        if selected == self._selected:
            return
        self._selected = selected
        self.update()

    @property
    def selected(self):
        return self._selected

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scaled = None   # the cover fit depends on the box size

    # ── Paint ────────────────────────────────────────────────────────────────

    def _cover_pixmap(self):
        """The photo scaled to fill the box, cached per size."""
        if self._pixmap is None or self._pixmap.isNull():
            return None
        if self._scaled is None or self._scaled.size() != self.size():
            self._scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        return self._scaled

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        rect = self.rect()
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(rect), CARD_RADIUS, CARD_RADIUS)

        painter.setClipPath(shape)
        painter.fillPath(shape, QColor(12, 12, 18))

        cover = self._cover_pixmap()
        if cover is not None:
            painter.setOpacity(1.0 if self._selected else 0.78)
            painter.drawPixmap(
                (rect.width() - cover.width()) // 2,
                (rect.height() - cover.height()) // 2,
                cover,
            )
            painter.setOpacity(1.0)

        # Dark at the bottom where the text sits, clear at the top.
        scrim = QLinearGradient(0, rect.height() * 0.18, 0, rect.height())
        scrim.setColorAt(0.0, QColor(6, 6, 12, 40))
        scrim.setColorAt(0.55, QColor(5, 5, 11, 175))
        scrim.setColorAt(1.0, QColor(3, 3, 8, 240))
        painter.fillPath(shape, QBrush(scrim))

        painter.setClipping(False)
        painter.setPen(QPen(QColor(ACCENT) if self._selected else QColor(255, 255, 255, 26),
                            2 if self._selected else 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = 1.0 if self._selected else 0.5
        painter.drawRoundedRect(
            QRectF(rect).adjusted(inset, inset, -inset, -inset), CARD_RADIUS, CARD_RADIUS
        )
        painter.end()


# ─────────────────────────────────────────────────────────────────────────────
# The article modal
# ─────────────────────────────────────────────────────────────────────────────

class ArticleModal(QFrame):
    """The full story, grown out of the box that was tapped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KWModal")
        self.setStyleSheet(f"""
            #KWModal {{
                background-color: #07070c;
                border-radius: 16px;
                border: 1px solid {ACCENT};
            }}
        """)
        self._anim = None

        # One opacity layer for the modal's whole life, switched off when it is
        # not fading. Creating and destroying it around each animation is the
        # obvious alternative and it crashes: clearing a graphics effect deletes
        # it, and the fade is still pointing at it.
        self._effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self._effect)
        self._effect.setEnabled(False)

        self._build_ui()
        self.hide()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.eyebrow = QLabel("KING'S WEEK", self)
        self.eyebrow.setStyleSheet(
            f"font-size: 9px; font-weight: 700; letter-spacing: 2px; "
            f"color: {ACCENT}; background: transparent; border: none;"
        )
        head.addWidget(self.eyebrow)
        head.addStretch(1)
        hint = QLabel("TAP TO CLOSE", self)
        hint.setStyleSheet(
            "font-size: 9px; font-weight: 700; letter-spacing: 1px; "
            "color: #55555f; background: transparent; border: none;"
        )
        head.addWidget(hint)
        root.addLayout(head)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet('background: transparent; border: none;')

        body = QWidget()
        body.setStyleSheet('background: transparent;')
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(10)

        self.hero = QLabel(body)
        self.hero.setScaledContents(False)
        self.hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hero.setStyleSheet('background: transparent; border: none;')
        self.hero.hide()
        body_lay.addWidget(self.hero)

        self.title_lbl = QLabel(body)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setStyleSheet(
            'font-size: 19px; font-weight: 700; color: #ffffff; '
            'background: transparent; border: none;'
        )
        body_lay.addWidget(self.title_lbl)

        self.meta_lbl = QLabel(body)
        self.meta_lbl.setStyleSheet(
            'font-size: 10px; font-weight: 600; letter-spacing: 1px; '
            'color: #8a8a96; background: transparent; border: none;'
        )
        body_lay.addWidget(self.meta_lbl)

        self.text_lbl = QLabel(body)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.text_lbl.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.text_lbl.setStyleSheet(
            'font-size: 12px; line-height: 150%; color: #d6d6de; '
            'background: transparent; border: none;'
        )
        body_lay.addWidget(self.text_lbl)

        self.link_lbl = QLabel(body)
        self.link_lbl.setWordWrap(True)
        self.link_lbl.setStyleSheet(
            'font-size: 9px; color: #4a4a55; background: transparent; border: none;'
        )
        body_lay.addWidget(self.link_lbl)
        body_lay.addStretch(1)

        self.scroll_area.setWidget(body)
        root.addWidget(self.scroll_area, 1)

    # ── Content ──────────────────────────────────────────────────────────────

    def set_article(self, article):
        self.title_lbl.setText(article.get('title', ''))
        meta = ' • '.join(x for x in (article.get('author', ''),
                                      article.get('date', '')) if x)
        self.meta_lbl.setText(meta)
        self.meta_lbl.setVisible(bool(meta))

        body = article.get('body') or article.get('summary') or ''
        self.text_lbl.setText(body)

        link = article.get('link', '')
        self.link_lbl.setText(f"Read the full story: {link}" if link else '')
        self.link_lbl.setVisible(bool(link))

        self.hero.clear()
        self.hero.hide()
        self.scroll_area.verticalScrollBar().setValue(0)

    def set_hero(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return
        width = max(120, self.scroll_area.viewport().width())
        self.hero.setPixmap(
            pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        )
        self.hero.show()

    def scroll_by_pixels(self, delta):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.value() + int(delta))

    # ── Animation ────────────────────────────────────────────────────────────

    def stop_animations(self):
        """Halt any open/close animation and take the opacity layer back out."""
        if self._anim:
            anims, self._anim = self._anim, None
            for anim in anims:
                anim.stop()
        self._effect.setEnabled(False)

    def hideEvent(self, event):
        # A modal that is off screen must not still be animating: the mirror can
        # retract the whole panel mid-fade, and an animation left running would
        # be driving a widget nobody can see — or, on teardown, one that is gone.
        self.stop_animations()
        super().hideEvent(event)

    def open_from(self, start_rect, end_rect):
        self.stop_animations()
        self.setGeometry(start_rect)
        self.show()
        self.raise_()

        self._effect.setEnabled(True)
        self._effect.setOpacity(0.0)

        fade = QPropertyAnimation(self._effect, b"opacity", self)
        fade.setDuration(MODAL_ANIM_MS)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        grow = QPropertyAnimation(self, b"geometry", self)
        grow.setDuration(MODAL_ANIM_MS)
        grow.setStartValue(start_rect)
        grow.setEndValue(end_rect)
        grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        # Switch the opacity layer off once it is fully open: leaving it on makes
        # every subsequent scroll repaint go through an offscreen buffer.
        grow.finished.connect(self.stop_animations)

        fade.start()
        grow.start()
        self._anim = (fade, grow)

    def close_to(self, end_rect, on_done=None):
        self.stop_animations()
        self._effect.setEnabled(True)
        self._effect.setOpacity(1.0)

        fade = QPropertyAnimation(self._effect, b"opacity", self)
        fade.setDuration(MODAL_ANIM_MS)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        shrink = QPropertyAnimation(self, b"geometry", self)
        shrink.setDuration(MODAL_ANIM_MS)
        shrink.setStartValue(self.geometry())
        shrink.setEndValue(end_rect)
        shrink.setEasingCurve(QEasingCurve.Type.InCubic)

        def done():
            self.hide()          # hideEvent stops the fade and drops the layer
            if on_done:
                on_done()

        shrink.finished.connect(done)
        fade.start()
        shrink.start()
        self._anim = (fade, shrink)


# ─────────────────────────────────────────────────────────────────────────────
# The panel
# ─────────────────────────────────────────────────────────────────────────────

class KingsWeekWidget(QFrame):
    """The King's Week grid, sitting below the timetable peek."""

    def __init__(self, parent=None, api_url='https://api.smartmirror.me'):
        super().__init__(parent)
        self.api_url = api_url.rstrip('/') + '/api/kings-week'

        self.setObjectName("KingsWeekWidget")
        self._apply_frame_style()

        self.cards = []
        self.selected_index = -1
        self.edition = {}
        self.articles = []
        self._gesture_active = False
        self._scroll_anim = None

        self.images = _ImageStore(self)
        self.images.changed.connect(self._on_image_ready)

        self._build_ui()

        self.modal = ArticleModal(self)
        self._modal_open = False
        self._modal_origin = None

        # Snap after the hand stops moving, not during — snapping mid-gesture
        # would fight whoever is still scrolling.
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.timeout.connect(self.snap_to_nearest_box)

        self.refresh()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(REFRESH_MS)

    # ── Build ────────────────────────────────────────────────────────────────

    def _apply_frame_style(self):
        border = ACCENT if getattr(self, '_gesture_active', False) else '#1c1c1c'
        self.setStyleSheet(f"""
            #KingsWeekWidget {{
                background-color: #000000;
                border-left: 1px solid {border};
                border-top: 1px solid #1c1c1c;
            }}
        """)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)

        eyebrow = QLabel("KING'S WEEK", self)
        eyebrow.setStyleSheet(
            f"font-size: 10px; font-weight: 700; letter-spacing: 2px; "
            f"color: {ACCENT}; background: transparent; border: none;"
        )
        head.addWidget(eyebrow)

        self.gesture_dot = QLabel('●', self)
        self.gesture_dot.setStyleSheet(
            f"font-size: 9px; color: {ACCENT}; background: transparent; border: none;"
        )
        self.gesture_dot.hide()
        head.addWidget(self.gesture_dot)
        head.addStretch(1)

        self.edition_lbl = QLabel('', self)
        self.edition_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 600; color: #6f6f7a; "
            "background: transparent; border: none;"
        )
        head.addWidget(self.edition_lbl)
        root.addLayout(head)

        div = QFrame(self)
        div.setFixedHeight(1)
        div.setStyleSheet('background: #1c1c1c;')
        root.addWidget(div)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet('background: transparent; border: none;')

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet('background: transparent;')
        self.grid = QGridLayout(self.grid_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(GRID_SPACING)
        self.scroll_area.setWidget(self.grid_container)
        root.addWidget(self.scroll_area, 1)

        self.status_lbl = QLabel('Loading King’s Week…', self)
        self.status_lbl.setStyleSheet(
            "font-size: 11px; color: #55555f; background: transparent; border: none;"
        )
        root.addWidget(self.status_lbl)

    # ── Data ─────────────────────────────────────────────────────────────────

    def refresh(self):
        threading.Thread(target=self._fetch_data, daemon=True).start()

    def _fetch_data(self):
        try:
            res = requests.get(self.api_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                QTimer.singleShot(0, lambda: self.apply_data(data))
        except Exception as e:
            print(f"[KingsWeek] fetch error: {e}")

    def apply_data(self, data):
        """Rebuild the grid from an /api/kings-week payload."""
        if not isinstance(data, dict):
            return

        self.edition = {
            'title':   data.get('title', ''),
            'edition': data.get('edition', ''),
            'date':    data.get('date', ''),
        }
        label = self.edition['edition'] or self.edition['title']
        if self.edition['date']:
            label = f"{label}  •  {self.edition['date']}" if label else self.edition['date']
        self.edition_lbl.setText(label)

        articles = [a for a in (data.get('articles') or []) if a.get('title')]
        self.set_articles(articles)

    def set_articles(self, articles):
        """Lay the stories out: the latest spans the full width, the rest pair up."""
        self.articles = articles
        self._clear_grid()

        if not articles:
            self.status_lbl.setText('King’s Week is not available right now.')
            self.status_lbl.show()
            return
        self.status_lbl.hide()

        for i, article in enumerate(articles):
            card = ArticleCard(article, feature=(i == 0), parent=self.grid_container)
            if i == 0:
                self.grid.addWidget(card, 0, 0, 1, GRID_COLUMNS)
            else:
                row = 1 + (i - 1) // GRID_COLUMNS
                self.grid.addWidget(card, row, (i - 1) % GRID_COLUMNS)
            self.cards.append(card)

            if card.image_url:
                cached = self.images.pixmap(card.image_url)
                if cached is not None:
                    card.set_pixmap(cached)
                else:
                    self.images.request(card.image_url)

        for col in range(GRID_COLUMNS):
            self.grid.setColumnStretch(col, 1)

        # Give the feature row twice the pull on any spare height, so with only
        # a handful of stories it still reads as the biggest box.
        self._rows = 1 + (max(0, len(articles) - 1) + GRID_COLUMNS - 1) // GRID_COLUMNS
        for row in range(self._rows):
            self.grid.setRowStretch(row, 2 if row == 0 else 1)

        self.select_index(0)

    def _clear_grid(self):
        for card in self.cards:
            self.grid.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self.cards = []
        self.selected_index = -1
        # Stretches outlive the widgets they were set for, so drop them too or a
        # shorter grid keeps reserving space for rows that no longer exist.
        for row in range(getattr(self, '_rows', 0)):
            self.grid.setRowStretch(row, 0)
        self._rows = 0

    def _on_image_ready(self, url):
        pixmap = self.images.pixmap(url)
        for card in self.cards:
            if card.image_url == url:
                card.set_pixmap(pixmap)
        if self._modal_open and self._selected_card() is not None:
            article = self._selected_card().article
            if url in (article.get('largeImageUrl'), article.get('imageUrl')):
                self.modal.set_hero(pixmap)

    @property
    def has_content(self):
        return bool(self.cards)

    # ── Selection ────────────────────────────────────────────────────────────

    def _selected_card(self):
        if 0 <= self.selected_index < len(self.cards):
            return self.cards[self.selected_index]
        return None

    def select_index(self, index):
        if not self.cards:
            self.selected_index = -1
            return None
        index = max(0, min(len(self.cards) - 1, index))
        if index == self.selected_index:
            return self.cards[index]
        for i, card in enumerate(self.cards):
            card.set_selected(i == index)
        self.selected_index = index
        return self.cards[index]

    def focus_at(self, x_frac, y_frac):
        """Lock the selection onto whichever box the hand is nearest.

        x_frac / y_frac are positions inside this panel, 0–1. A point in a gap
        or a margin still resolves to a box, so there is never a dead spot.
        """
        if not self.cards or self._modal_open:
            return None

        viewport = self.scroll_area.viewport()
        x = _clamp01(x_frac) * viewport.width()
        y = _clamp01(y_frac) * viewport.height() + \
            self.scroll_area.verticalScrollBar().value()

        best, best_dist = -1, None
        for i, card in enumerate(self.cards):
            dist = rect_distance(card.geometry(), x, y)
            if best_dist is None or dist < best_dist:
                best, best_dist = i, dist

        card = self.select_index(best)
        # Pointing at a box that is only half on screen should bring it in.
        if card is not None:
            self._keep_visible(card)
        return card

    def _keep_visible(self, card):
        sb = self.scroll_area.verticalScrollBar()
        top, bottom = sb.value(), sb.value() + self.scroll_area.viewport().height()
        if card.y() < top or card.y() + card.height() > bottom:
            self.scroll_area.ensureWidgetVisible(card, 0, GRID_SPACING)

    # ── Scrolling ────────────────────────────────────────────────────────────

    def at_top(self):
        return self.scroll_area.verticalScrollBar().value() <= 0

    def at_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        return sb.value() >= sb.maximum()

    def scroll_by_pixels(self, delta):
        """Same open-palm scroll the notices column uses."""
        if self._modal_open:
            self.modal.scroll_by_pixels(delta)
            return
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.value() + int(delta))
        self._snap_timer.start(SCROLL_SNAP_MS)

    def snap_to_nearest_box(self):
        """Come to rest with a row of boxes aligned to the top of the view."""
        if not self.cards or self._modal_open:
            return
        sb = self.scroll_area.verticalScrollBar()
        current = sb.value()

        target = min((card.y() for card in self.cards),
                     key=lambda y: abs(y - current), default=current)
        target = max(0, min(sb.maximum(), target))
        if target == current:
            return

        anim = QPropertyAnimation(sb, b"value", self)
        anim.setDuration(SCROLL_SNAP_ANIM_MS)
        anim.setStartValue(current)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._scroll_anim = anim

    # ── Modal ────────────────────────────────────────────────────────────────

    @property
    def modal_open(self):
        return self._modal_open

    def activate_selected(self):
        """Tap handler: open the selected story. True if a modal opened."""
        card = self._selected_card()
        if card is None or self._modal_open:
            return False

        self._snap_timer.stop()
        self.modal.set_article(card.article)

        large = card.article.get('largeImageUrl') or card.image_url
        if large:
            cached = self.images.pixmap(large)
            if cached is not None:
                self.modal.set_hero(cached)
            else:
                self.images.request(large)

        # Grow out of the box that was tapped, clipped to this panel.
        origin = QRect(card.mapTo(self, QPoint(0, 0)), card.size())
        self._modal_origin = origin
        self._modal_open = True
        self.modal.open_from(origin, self._modal_geometry())
        return True

    def close_modal(self):
        """True if a modal was open and is now closing."""
        if not self._modal_open:
            return False
        self._modal_open = False
        origin = self._modal_origin or self._modal_geometry()
        self.modal.close_to(origin)
        return True

    def _modal_geometry(self):
        return self.rect().adjusted(
            MODAL_MARGIN, MODAL_MARGIN, -MODAL_MARGIN, -MODAL_MARGIN
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_modal_open', False):
            self.modal.setGeometry(self._modal_geometry())

    # ── Gesture affordance ───────────────────────────────────────────────────

    def set_gesture_active(self, active):
        if active == self._gesture_active:
            return
        self._gesture_active = active
        self.gesture_dot.setVisible(active)
        self._apply_frame_style()

    def reset_gesture_state(self):
        """Back to a resting panel — used when the mirror changes user."""
        self._snap_timer.stop()
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
            self._scroll_anim = None
        self.modal.stop_animations()
        if self._modal_open:
            self._modal_open = False
            self.modal.hide()
        self._modal_origin = None
        self.set_gesture_active(False)
        self.scroll_area.verticalScrollBar().setValue(0)
        self.select_index(0)
