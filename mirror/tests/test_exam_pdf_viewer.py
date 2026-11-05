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
