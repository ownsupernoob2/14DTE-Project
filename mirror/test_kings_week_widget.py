"""Offline tests for the King's Week grid.

Runs headless (offscreen Qt) with no network: the panel's fetch is stubbed out
and article dictionaries are handed straight to set_articles().

Run from the mirror/ directory:  python -m unittest test_kings_week_widget
"""

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect

from widgets.kings_week_widget import (
    KingsWeekWidget, ArticleCard, GRID_COLUMNS, rect_distance,
)

app = QApplication.instance() or QApplication([])


def article(n, images=True):
    return {
        'id':            f'a{n}',
        'title':         f'Story {n}',
        'summary':       f'Summary for story {n}.',
        'body':          f'Body of story {n}.\n\nSecond paragraph.',
        'author':        'Reporter',
        'date':          '21 Aug 2026',
        'link':          f'https://hail.to/kings-high-school/article/a{n}',
        'imageUrl':      f'https://cdn/500-{n}.jpg' if images else '',
        'largeImageUrl': f'https://cdn/1000-{n}.jpg' if images else '',
        'images':        [],
    }


class StubPanel(KingsWeekWidget):
    """No network — the grid is driven directly by the tests.

    The image store is stubbed as well: the fake cdn URLs on the fixtures would
    otherwise start a download thread per card and sit there failing DNS.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images.request = lambda url: None

    def refresh(self):
        pass


def make_panel(count=7, width=520, height=760):
    panel = StubPanel()
    panel.resize(width, height)
    panel.set_articles([article(i) for i in range(count)])
    panel.show()
    app.processEvents()
    panel.grid_container.layout().activate()
    app.processEvents()
    return panel


def close_panel(panel):
    """Tear a panel down deterministically.

    Nothing may still be animating when the widgets go away, and deleteLater
    only runs on the next pass of the event loop — which would otherwise be
    somewhere in the middle of the next test.
    """
    panel.reset_gesture_state()
    panel.hide()
    panel.deleteLater()
    app.processEvents()


class TestRectDistance(unittest.TestCase):
    def test_inside_is_zero(self):
        r = QRect(10, 10, 100, 50)
        self.assertEqual(rect_distance(r, 50, 30), 0)
        self.assertEqual(rect_distance(r, 10, 10), 0)

    def test_outside_grows_with_distance(self):
        r = QRect(0, 0, 100, 100)
        near = rect_distance(r, 110, 50)
        far = rect_distance(r, 200, 50)
        self.assertGreater(near, 0)
        self.assertGreater(far, near)

    def test_diagonal_uses_both_axes(self):
        r = QRect(0, 0, 10, 10)
        self.assertAlmostEqual(rect_distance(r, 13, 14), 5.0)


class TestGridLayout(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel(7)

    def tearDown(self):
        close_panel(self.panel)

    def test_one_card_per_article(self):
        self.assertEqual(len(self.panel.cards), 7)

    def test_latest_story_is_the_feature(self):
        first, second = self.panel.cards[0], self.panel.cards[1]
        self.assertTrue(first.feature)
        self.assertFalse(second.feature)
        # It has to actually look biggest, not just be flagged as such.
        self.assertGreater(first.height(), second.height())

    def test_feature_spans_the_full_width(self):
        first, second = self.panel.cards[0], self.panel.cards[1]
        self.assertGreater(first.width(), second.width())
        pos = self.panel.grid.getItemPosition(self.panel.grid.indexOf(first))
        self.assertEqual(pos[3], GRID_COLUMNS)   # column span

    def test_remaining_stories_pair_up(self):
        rows = {}
        for card in self.panel.cards[1:]:
            pos = self.panel.grid.getItemPosition(self.panel.grid.indexOf(card))
            rows.setdefault(pos[0], []).append(card)
        for row, cards in rows.items():
            self.assertLessEqual(len(cards), GRID_COLUMNS, f"row {row} overfilled")
        self.assertEqual(sum(len(c) for c in rows.values()), 6)

    def test_rebuilding_replaces_the_grid(self):
        self.panel.set_articles([article(9)])
        self.assertEqual(len(self.panel.cards), 1)
        self.assertEqual(self.panel.selected_index, 0)

    def test_no_articles_shows_a_message(self):
        self.panel.set_articles([])
        self.assertFalse(self.panel.has_content)
        self.assertTrue(self.panel.status_lbl.isVisible())
        self.assertIn('not available', self.panel.status_lbl.text())


class TestApplyData(unittest.TestCase):
    def setUp(self):
        self.panel = StubPanel()
        self.panel.resize(520, 760)

    def tearDown(self):
        close_panel(self.panel)

    def test_reads_the_api_payload(self):
        self.panel.apply_data({
            'title': "King's Week - 21 August 2026",
            'edition': "King's Week #1338",
            'date': 'Friday, 21st August 2026',
            'articles': [article(0), article(1)],
        })
        self.assertEqual(len(self.panel.cards), 2)
        self.assertIn("#1338", self.panel.edition_lbl.text())
        self.assertIn('21st August', self.panel.edition_lbl.text())

    def test_untitled_articles_are_dropped(self):
        self.panel.apply_data({'articles': [article(0), {'id': 'x', 'title': ''}]})
        self.assertEqual(len(self.panel.cards), 1)

    def test_missing_articles_key_is_survivable(self):
        self.panel.apply_data({'title': 'X'})
        self.assertFalse(self.panel.has_content)

    def test_junk_payload_is_ignored(self):
        self.panel.apply_data([])          # not a dict
        self.panel.apply_data('nonsense')
        self.assertFalse(self.panel.has_content)


class TestSelection(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel(7)

    def tearDown(self):
        close_panel(self.panel)

    def test_latest_starts_selected(self):
        self.assertEqual(self.panel.selected_index, 0)
        self.assertTrue(self.panel.cards[0].selected)

    def test_exactly_one_card_is_selected(self):
        self.panel.select_index(3)
        selected = [i for i, c in enumerate(self.panel.cards) if c.selected]
        self.assertEqual(selected, [3])

    def test_select_index_clamps(self):
        self.panel.select_index(999)
        self.assertEqual(self.panel.selected_index, len(self.panel.cards) - 1)
        self.panel.select_index(-5)
        self.assertEqual(self.panel.selected_index, 0)

    def test_focus_locks_onto_the_box_under_the_hand(self):
        target = self.panel.cards[2]
        vp = self.panel.scroll_area.viewport()
        centre = target.geometry().center()
        card = self.panel.focus_at(centre.x() / vp.width(), centre.y() / vp.height())
        self.assertIs(card, target)
        self.assertEqual(self.panel.selected_index, 2)

    def test_a_gap_between_boxes_still_locks_onto_one(self):
        # There is no cursor and no hover, so every point has to resolve to a box.
        a, b = self.panel.cards[1].geometry(), self.panel.cards[2].geometry()
        vp = self.panel.scroll_area.viewport()
        gap_x = (a.right() + b.left()) / 2
        gap_y = a.center().y()
        card = self.panel.focus_at(gap_x / vp.width(), gap_y / vp.height())
        self.assertIn(card, (self.panel.cards[1], self.panel.cards[2]))
        self.assertTrue(card.selected)

    def test_focus_outside_the_panel_is_clamped_not_dropped(self):
        card = self.panel.focus_at(-3.0, -3.0)
        self.assertIs(card, self.panel.cards[0])
        card = self.panel.focus_at(9.0, 9.0)
        self.assertIsNotNone(card)
        self.assertTrue(card.selected)

    def test_focus_with_no_articles_is_harmless(self):
        self.panel.set_articles([])
        self.assertIsNone(self.panel.focus_at(0.5, 0.5))

    def test_focus_is_ignored_while_a_modal_is_open(self):
        # The hand drifting mid-read must not reshuffle the selection behind it.
        self.panel.select_index(2)
        self.panel.activate_selected()
        self.assertIsNone(self.panel.focus_at(0.1, 0.1))
        self.assertEqual(self.panel.selected_index, 2)


class TestScrolling(unittest.TestCase):
    def setUp(self):
        # Enough stories that the scroll range comfortably exceeds the deltas
        # used below — otherwise the scrollbar clamps and the assertions are
        # measuring the clamp rather than the scroll.
        self.panel = make_panel(15)
        self.sb = self.panel.scroll_area.verticalScrollBar()

    def tearDown(self):
        close_panel(self.panel)

    def test_scrollable_content(self):
        self.assertGreater(self.sb.maximum(), 0,
                           "fifteen stories should not fit in one viewport")

    def test_scroll_by_pixels_moves_the_list(self):
        self.assertGreater(self.sb.maximum(), 120, "not enough range to test with")
        self.panel.scroll_by_pixels(120)
        self.assertEqual(self.sb.value(), 120)

    def test_scroll_arms_the_snap(self):
        self.panel.scroll_by_pixels(70)
        self.assertTrue(self.panel._snap_timer.isActive())

    def test_at_top_and_bottom(self):
        self.assertTrue(self.panel.at_top())
        self.sb.setValue(self.sb.maximum())
        self.assertTrue(self.panel.at_bottom())
        self.assertFalse(self.panel.at_top())

    def test_snap_locks_to_a_box_edge(self):
        tops = sorted({card.y() for card in self.panel.cards})
        # Land deliberately between two rows.
        between = (tops[1] + tops[2]) // 2
        self.sb.setValue(min(between, self.sb.maximum()))
        self.panel.snap_to_nearest_box()
        app.processEvents()
        # The animation is asynchronous; the target is what matters here.
        self.assertIn(self.panel._scroll_anim.endValue(), tops)

    def test_snap_does_nothing_when_already_aligned(self):
        self.sb.setValue(self.panel.cards[0].y())
        self.panel._scroll_anim = None
        self.panel.snap_to_nearest_box()
        self.assertIsNone(self.panel._scroll_anim)

    def test_scroll_goes_to_the_article_while_a_modal_is_open(self):
        # A story long enough that the modal has somewhere of its own to scroll.
        long_story = article(0)
        long_story['body'] = '\n\n'.join(
            f'Paragraph {i} of a story that runs well past the modal. ' * 4
            for i in range(40)
        )
        self.panel.set_articles([long_story] + [article(i) for i in range(1, 9)])
        self.panel.activate_selected()
        app.processEvents()

        before = self.sb.value()
        self.panel.scroll_by_pixels(90)
        self.assertEqual(self.sb.value(), before, "the grid must not move behind the modal")

        modal_sb = self.panel.modal.scroll_area.verticalScrollBar()
        self.assertGreater(modal_sb.maximum(), 90, "the test story must overflow the modal")
        self.assertEqual(modal_sb.value(), 90)


class TestModal(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel(7)

    def tearDown(self):
        close_panel(self.panel)

    def test_tap_opens_the_selected_story(self):
        self.panel.select_index(3)
        self.assertTrue(self.panel.activate_selected())
        self.assertTrue(self.panel.modal_open)
        self.assertEqual(self.panel.modal.title_lbl.text(), 'Story 3')
        self.assertIn('Body of story 3', self.panel.modal.text_lbl.text())
        self.assertIn('article/a3', self.panel.modal.link_lbl.text())

    def test_modal_grows_out_of_its_box(self):
        card = self.panel.select_index(2)
        self.panel.activate_selected()
        origin = self.panel._modal_origin
        self.assertEqual(origin.size(), card.size())
        # It has to end up bigger than the box it came from.
        end = self.panel._modal_geometry()
        self.assertGreater(end.height(), origin.height())

    def test_second_tap_does_not_reopen(self):
        self.panel.activate_selected()
        self.assertFalse(self.panel.activate_selected())

    def test_close_modal(self):
        self.panel.activate_selected()
        self.assertTrue(self.panel.close_modal())
        self.assertFalse(self.panel.modal_open)
        self.assertFalse(self.panel.close_modal())

    def test_nothing_to_open_without_articles(self):
        self.panel.set_articles([])
        self.assertFalse(self.panel.activate_selected())

    def test_author_and_date_are_shown(self):
        self.panel.activate_selected()
        self.assertIn('Reporter', self.panel.modal.meta_lbl.text())
        self.assertIn('21 Aug 2026', self.panel.modal.meta_lbl.text())

    def test_body_falls_back_to_the_summary(self):
        thin = article(1)
        thin['body'] = ''
        self.panel.set_articles([thin])
        self.panel.activate_selected()
        self.assertEqual(self.panel.modal.text_lbl.text(), 'Summary for story 1.')


class TestGestureState(unittest.TestCase):
    def setUp(self):
        self.panel = make_panel(7)

    def tearDown(self):
        close_panel(self.panel)

    def test_affordance_dot(self):
        self.panel.set_gesture_active(True)
        self.assertTrue(self.panel.gesture_dot.isVisible())
        self.panel.set_gesture_active(False)
        self.assertFalse(self.panel.gesture_dot.isVisible())

    def test_reset_returns_to_a_resting_panel(self):
        self.panel.set_gesture_active(True)
        self.panel.select_index(4)
        self.panel.scroll_by_pixels(200)
        self.panel.activate_selected()

        self.panel.reset_gesture_state()

        self.assertFalse(self.panel.modal_open)
        self.assertFalse(self.panel.modal.isVisible())
        self.assertFalse(self.panel.gesture_dot.isVisible())
        self.assertEqual(self.panel.scroll_area.verticalScrollBar().value(), 0)
        self.assertEqual(self.panel.selected_index, 0)
        self.assertFalse(self.panel._snap_timer.isActive())


class TestCards(unittest.TestCase):
    def test_card_without_art_still_builds(self):
        card = ArticleCard(article(1, images=False))
        self.assertEqual(card.image_url, '')
        self.assertEqual(card.title_lbl.text(), 'Story 1')

    def test_only_the_feature_carries_a_summary(self):
        feature = ArticleCard(article(0), feature=True)
        small = ArticleCard(article(1), feature=False)
        self.assertTrue(hasattr(feature, 'summary_lbl'))
        self.assertFalse(hasattr(small, 'summary_lbl'))

    def test_selection_is_idempotent(self):
        card = ArticleCard(article(0))
        card.set_selected(True)
        card.set_selected(True)
        self.assertTrue(card.selected)
        card.set_selected(False)
        self.assertFalse(card.selected)


if __name__ == '__main__':
    unittest.main()
