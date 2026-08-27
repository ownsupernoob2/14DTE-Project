"""
barcode_reader.py — decode student ID barcodes from camera frames.

Wraps whichever decoder the host actually has. OpenCV's contrib build ships
cv2.barcode (EAN/UPC/Code128) and cv2.QRCodeDetector; pyzbar is used when
present because it handles Code39, which some school ID cards use.

A single frame decode is noisy — motion blur and partial occlusion produce
plausible-looking wrong digits — so detect() only reports a code once it has
seen the same value on CONFIRM_READS separate frames, and then suppresses
repeats for REPEAT_COOLDOWN_SEC so one card held up does not re-trigger
sign-in over and over.
"""

import re
import time

import cv2

try:
    from pyzbar import pyzbar
except Exception:
    pyzbar = None


# Must agree with validateBarcode in server/handlers_barcode.go — rejecting
# malformed reads here saves a pointless round trip.
_CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9-]*$')
_MIN_LEN = 4
_MAX_LEN = 32

CONFIRM_READS = 2
REPEAT_COOLDOWN_SEC = 20.0
# A partial read of the same card can arrive several frames later; anything
# older than this is treated as an unrelated sighting.
CONFIRM_WINDOW_SEC = 2.0


def normalize_code(raw):
    """Match normalizeBarcode in the Go server: strip whitespace, uppercase."""
    if not raw:
        return ''
    return ''.join(raw.split()).upper()


def is_plausible_code(code):
    return _MIN_LEN <= len(code) <= _MAX_LEN and bool(_CODE_RE.match(code))


class BarcodeReader:
    def __init__(self):
        self._detector = None
        self._qr = None
        self.backend = 'none'

        # cv2.barcode lives in opencv-contrib; plain opencv-python lacks it.
        try:
            self._detector = cv2.barcode.BarcodeDetector()
            self.backend = 'cv2.barcode'
        except Exception:
            self._detector = None

        try:
            self._qr = cv2.QRCodeDetector()
        except Exception:
            self._qr = None

        if pyzbar is not None:
            self.backend = 'pyzbar' if self._detector is None else 'pyzbar+cv2.barcode'

        if self._detector is None and self._qr is None and pyzbar is None:
            print('[BARCODE] No decoder available — barcode sign-in disabled. '
                  'Install opencv-contrib-python or pyzbar to enable it.')

        # code -> (first_seen, count); plus the last code we actually reported
        self._pending = {}
        self._last_reported = None
        self._last_reported_at = 0.0

    @property
    def available(self):
        return self._detector is not None or self._qr is not None or pyzbar is not None

    # ── Raw decoding ──────────────────────────────────────────────────────

    def _decode_raw(self, frame):
        """Return every plausible code found in the frame."""
        found = []

        if pyzbar is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                for sym in pyzbar.decode(gray):
                    found.append(sym.data.decode('utf-8', errors='ignore'))
            except Exception:
                pass

        if self._detector is not None:
            try:
                ok, decoded, _types, _points = self._detector.detectAndDecodeWithType(frame)
                if ok and decoded:
                    found.extend(decoded)
            except Exception:
                # Older bindings return 3 values instead of 4.
                try:
                    ok, decoded, _points = self._detector.detectAndDecode(frame)
                    if ok and decoded:
                        found.extend(decoded if isinstance(decoded, (list, tuple)) else [decoded])
                except Exception:
                    pass

        if self._qr is not None:
            try:
                data, _points, _straight = self._qr.detectAndDecode(frame)
                if data:
                    found.append(data)
            except Exception:
                pass

        codes = []
        for raw in found:
            code = normalize_code(raw)
            if is_plausible_code(code) and code not in codes:
                codes.append(code)
        return codes

    # ── Public API ────────────────────────────────────────────────────────

    def detect(self, frame):
        """Return a confirmed, non-repeated code, or None.

        Safe to call on every frame; it is cheap when nothing is in view.
        """
        if not self.available or frame is None:
            return None

        now = time.time()

        # Expire stale partial sightings so unrelated reads never accumulate
        # into a false confirmation.
        self._pending = {
            code: seen for code, seen in self._pending.items()
            if now - seen[0] < CONFIRM_WINDOW_SEC
        }

        for code in self._decode_raw(frame):
            # _decode_raw already filters, but re-check here so the invariant
            # holds for any decoder backend added later.
            if not is_plausible_code(code):
                continue

            if code == self._last_reported and now - self._last_reported_at < REPEAT_COOLDOWN_SEC:
                continue

            first_seen, count = self._pending.get(code, (now, 0))
            count += 1
            self._pending[code] = (first_seen, count)

            if count >= CONFIRM_READS:
                self._pending.pop(code, None)
                self._last_reported = code
                self._last_reported_at = now
                return code

        return None

    def reset(self):
        """Forget the cooldown so the same card can sign in again immediately."""
        self._pending.clear()
        self._last_reported = None
        self._last_reported_at = 0.0
