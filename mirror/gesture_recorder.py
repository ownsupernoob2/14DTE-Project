#!/usr/bin/env python3
"""mirror/gesture_recorder.py — Gesture Recorder & Statistical Calibration Tool.

Overhaul tool for building instinct-based, natural gestures:
1. Live Camera Feed with MediaPipe hand skeleton landmarks, palm crosshair, and pinch gauge.
2. 3 Dedicated Recording Modes:
   - [1] Click / Interact (Pinch & Tap gap ratios, hold durations, drift)
   - [2] Scroll / Wave (Open-palm vertical swipes, stroke velocities, return strokes)
   - [3] Resting / Dwell (Hand tremor noise floor, stillness, corner dwell progress)
3. Statistical Analysis Engine (--analyze or 'A' key):
   - Computes empirical distributions across recordings.
   - Recommends calibrated constants for gesture_engine.py.
   - Outputs analysis_report.md and analysis_report.json.
"""

import argparse
import datetime
import json
import math
import os
import sys
import time

import cv2

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
except ImportError:
    mp = None

# Model path matches gesture_engine.py
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gesture_recognizer.task")
RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gesture_recordings")

# Modes
MODE_CLICK = "click_interact"
MODE_SCROLL = "scroll_pinch_drag"
MODE_DWELL = "resting_dwell"

MODE_INFO = {
    MODE_CLICK: {
        "title": "MODE 1: CLICK / PINCH INTERACT",
        "desc": "Pinch thumb and index together to click or tap. Record pinch & release.",
        "color": (255, 191, 0),    # Cyan/Amber
    },
    MODE_SCROLL: {
        "title": "MODE 2: PINCH & DRAG SCROLL",
        "desc": "Pinch thumb and index together and drag vertically up/down to scroll.",
        "color": (0, 255, 128),    # Emerald
    },
    MODE_DWELL: {
        "title": "MODE 3: RESTING / DWELL",
        "desc": "Hold hand resting or steady in top-right corner to test dwell & jitter.",
        "color": (255, 105, 180),  # Magenta/Pink
    },
}

HAND_CONNECTIONS = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle
    (0, 9), (9, 10), (10, 11), (11, 12),
    # Ring
    (0, 13), (13, 14), (14, 15), (15, 16),
    # Pinky
    (0, 17), (17, 18), (18, 19), (19, 20),
    # Palm knuckles
    (5, 9), (9, 13), (13, 17),
]


