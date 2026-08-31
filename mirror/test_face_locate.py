"""Offline tests for face_recognize.locate_faces().

No camera and no real face needed: dlib's detector and the Haar cascade are both
stubbed, so what is under test is the fallback ladder and the coordinate
conversion between the two — which is where the bug was.

Run from the mirror/ directory:  python -m unittest test_face_locate
"""

import unittest

import numpy as np

import face_recognize as fr


BLANK = np.zeros((120, 160, 3), dtype=np.uint8)


class _StubCascade:
    """Stand-in for cv2.CascadeClassifier, returning fixed (x, y, w, h) boxes."""

    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = 0

    def detectMultiScale(self, gray, scale, neighbours):
        self.calls += 1
        return self.boxes


class LocateFacesTest(unittest.TestCase):
    def setUp(self):
        self._real_locations = fr.face_recognition.face_locations
        self._real_cascade = fr._fallback_cascade
        self.hog_calls = []

    def tearDown(self):
        fr.face_recognition.face_locations = self._real_locations
        fr._fallback_cascade = self._real_cascade

    def _stub_hog(self, plain=(), upsampled=()):
        def face_locations(rgb, number_of_times_to_upsample=0, **kw):
            self.hog_calls.append(number_of_times_to_upsample)
            return list(upsampled if number_of_times_to_upsample else plain)
        fr.face_recognition.face_locations = face_locations

    def test_hog_is_preferred_when_it_finds_a_face(self):
        # Its boxes frame a face the way the encoder expects, so nothing else
        # should even be attempted.
        self._stub_hog(plain=[(10, 90, 80, 20)])
        fr._fallback_cascade = _StubCascade([(0, 0, 50, 50)])

        locations, detector = fr.locate_faces(BLANK)

        self.assertEqual(detector, 'hog')
        self.assertEqual(locations, [(10, 90, 80, 20)])
        self.assertEqual(self.hog_calls, [0])
        self.assertEqual(fr._fallback_cascade.calls, 0)

    def test_a_small_face_falls_through_to_upsampling(self):
        self._stub_hog(plain=[], upsampled=[(5, 40, 35, 10)])
        fr._fallback_cascade = _StubCascade([(0, 0, 50, 50)])

        locations, detector = fr.locate_faces(BLANK)

        self.assertEqual(detector, 'hog-upsampled')
        self.assertEqual(locations, [(5, 40, 35, 10)])
        self.assertEqual(fr._fallback_cascade.calls, 0)

    def test_haar_rescues_a_pose_dlib_rejects(self):
        # The real fault: a head tilted back with the chin up is invisible to
        # HOG at any scale, while Haar boxes it happily — so recognition used to
        # stop dead on exactly the pose people stand in at a mirror.
        self._stub_hog(plain=[], upsampled=[])
        fr._fallback_cascade = _StubCascade([(290, 96, 116, 116)])

        locations, detector = fr.locate_faces(BLANK)

        self.assertEqual(detector, 'haar')
        # (x=290, y=96, w=116, h=116) → (top, right, bottom, left)
        self.assertEqual(locations, [(96, 406, 212, 290)])

    def test_an_empty_frame_reports_nothing_found(self):
        self._stub_hog(plain=[], upsampled=[])
        fr._fallback_cascade = _StubCascade([])

        self.assertEqual(fr.locate_faces(BLANK), ([], 'none'))

    def test_the_real_cascade_loads_and_runs(self):
        # _fallback_cascade is lazily built, so a broken path would only show up
        # on the first frame that HOG missed — in front of a student.
        self._stub_hog(plain=[], upsampled=[])
        fr._fallback_cascade = None

        locations, detector = fr.locate_faces(BLANK)

        self.assertIsNotNone(fr._fallback_cascade)
        self.assertFalse(fr._fallback_cascade.empty(),
                         'the Haar cascade XML did not load')
        self.assertEqual((locations, detector), ([], 'none'))


if __name__ == '__main__':
    unittest.main()
