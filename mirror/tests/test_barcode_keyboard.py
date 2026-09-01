"""Tests for physical barcode scanner / keyboard input, guest transition on unrecognized barcodes,
and enlarged smartmirror.me guest screen typography.

Run from the mirror/ directory:  python -m unittest test_barcode_keyboard
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import requests
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent

class _MockResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = ''

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


app = QApplication.instance() or QApplication([])

import smart_mirror_pro as smp


class TestBarcodeKeyboardInput(unittest.TestCase):
    def setUp(self):
        # Create mirror in test mode
        os.environ['MIRROR_WINDOWED'] = '1'
        os.environ['MIRROR_GESTURES'] = '0'
        self.mirror = smp.SmartMirrorPro()
        self.mirror.poll_timer.stop()
        self.mirror.gesture_timer.stop()
        self.mirror.banner_timer.stop()
        self.mirror.resize(1280, 800)
        self.mirror.show()
        app.processEvents()

    def tearDown(self):
        self.mirror.close()

    def _send_key(self, key, text=""):
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
        self.mirror.keyPressEvent(event)

    def _type_string(self, s, press_enter=True):
        for ch in s:
            self._send_key(Qt.Key.Key_unknown, ch)
        if press_enter:
            self._send_key(Qt.Key.Key_Return, "\r")

    def test_guest_screen_elements_and_typography(self):
        """Verify the enlarged smartmirror.me and Barcode Not Detected elements exist."""
        self.assertTrue(hasattr(self.mirror, 'guest_barcode_status_lbl'))
        self.assertEqual(self.mirror.guest_barcode_status_lbl.text(), "Barcode Not Detected")
        
        # Check domain label font size is enlarged (>= 68px)
        domain_style = self.mirror.guest_domain_lbl.styleSheet()
        self.assertIn("72px", domain_style)
        self.assertEqual(self.mirror.guest_domain_lbl.text(), "smartmirror.me")

        # Check info label font size is enlarged (>= 24px)
        info_style = self.mirror.guest_info_lbl.styleSheet()
        self.assertIn("24px", info_style)

    def test_barcode_buffering_and_backspace(self):
        """Verify typing accumulates in buffer and Backspace deletes characters."""
        self.mirror._barcode_buffer = ""
        self._send_key(Qt.Key.Key_A, "1")
        self._send_key(Qt.Key.Key_B, "8")
        self._send_key(Qt.Key.Key_C, "2")
        self.assertEqual(self.mirror._barcode_buffer, "182")
        
        self._send_key(Qt.Key.Key_Backspace, "")
        self.assertEqual(self.mirror._barcode_buffer, "18")
        
        self._send_key(Qt.Key.Key_Escape, "")
        self.assertEqual(self.mirror._barcode_buffer, "")

    def test_successful_barcode_scan_transitions_to_user(self):
        """Verify scanning a valid student ID logs the user in."""
        user_id = "STU18234"
        widgets = [{"id": "timetable", "type": "timetable"}]
        
        # Trigger verification callback directly
        self.mirror._on_barcode_verified(user_id, widgets, {}, True, "18234")
        
        self.assertEqual(self.mirror.current_user_id, user_id)
        self.assertEqual(self.mirror._last_state, 'user')
        self.assertTrue(self.mirror.face_recognized)

    def _settle(self):
        anims = []
        for extra in (self.mirror._timetable_anim, self.mirror._anim_in, self.mirror._anim_out, self.mirror._demo_anim):
            if extra is not None:
                anims.append(extra)
        for anim in anims:
            anim.setCurrentTime(anim.duration())
        app.processEvents()

    def test_unrecognized_barcode_scan_shows_guest_screen(self):
        """Verify scanning an unlinked/invalid barcode transitions to guest screen."""
        self.mirror._last_state = 'idle'
        
        # Trigger verification failure
        self.mirror._on_barcode_verified(None, [], {}, False, "UNKNOWN999")
        self._settle()
        
        self.assertEqual(self.mirror._last_state, 'guest')
        self.assertEqual(self.mirror.guest_barcode_status_lbl.text(), "Barcode Not Detected")
        self.assertTrue(self.mirror.guest_barcode_status_lbl.isVisible())

    def test_normal_guest_mode_hides_barcode_error(self):
        """Verify normal guest mode (no failed barcode attempt) keeps barcode error hidden."""
        self.mirror._last_state = 'idle'
        self.mirror._trigger_transition('guest', '', {'state': 'guest'})
        self._settle()
        self.assertFalse(self.mirror.guest_barcode_status_lbl.isVisible())

    def test_left_side_dwell_does_not_show_indicator_bar(self):
        """Verify hand dwelling on the left side does not display the indicator bar."""
        self.mirror._last_state = 'user'
        self.mirror._handle_gesture({
            'present': True,
            'region': 'left',
            'hand_x': 0.2,
            'dwell_side': 'left',
            'right_dwell_progress': 0.8
        })
        self.assertTrue(self.mirror.indicator_bar.isHidden())

    def test_right_side_dwell_shows_indicator_bar_and_hint(self):
        """Verify hand dwelling on the right side displays the indicator bar and subtle hint."""
        self.mirror._last_state = 'user'
        self.mirror._timetable_slid_away = False
        self.mirror._update_arrow_indicator()
        self.assertTrue(self.mirror.edge_hint_label.isVisible())
        self.assertIn("King's Week", self.mirror.edge_hint_label.text())

        self.mirror._handle_gesture({
            'present': True,
            'region': 'right',
            'hand_x': 0.85,
            'dwell_side': 'right',
            'right_dwell_progress': 0.5
        })
        self.assertFalse(self.mirror.indicator_bar.isHidden())

    def test_timetable_duration_is_10_seconds(self):
        """Verify timetable display duration is configured to 10 seconds."""
        self.assertEqual(smp.TIMETABLE_DISPLAY_MS, 10_000)

    def test_barcode_success_banner(self):
        """Verify barcode verification sets banner message."""
        self.mirror._on_barcode_verified("STU12345", [], {}, True, "12345")
        self.assertTrue(self.mirror.banner_frame.isVisible())
        self.assertIn("STU12345", self.mirror.banner_label.text())


if __name__ == '__main__':
    unittest.main()