class GestureRecorderApp:
    def __init__(self, camera_id=0, flip=False):
        self.camera_id = camera_id
        self.flip = flip
        self.current_mode = MODE_CLICK
        self.modes = [MODE_CLICK, MODE_SCROLL, MODE_DWELL]
        self.mode_index = 0

        self.recording = False
        self.record_frames = []
        self.record_start_time = 0.0

        self.last_toast_msg = ""
        self.last_toast_time = 0.0

        # Motion tracking
        self.last_palm_x = None
        self.last_palm_y = None
        self.last_palm_t = 0.0
        self.cur_vel_x = 0.0
        self.cur_vel_y = 0.0

        # Dwell tracking
        self.dwell_start_t = None
        self.dwell_progress = 0.0

        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        self.tracker = self._init_tracker()

    def _init_tracker(self):
        if mp is None:
            print("[RECORDER] mediapipe not installed.")
            return None
        if not os.path.exists(MODEL_PATH):
            print(f"[RECORDER] Missing {MODEL_PATH}.")
            return None
        try:
            options = mp_vision.GestureRecognizerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            return mp_vision.GestureRecognizer.create_from_options(options)
        except Exception as e:
            print(f"[RECORDER] Tracker init failed: {e}")
            return None

    def set_toast(self, msg):
        self.last_toast_msg = msg
        self.last_toast_time = time.time()

    def set_mode(self, mode):
        if self.recording:
            self.stop_recording(save=True)
        self.current_mode = mode
        self.mode_index = self.modes.index(mode)
        self.set_toast(f"Switched to {MODE_INFO[mode]['title']}")

    def toggle_recording(self):
        if self.recording:
            self.stop_recording(save=True)
        else:
            self.start_recording()

    def start_recording(self):
        self.recording = True
        self.record_frames = []
        self.record_start_time = time.time()
        self.set_toast(f"Started recording: {self.current_mode}")

    def stop_recording(self, save=True):
        if not self.recording:
            return
        self.recording = False
        duration = time.time() - self.record_start_time

        if save and len(self.record_frames) > 5:
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.current_mode}_{timestamp_str}.json"
            filepath = os.path.join(RECORDINGS_DIR, filename)

            payload = {
                "mode": self.current_mode,
                "recorded_at": datetime.datetime.now().isoformat(),
                "duration_seconds": round(duration, 3),
                "frame_count": len(self.record_frames),
                "approx_fps": round(len(self.record_frames) / max(0.001, duration), 1),
                "frames": self.record_frames,
            }
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                self.set_toast(f"Saved {len(self.record_frames)} frames -> {filename}")
                print(f"[RECORDER] Saved: {filepath} ({len(self.record_frames)} frames, {duration:.1f}s)")
            except Exception as e:
                self.set_toast(f"Save error: {e}")
        elif save:
            self.set_toast("Discarded (too short)")
        else:
            self.set_toast("Recording cancelled")
        self.record_frames = []

    def run(self):
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print(f"[RECORDER] Cannot open camera {self.camera_id}")
            return

        window_name = "Smart Mirror - Gesture Calibration & Recorder"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

        start_time = time.time()
        last_stamp_ms = -1
        frame_idx = 0

        print("\n" + "=" * 65)
        print(" GESTURE RECORDER & OVERHAUL CALIBRATION TOOL")
        print("=" * 65)
        print(" [1] Click / Interact mode")
        print(" [2] Pinch & Drag Scroll mode")
        print(" [3] Resting / Dwell mode")
        print(" [SPACE] Start / Stop Recording")
        print(" [A] Run Statistical Analysis & Calibration")
        print(" [F] Toggle Camera Mirroring (Flip)")
        print(" [C] Cancel active recording")
        print(" [Q] / [ESC] Quit")
        print("=" * 65 + "\n")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                if self.flip:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                now = time.time()
                frame_idx += 1

                # MediaPipe hand tracking
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                stamp_ms = max(int((now - start_time) * 1000), last_stamp_ms + 1)
                last_stamp_ms = stamp_ms

                hand_detected = False
                landmarks_dict = None
                pinch_ratio = 1.0
                palm_x, palm_y = 0.5, 0.5
                palm_size = 0.1
                in_top_right = False
                handedness_str = "Right"
                hand_score = 0.0

                if self.tracker is not None:
                    results = self.tracker.recognize_for_video(mp_img, stamp_ms)
                    if results.hand_landmarks and len(results.hand_landmarks) > 0:
                        lm = results.hand_landmarks[0]
                        hand_detected = True

                        if getattr(results, "handedness", None) and len(results.handedness) > 0:
                            cat = results.handedness[0][0]
                            handedness_str = getattr(cat, "category_name", "Right")
                            hand_score = getattr(cat, "score", 1.0)

                        # Palm centre: avg of wrist and knuckles 5, 9, 13, 17
                        pts = [lm[0], lm[5], lm[9], lm[13], lm[17]]
                        palm_x = sum(p.x for p in pts) / len(pts)
                        palm_y = sum(p.y for p in pts) / len(pts)

                        # Palm size: wrist (0) to middle knuckle (9)
                        aspect = (w / h) if h else 1.0
                        dx = (lm[0].x - lm[9].x) * aspect
                        dy = lm[0].y - lm[9].y
                        palm_size = math.sqrt(dx * dx + dy * dy)

                        # Pinch gap: thumb tip (4) to index tip (8)
                        gap_dx = (lm[4].x - lm[8].x) * aspect
                        gap_dy = lm[4].y - lm[8].y
                        pinch_dist = math.sqrt(gap_dx * gap_dx + gap_dy * gap_dy)
                        pinch_ratio = pinch_dist / max(0.01, palm_size)

                        # Velocity tracking
                        if self.last_palm_t > 0:
                            dt = max(0.001, now - self.last_palm_t)
                            if dt < 0.3:
                                inst_vx = (palm_x - self.last_palm_x) / dt
                                inst_vy = (palm_y - self.last_palm_y) / dt
                                self.cur_vel_x = 0.7 * self.cur_vel_x + 0.3 * inst_vx
                                self.cur_vel_y = 0.7 * self.cur_vel_y + 0.3 * inst_vy
                        self.last_palm_x = palm_x
                        self.last_palm_y = palm_y
                        self.last_palm_t = now

                        # Top-right dwell region
                        in_top_right = (palm_x >= 0.62 and palm_y <= 0.18)
                        if in_top_right:
                            if self.dwell_start_t is None:
                                self.dwell_start_t = now
                            elapsed = now - self.dwell_start_t
                            self.dwell_progress = min(1.0, elapsed / 1.6)
                        else:
                            self.dwell_start_t = None
                            self.dwell_progress = 0.0

                        # Save landmark coordinates
                        landmarks_dict = [
                            {"x": round(p.x, 4), "y": round(p.y, 4), "z": round(getattr(p, "z", 0.0), 4)}
                            for p in lm
                        ]

                        # Draw skeleton
                        self._draw_hand_skeleton(frame, lm, w, h, pinch_ratio)

                if not hand_detected:
                    self.last_palm_t = 0.0
                    self.cur_vel_x = 0.0
                    self.cur_vel_y = 0.0
                    self.dwell_start_t = None
                    self.dwell_progress = 0.0

                # Record frame if active
                if self.recording:
                    frame_record = {
                        "frame_idx": frame_idx,
                        "rel_time": round(now - self.record_start_time, 4),
                        "wall_time": now,
                        "hand_detected": hand_detected,
                        "handedness": handedness_str if hand_detected else None,
                        "score": round(hand_score, 3) if hand_detected else 0.0,
                        "palm_x": round(palm_x, 4) if hand_detected else None,
                        "palm_y": round(palm_y, 4) if hand_detected else None,
                        "palm_size": round(palm_size, 4) if hand_detected else None,
                        "pinch_ratio": round(pinch_ratio, 4) if hand_detected else None,
                        "vel_x": round(self.cur_vel_x, 3) if hand_detected else 0.0,
                        "vel_y": round(self.cur_vel_y, 3) if hand_detected else 0.0,
                        "in_top_right": in_top_right,
                        "dwell_progress": round(self.dwell_progress, 3),
                        "landmarks": landmarks_dict,
                    }
                    self.record_frames.append(frame_record)

                # Render HUD overlays
                self._draw_hud(frame, w, h, hand_detected, pinch_ratio, palm_x, palm_y, handedness_str)

                cv2.imshow(window_name, frame)
                key = cv2.waitKey(1) & 0xFF

                if key in (ord('q'), ord('Q'), 27):  # Q or ESC
                    if self.recording:
                        self.stop_recording(save=True)
                    break
                elif key == ord('1'):
                    self.set_mode(MODE_CLICK)
                elif key == ord('2'):
                    self.set_mode(MODE_SCROLL)
                elif key == ord('3'):
                    self.set_mode(MODE_DWELL)
                elif key == 32:  # SPACE
                    self.toggle_recording()
                elif key in (ord('c'), ord('C')):
                    self.stop_recording(save=False)
                elif key in (ord('f'), ord('F')):
                    self.flip = not self.flip
                    self.set_toast(f"Mirroring (Flip): {'ON' if self.flip else 'OFF'}")
                elif key in (ord('a'), ord('A')):
                    report = analyze_recordings()
                    self.set_toast("Analysis complete! See console & report")
        finally:
            cap.release()
            cv2.destroyAllWindows()
            if self.tracker and hasattr(self.tracker, 'close'):
                self.tracker.close()

    def _draw_hand_skeleton(self, frame, lm, w, h, pinch_ratio):
        # Draw connections
        for p1_idx, p2_idx in HAND_CONNECTIONS:
            pt1 = (int(lm[p1_idx].x * w), int(lm[p1_idx].y * h))
            pt2 = (int(lm[p2_idx].x * w), int(lm[p2_idx].y * h))
            cv2.line(frame, pt1, pt2, (180, 180, 180), 2, cv2.LINE_AA)

        # Draw joints
        for idx, p in enumerate(lm):
            px, py = int(p.x * w), int(p.y * h)
            # Fingertips highlighted
            if idx in (4, 8, 12, 16, 20):
                cv2.circle(frame, (px, py), 7, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, (px, py), 9, (0, 0, 0), 2, cv2.LINE_AA)
            else:
                cv2.circle(frame, (px, py), 4, (100, 255, 255), -1, cv2.LINE_AA)

        # Draw pinch line between thumb tip (4) and index tip (8)
        t_pt = (int(lm[4].x * w), int(lm[4].y * h))
        i_pt = (int(lm[8].x * w), int(lm[8].y * h))
        is_pinched = (pinch_ratio < 0.55)
        pinch_color = (34, 197, 94) if is_pinched else (56, 189, 248)  # Green or Cyan
        cv2.line(frame, t_pt, i_pt, pinch_color, 4 if is_pinched else 2, cv2.LINE_AA)

        # Draw palm center
        pts = [lm[0], lm[5], lm[9], lm[13], lm[17]]
        cx = int(sum(p.x for p in pts) / len(pts) * w)
        cy = int(sum(p.y for p in pts) / len(pts) * h)
        cv2.circle(frame, (cx, cy), 12, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1, cv2.LINE_AA)

    def _draw_hud(self, frame, w, h, hand_detected, pinch_ratio, palm_x, palm_y, handedness):
        mode_data = MODE_INFO[self.current_mode]

        # Top banner panel (Dark Brutalist)
        cv2.rectangle(frame, (16, 16), (w - 16, 86), (10, 10, 10), -1)
        cv2.rectangle(frame, (16, 16), (w - 16, 86), (255, 255, 255), 2)

        # Mode title
        cv2.putText(frame, mode_data["title"], (32, 48),
                    cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, mode_data["desc"], (32, 74),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

        # Recording Status Badge
        if self.recording:
            rec_elapsed = time.time() - self.record_start_time
            rec_text = f"REC [{rec_elapsed:04.1f}s | {len(self.record_frames)} frames]"
            cv2.rectangle(frame, (w - 320, 26), (w - 32, 76), (0, 0, 180), -1)
            cv2.rectangle(frame, (w - 320, 26), (w - 32, 76), (255, 255, 255), 2)
            cv2.circle(frame, (w - 296, 51), 8, (255, 255, 255), -1)
            cv2.putText(frame, rec_text, (w - 276, 57),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.rectangle(frame, (w - 300, 26), (w - 32, 76), (30, 30, 30), -1)
            cv2.rectangle(frame, (w - 300, 26), (w - 32, 76), (140, 140, 140), 2)
            cv2.putText(frame, "IDLE (SPACE to Rec)", (w - 275, 57),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (220, 220, 220), 1, cv2.LINE_AA)

        # Left metrics telemetry card
        card_w, card_h = 320, 240
        card_x, card_y = 16, 102
        cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h), (12, 12, 12), -1)
        cv2.rectangle(frame, (card_x, card_y), (card_x + card_w, card_y + card_h), (255, 255, 255), 2)

        cv2.putText(frame, "LIVE TELEMETRY", (card_x + 16, card_y + 26),
                    cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        if hand_detected:
            h_stat = f"Hand: {handedness} (Active)"
            cv2.putText(frame, h_stat, (card_x + 16, card_y + 56),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 128), 1, cv2.LINE_AA)

            pos_str = f"Palm: X={palm_x:.3f}  Y={palm_y:.3f}"
            cv2.putText(frame, pos_str, (card_x + 16, card_y + 84),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            # Pinch ratio bar
            pr_label = f"Pinch Ratio: {pinch_ratio:.2f}"
            cv2.putText(frame, pr_label, (card_x + 16, card_y + 114),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
            bar_w = 180
            fill = int(min(1.0, max(0.0, pinch_ratio / 1.0)) * bar_w)
            cv2.rectangle(frame, (card_x + 16, card_y + 122), (card_x + 16 + bar_w, card_y + 132), (50, 50, 50), -1)
            cv2.rectangle(frame, (card_x + 16, card_y + 122), (card_x + 16 + fill, card_y + 132),
                          (34, 197, 94) if pinch_ratio < 0.55 else (56, 189, 248), -1)
            cv2.line(frame, (card_x + 16 + int(0.55 * bar_w), card_y + 118),
                     (card_x + 16 + int(0.55 * bar_w), card_y + 136), (0, 0, 255), 2)

            # Velocity metrics
            vel_str = f"Vy: {self.cur_vel_y:+.2f}/s   Vx: {self.cur_vel_x:+.2f}/s"
            cv2.putText(frame, vel_str, (card_x + 16, card_y + 160),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

            # Dwell status
            dwell_pct = int(self.dwell_progress * 100)
            dwell_str = f"Top-Right Dwell: {dwell_pct}%"
            cv2.putText(frame, dwell_str, (card_x + 16, card_y + 190),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
            d_fill = int(self.dwell_progress * bar_w)
            cv2.rectangle(frame, (card_x + 16, card_y + 198), (card_x + 16 + bar_w, card_y + 208), (50, 50, 50), -1)
            cv2.rectangle(frame, (card_x + 16, card_y + 198), (card_x + 16 + d_fill, card_y + 208), (255, 215, 0), -1)
        else:
            cv2.putText(frame, "NO HAND DETECTED", (card_x + 16, card_y + 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (100, 100, 255), 1, cv2.LINE_AA)
            cv2.putText(frame, "Hold hand up to camera", (card_x + 16, card_y + 88),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)

        # Top-Right Dwell Target Box Outline
        tr_x1, tr_y1 = int(0.62 * w), int(0.02 * h)
        tr_x2, tr_y2 = int(0.98 * w), int(0.18 * h)
        cv2.rectangle(frame, (tr_x1, tr_y1), (tr_x2, tr_y2), (255, 215, 0), 2)
        cv2.putText(frame, "TOP-RIGHT DWELL ZONE", (tr_x1 + 10, tr_y1 + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 215, 0), 1, cv2.LINE_AA)

        # Bottom Controls Instruction Strip
        strip_y = h - 44
        cv2.rectangle(frame, (16, strip_y), (w - 16, h - 16), (15, 15, 15), -1)
        cv2.rectangle(frame, (16, strip_y), (w - 16, h - 16), (255, 255, 255), 2)
        hints = "[1] Click Mode   [2] Pinch Scroll   [3] Dwell Mode   [SPACE] Record   [A] Analyze   [F] Flip   [Q] Quit"
        cv2.putText(frame, hints, (32, strip_y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (240, 240, 240), 1, cv2.LINE_AA)

        # Toast Notification Overlay
        if self.last_toast_msg and (time.time() - self.last_toast_time < 3.0):
            t_w = len(self.last_toast_msg) * 11 + 40
            t_x = (w - t_w) // 2
            t_y = h - 90
            cv2.rectangle(frame, (t_x, t_y), (t_x + t_w, t_y + 36), (0, 0, 0), -1)
            cv2.rectangle(frame, (t_x, t_y), (t_x + t_w, t_y + 36), (0, 255, 128), 2)
            cv2.putText(frame, self.last_toast_msg, (t_x + 20, t_y + 24),
                        cv2.FONT_HERSHEY_DUPLEX, 0.50, (255, 255, 255), 1, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
# Statistical Analysis & Calibration Engine
# ─────────────────────────────────────────────────────────────────────────────

def analyze_recordings():
    """Aggregates all recordings and computes statistical calibrations."""
    print("\n" + "=" * 65)
    print(" RUNNING GESTURE STATISTICAL ANALYSIS & CALIBRATION")
    print("=" * 65)

    if not os.path.exists(RECORDINGS_DIR):
        print(f"[ANALYSIS] No recordings directory found at {RECORDINGS_DIR}")
        return None

    files = [f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".json") and f != "analysis_report.json"]
    if not files:
        print("[ANALYSIS] No recording JSON files found in gesture_recordings/.")
        print("Record at least one session for Click, Scroll, and Dwell first.")
        return None

    by_mode = {MODE_CLICK: [], MODE_SCROLL: [], MODE_DWELL: []}

    for fname in files:
        fpath = os.path.join(RECORDINGS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            mode = data.get("mode")
            if mode in ("scroll_wave", "scroll_pinch_drag"):
                mode = MODE_SCROLL
            if mode in by_mode:
                by_mode[mode].append((fname, data))
        except Exception as e:
            print(f"[ANALYSIS] Failed reading {fname}: {e}")

    report = {
        "generated_at": datetime.datetime.now().isoformat(),
        "total_sessions": len(files),
        "results": {},
        "recommended_constants": {},
    }

    # 1. Click / Pinch Analysis
    click_sessions = by_mode[MODE_CLICK]
    all_pinch_ratios = []
    min_pinches_per_session = []

    for _, sess in click_sessions:
        ratios = [f["pinch_ratio"] for f in sess.get("frames", []) if f.get("pinch_ratio") is not None]
        if ratios:
            all_pinch_ratios.extend(ratios)
            min_pinches_per_session.append(min(ratios))

    click_stats = {}
    if all_pinch_ratios:
        all_pinch_ratios.sort()
        n = len(all_pinch_ratios)
        click_stats["total_samples"] = n
        click_stats["sessions_count"] = len(click_sessions)
        click_stats["min_pinch_recorded"] = round(all_pinch_ratios[0], 3)
        click_stats["p10_pinch"] = round(all_pinch_ratios[int(0.10 * n)], 3)
        click_stats["median_pinch"] = round(all_pinch_ratios[int(0.50 * n)], 3)
        click_stats["p90_pinch"] = round(all_pinch_ratios[int(0.90 * n)], 3)
        click_stats["max_pinch"] = round(all_pinch_ratios[-1], 3)

        # Recommended thresholds:
        # PINCH_ENTER_RATIO: Set above the min pinches to capture deliberate clicks reliably
        if min_pinches_per_session:
            avg_min_pinch = sum(min_pinches_per_session) / len(min_pinches_per_session)
            recommended_enter = round(min(0.60, max(0.48, avg_min_pinch + 0.12)), 2)
            recommended_exit = round(recommended_enter + 0.20, 2)
        else:
            recommended_enter = 0.55
            recommended_exit = 0.75

        click_stats["recommended_PINCH_ENTER_RATIO"] = recommended_enter
        click_stats["recommended_PINCH_EXIT_RATIO"] = recommended_exit
        report["recommended_constants"]["PINCH_ENTER_RATIO"] = recommended_enter
        report["recommended_constants"]["PINCH_EXIT_RATIO"] = recommended_exit
    report["results"]["click_interact"] = click_stats

    # 2. Scroll / Wave Analysis
    scroll_sessions = by_mode[MODE_SCROLL]
    all_vy = []
    peak_vy_per_session = []

    for _, sess in scroll_sessions:
        vys = [f["vel_y"] for f in sess.get("frames", []) if f.get("vel_y") is not None]
        if vys:
            all_vy.extend(vys)
            abs_vys = [abs(v) for v in vys]
            peak_vy_per_session.append(max(abs_vys))

    scroll_stats = {}
    if all_vy:
        abs_all = [abs(v) for v in all_vy]
        abs_all.sort()
        n = len(abs_all)
        scroll_stats["total_samples"] = n
        scroll_stats["sessions_count"] = len(scroll_sessions)
        scroll_stats["median_abs_velocity"] = round(abs_all[int(0.50 * n)], 3)
        scroll_stats["p75_abs_velocity"] = round(abs_all[int(0.75 * n)], 3)
        scroll_stats["p95_abs_velocity"] = round(abs_all[int(0.95 * n)], 3)

        # Recommended wave velocity threshold: 60th percentile of deliberate wave sessions
        recommended_wave_vel = round(max(0.18, min(0.35, abs_all[int(0.60 * n)])), 2)
        scroll_stats["recommended_WAVE_VELOCITY_THRESHOLD"] = recommended_wave_vel
        report["recommended_constants"]["WAVE_VELOCITY_THRESHOLD"] = recommended_wave_vel
    report["results"]["scroll_wave"] = scroll_stats

    # 3. Resting / Dwell Jitter Analysis
    dwell_sessions = by_mode[MODE_DWELL]
    dxs, dys = [], []
    dwell_times = []

    for _, sess in dwell_sessions:
        frames = [f for f in sess.get("frames", []) if f.get("palm_x") is not None]
        for i in range(1, len(frames)):
            dxs.append(abs(frames[i]["palm_x"] - frames[i - 1]["palm_x"]))
            dys.append(abs(frames[i]["palm_y"] - frames[i - 1]["palm_y"]))
        max_dwell = max([f.get("dwell_progress", 0.0) for f in frames], default=0.0)
        dwell_times.append(max_dwell)

    dwell_stats = {}
    if dxs and dys:
        dxs.sort()
        dys.sort()
        n = len(dxs)
        jitter_p95_x = dxs[int(0.95 * n)]
        jitter_p95_y = dys[int(0.95 * n)]
        dwell_stats["total_transitions"] = n
        dwell_stats["sessions_count"] = len(dwell_sessions)
        dwell_stats["jitter_p95_x"] = round(jitter_p95_x, 4)
        dwell_stats["jitter_p95_y"] = round(jitter_p95_y, 4)

        # Recommended quantum should be strictly larger than p95 jitter to suppress idle jitter
        rec_quantum_size = max(0.008, jitter_p95_x * 1.5, jitter_p95_y * 1.5)
        rec_quantum_denominator = int(1.0 / rec_quantum_size)
        # Snap to nearest sensible fraction
        rec_quantum_denominator = max(48, min(120, rec_quantum_denominator))
        dwell_stats["recommended_POSITION_QUANTUM"] = f"1.0 / {rec_quantum_denominator}"
        report["recommended_constants"]["POSITION_QUANTUM"] = f"1.0 / {rec_quantum_denominator}"
    report["results"]["resting_dwell"] = dwell_stats

    # Print summary
    print(f"\n[ANALYSIS] Analyzed {len(files)} recording sessions:")
    print(f"  • Click / Pinch sessions:  {len(click_sessions)}")
    print(f"  • Scroll / Wave sessions:  {len(scroll_sessions)}")
    print(f"  • Resting / Dwell sessions: {len(dwell_sessions)}")
    print("\nRECOMMENDED TUNING PARAMETERS:")
    for k, v in report["recommended_constants"].items():
        print(f"  -> {k:28s} = {v}")

    # Save reports
    json_path = os.path.join(RECORDINGS_DIR, "analysis_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    md_path = os.path.join(RECORDINGS_DIR, "analysis_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Smart Mirror — Gesture Calibration & Analysis Report\n\n")
        f.write(f"Generated on **{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}** across **{len(files)}** recorded sessions.\n\n")
        f.write("## 1. Calibrated Tuning Constants\n\n")
        f.write("| Parameter | Calibrated Value | Description |\n")
        f.write("| :--- | :--- | :--- |\n")
        for k, v in report["recommended_constants"].items():
            f.write(f"| `{k}` | `{v}` | Calibrated from empirical recording distributions |\n")
        f.write("\n## 2. Detailed Metrics by Mode\n\n")
        f.write("```json\n" + json.dumps(report["results"], indent=2) + "\n```\n")

    print(f"\n[ANALYSIS] Saved report to {json_path} and {md_path}\n" + "=" * 65 + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="Smart Mirror Gesture Recorder & Calibration Tool")
    parser.add_argument("--camera-id", default=0, type=int, help="Webcam device index (default 0)")
    parser.add_argument("--flip", action="store_true", help="Mirror video horizontally")
    parser.add_argument("--analyze", action="store_true", help="Run analysis on existing recordings and exit")
    args = parser.parse_args()

    if args.analyze:
        analyze_recordings()
        return

    app = GestureRecorderApp(camera_id=args.camera_id, flip=args.flip)
    app.run()


if __name__ == "__main__":
    main()
