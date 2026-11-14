"""Offline tests for the full-screen exam timetable: drawing the PDF, and fetching a newer one.

Run from the mirror/ directory:  python -m unittest tests.test_exam_pdf_viewer
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QMarginsF, QPointF, QRect
from PyQt6.QtGui import QPageSize, QPainter, QPdfWriter
from PyQt6.QtWidgets import QApplication

from widgets import exam_pdf_viewer as epv

app = QApplication.instance() or QApplication([])


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def make_pdf(path, pages=2):
    """A real PDF with `pages` A4 pages, each with a line of text."""
    w = QPdfWriter(path)
    w.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    w.setPageMargins(QMarginsF(10, 10, 10, 10))
    p = QPainter(w)
    for i in range(pages):
        if i:
            w.newPage()
        p.drawText(QPointF(200, 400), f"Exam timetable page {i + 1}")
    p.end()
    with open(path, 'rb') as f:
        return f.read()


class FakeResponse:
    def __init__(self, status=200, content=b''):
        self.status_code, self.content = status, content


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cache = os.path.join(self.dir, 'exam.pdf')
        self.real_get = epv.requests.get
        self.addCleanup(setattr, epv.requests, 'get', self.real_get)

    def viewer(self, api_url=None):
        v = epv.ExamPdfViewer(api_url=api_url, cache_path=self.cache)
        v.resize(1280, 800)
        self.addCleanup(v.deleteLater)
        return v

    def test_without_a_downloaded_pdf_the_bundled_picture_is_shown(self):
        v = self.viewer()
        self.assertFalse(v._page().isNull())
        self.assertEqual(v._page().width(), 1280 - 2 * v.MARGIN)
        self.assertGreater(v.scroll_max(), 0)

    def test_the_downloaded_pdf_is_drawn_page_after_page_as_wide_as_the_screen(self):
        make_pdf(self.cache, pages=2)
        v = self.viewer()
        page = v._page()
        self.assertEqual(page.width(), 1280 - 2 * v.MARGIN)
        one_page = int(page.width() * 297 / 210)
        self.assertGreater(page.height(), 2 * one_page - 5)        # two A4 pages, stacked
        self.assertLess(page.height(), 2 * one_page + v.PAGE_GAP + 5)
        self.assertGreater(v.scroll_max(), one_page)               # all of it can be scrolled to

    def test_a_pdf_with_more_pages_makes_a_longer_scroll(self):
        make_pdf(self.cache, pages=1)
        short = self.viewer().scroll_max()
        make_pdf(self.cache, pages=3)
        self.assertGreater(self.viewer().scroll_max(), short + 1000)

    def test_a_broken_file_falls_back_to_the_picture(self):
        with open(self.cache, 'wb') as f:
            f.write(b'%PDF-1.4 but not really')
        v = self.viewer()
        self.assertFalse(v._page().isNull())
        self.assertGreater(v.scroll_max(), 0)

    def test_a_newer_file_is_drawn_after_it_arrives(self):
        make_pdf(self.cache, pages=1)
        v = self.viewer()
        before = v._page().height()
        time.sleep(0.05)
        make_pdf(self.cache, pages=3)
        os.utime(self.cache, (time.time() + 5, time.time() + 5))
        v._on_refreshed()
        self.assertGreater(v._page().height(), before + 1000)

    # -- leaving: two quick pinches --
    def opened(self):
        v = self.viewer()
        closed = []
        v.closed.connect(lambda: closed.append(1))
        v.open()
        return v, closed

    def test_two_quick_pinches_close_it(self):
        v, closed = self.opened()
        v.handle(None, "tap")
        self.assertTrue(v.isVisible())
        self.assertTrue(v.waiting_for_second_pinch())
        v.handle(None, "tap")
        self.assertFalse(v.isVisible())
        self.assertEqual(closed, [1])

    def test_one_pinch_alone_does_not_close_it_and_the_wait_runs_out(self):
        v, closed = self.opened()
        now = [100.0]
        real = epv.time.monotonic
        epv.time.monotonic = lambda: now[0]
        self.addCleanup(setattr, epv.time, 'monotonic', real)
        v.handle(None, "tap")
        now[0] += v.DOUBLE_PINCH_SEC + 0.1
        self.assertFalse(v.waiting_for_second_pinch())
        v.handle(None, "tap")                          # too late to count as the second: it is a new first
        self.assertTrue(v.isVisible())
        self.assertEqual(closed, [])
        now[0] += 0.4
        v.handle(None, "tap")
        self.assertFalse(v.isVisible())

    def test_a_scroll_between_two_pinches_makes_them_two_separate_pinches(self):
        v, closed = self.opened()
        v.handle(None, "tap")
        v.handle(None, "scroll", 80)
        self.assertFalse(v.waiting_for_second_pinch())
        v.handle(None, "tap")
        self.assertTrue(v.isVisible())
        self.assertEqual(v._scroll, 80)

    def test_opening_it_again_starts_from_no_pinches(self):
        v, closed = self.opened()
        v.handle(None, "tap")
        v.close_viewer()
        v.open()
        self.assertFalse(v.waiting_for_second_pinch())

    def test_there_is_no_close_button_any_more(self):
        self.assertFalse(hasattr(epv.ExamPdfViewer, 'close_rect'))

    def test_the_header_says_how_to_leave_in_white(self):
        v, _ = self.opened()
        v.resize(1280, 800)

        def white_in_right_header():
            img = v.grab().toImage()
            count = 0
            for y in range(0, v.HEADER_H - 40):
                for x in range(640, 1280 - v.MARGIN):
                    c = img.pixelColor(x, y)
                    if c.red() == c.green() == c.blue() == 255:
                        count += 1
            return count

        self.assertGreater(white_in_right_header(), 200)       # the instruction is there, in white
        # and no slate-blue button (the old CLOSE one) is drawn in the header
        img = v.grab().toImage()
        slate = sum(1 for y in range(0, v.HEADER_H - 6) for x in range(640, 1280 - v.MARGIN)
                    if (lambda c: (c.red(), c.green(), c.blue()) == (30, 41, 59))(img.pixelColor(x, y)))
        self.assertEqual(slate, 0)

    def test_a_double_click_closes_it_at_a_desk(self):
        from PyQt6.QtCore import Qt, QPointF, QEvent
        from PyQt6.QtGui import QMouseEvent
        v, closed = self.opened()
        e = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(300, 300), QPointF(300, 300),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        v.mouseDoubleClickEvent(e)
        self.assertFalse(v.isVisible())

    # -- fetching --
    def test_a_newer_pdf_is_saved(self):
        pdf = make_pdf(os.path.join(self.dir, 'src.pdf'))
        seen = {}

        def get(url, headers=None, timeout=None):
            seen.update(url=url, headers=headers or {})
            return FakeResponse(200, pdf)

        epv.requests.get = get
        v = self.viewer(api_url='http://api.test')
        got = []
        v.refreshed.connect(lambda: got.append(1))
        v._download()
        app.processEvents()
        self.assertEqual(seen['url'], 'http://api.test/api/exam-timetable.pdf')
        self.assertEqual(read(self.cache), pdf)
        self.assertEqual(got, [1])

    def test_it_asks_only_for_what_changed_since_its_copy(self):
        make_pdf(self.cache)
        seen = {}

        def get(url, headers=None, timeout=None):
            seen.update(headers or {})
            return FakeResponse(304)

        epv.requests.get = get
        v = self.viewer(api_url='http://api.test')
        before = read(self.cache)
        v._download()
        self.assertIn('If-Modified-Since', seen)
        self.assertEqual(read(self.cache), before)

    def test_something_that_is_not_a_pdf_is_not_kept(self):
        epv.requests.get = lambda *a, **k: FakeResponse(200, b'<html>sign in</html>')
        v = self.viewer(api_url='http://api.test')
        v._download()
        self.assertFalse(os.path.exists(self.cache))

    def test_a_failed_download_keeps_the_copy_and_does_not_crash(self):
        make_pdf(self.cache)
        before = read(self.cache)

        def boom(*a, **k):
            raise OSError('no network')

        epv.requests.get = boom
        v = self.viewer(api_url='http://api.test')
        v._download()
        self.assertEqual(read(self.cache), before)

    def test_without_a_server_address_it_never_fetches(self):
        epv.requests.get = lambda *a, **k: self.fail('fetched')
        v = self.viewer(api_url=None)
        v.refresh()
        v.open()
        v.close_viewer()


if __name__ == '__main__':
    unittest.main()
