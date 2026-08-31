"""Offline tests for barcode_reader's validation and confirmation logic.

Run from the mirror/ directory:  python -m unittest test_barcode_reader
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from barcode_reader import (
    BarcodeReader,
    CONFIRM_READS,
    normalize_code,
    is_plausible_code,
)


class FakeReader(BarcodeReader):
    """BarcodeReader with the camera decode replaced by a scripted queue."""

    def __init__(self, frames):
        super().__init__()
        self._frames = list(frames)
        self._calls = 0

    @property
    def available(self):
        return True

    def _decode_raw(self, frame):
        if self._calls < len(self._frames):
            codes = self._frames[self._calls]
        else:
            codes = []
        self._calls += 1
        return codes


class TestNormalizeAndValidate(unittest.TestCase):
    def test_normalize_matches_server_rules(self):
        # Scanners append newlines; students type spaces and lowercase.
        self.assertEqual(normalize_code('18234\n'), '18234')
        self.assertEqual(normalize_code(' 18 234 '), '18234')
        self.assertEqual(normalize_code('kh-18234'), 'KH-18234')
        self.assertEqual(normalize_code(None), '')

    def test_plausible_codes(self):
        for code in ('1823', '18234', 'KH-18234', 'ABC123456789'):
            self.assertTrue(is_plausible_code(code), code)

    def test_implausible_codes(self):
        for code in ('', '123', 'A' * 33, '-18234', '18_234', '18234;DROP', 'kh-18234'):
            self.assertFalse(is_plausible_code(code), code)


class TestConfirmation(unittest.TestCase):
    def test_single_read_is_not_enough(self):
        # One frame must never trigger sign-in — motion blur produces wrong digits.
        reader = FakeReader([['18234']])
        self.assertIsNone(reader.detect(object()))

    def test_repeated_read_confirms(self):
        reader = FakeReader([['18234']] * CONFIRM_READS)
        results = [reader.detect(object()) for _ in range(CONFIRM_READS)]
        self.assertEqual(results[-1], '18234')
        self.assertTrue(all(r is None for r in results[:-1]))

    def test_confirmed_code_is_not_reported_twice(self):
        # A card left in view must not re-trigger sign-in every frame.
        reader = FakeReader([['18234']] * (CONFIRM_READS + 5))
        reported = [r for r in (reader.detect(object()) for _ in range(CONFIRM_READS + 5)) if r]
        self.assertEqual(reported, ['18234'])

    def test_two_different_partial_reads_do_not_confirm_each_other(self):
        # Distinct misreads must each need their own confirmations.
        reader = FakeReader([['18234'], ['18235'], ['18236']])
        results = [reader.detect(object()) for _ in range(3)]
        self.assertTrue(all(r is None for r in results), results)

    def test_reset_allows_same_card_again(self):
        reader = FakeReader([['18234']] * (2 * CONFIRM_READS))
        for _ in range(CONFIRM_READS):
            reader.detect(object())
        reader.reset()
        results = [reader.detect(object()) for _ in range(CONFIRM_READS)]
        self.assertEqual(results[-1], '18234')

    def test_implausible_reads_are_dropped_before_confirmation(self):
        reader = FakeReader([['<script>'], ['<script>'], ['12']] * 2)
        results = [reader.detect(object()) for _ in range(6)]
        self.assertTrue(all(r is None for r in results), results)

    def test_no_frame_returns_none(self):
        reader = FakeReader([['18234']] * CONFIRM_READS)
        self.assertIsNone(reader.detect(None))


if __name__ == '__main__':
    unittest.main()
