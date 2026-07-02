# mirror/gesture_engine.py
import os
import sys
import json
import time
import math
import cv2
import numpy as np

try:
    import mediapipe as mp
except ImportError:
    mp = None

GESTURE_STATUS_FILE = os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")), "gesture_status.json"
)

class GestureEngine:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.running = False
        self.hands = None
        self.mp_hands = None

        if mp is not None:
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        else:
            print("[GESTURE] Warning: mediapipe not installed. Running in mock/headless mode.")

        # Tracking state
        self.history = []  # list of (timestamp, x, y)
        self.last_gesture = None
        self.last_gesture_time = 0.0
        self.peace_start_time = None
        self.ok_start_time = None
        
        # Pinch-to-scroll state
        self.is_pinching = False
        self.last_pinch_y = None

    def calculate_distance(self, p1, p2):
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

    def detect_gestures(self, landmarks, shape):
        now = time.time()
        w, h = shape[1], shape[0]

        # Landmark coordinates
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        index_tip = landmarks[8]
        index_mcp = landmarks[5]
        middle_tip = landmarks[12]
        middle_mcp = landmarks[9]
        ring_tip = landmarks[16]
        ring_mcp = landmarks[13]
        pinky_tip = landmarks[20]
        pinky_mcp = landmarks[17]

        # Detect fingers extension (higher Y is lower on screen)
        index_extended = index_tip.y < index_mcp.y
        middle_extended = middle_tip.y < middle_mcp.y
        ring_extended = ring_tip.y < ring_mcp.y
        pinky_extended = pinky_tip.y < pinky_mcp.y

        # Pinch detection (Thumb tip to Index tip distance)
        pinch_dist = self.calculate_distance(thumb_tip, index_tip)
        pinched = pinch_dist < 0.06

        current_event = None
        scroll_delta = 0

        # 1. Pinch & Scroll check
        # Pinch is active if thumb and index are pinched, but middle, ring, pinky are NOT all extended (to avoid OK sign overlap)
        is_only_pinch = pinched and not (middle_extended and ring_extended and pinky_extended)
        if is_only_pinch:
            pinch_y = index_tip.y
            if not self.is_pinching:
                self.is_pinching = True
                self.last_pinch_y = pinch_y
            else:
                dy = pinch_y - self.last_pinch_y
                # If dy is negative, hand moved UP (scroll up). If positive, hand moved DOWN (scroll down)
                if abs(dy) > 0.02:
                    scroll_delta = -int(dy * 100) # Negative for scroll down, Positive for scroll up
                    self.last_pinch_y = pinch_y
                    current_event = "scroll"
        else:
            self.is_pinching = False
            self.last_pinch_y = None

        # 2. Hold Peace Sign (Shortcut to Notices)
        is_peace = index_extended and middle_extended and not ring_extended and not pinky_extended and not pinched
        if is_peace:
            if self.peace_start_time is None:
                self.peace_start_time = now
            elif now - self.peace_start_time >= 2.0:
                current_event = "peace_hold"
        else:
            self.peace_start_time = None

        # 3. Hold OK Sign (Shortcut to Timetable)
        is_ok = pinched and middle_extended and ring_extended and pinky_extended
        if is_ok:
            if self.ok_start_time is None:
                self.ok_start_time = now
            elif now - self.ok_start_time >= 2.0:
                current_event = "ok_hold"
        else:
            self.ok_start_time = None

        # 4. Swipe Left / Right check using wrist tracking
        self.history.append((now, wrist.x, wrist.y))
        # Keep history within last 0.8 seconds
        self.history = [pt for pt in self.history if now - pt[0] < 0.8]

        if len(self.history) > 5 and current_event is None:
            first_pt = self.history[0]
            last_pt = self.history[-1]
            dx = last_pt[1] - first_pt[1]
            dt = last_pt[0] - first_pt[0]
            
            if dt > 0.15:
                # Swipe Left: X decreases (since camera might be mirrored, verify movement direction)
                # Left on screen is generally decreasing X in normalized coords (0 is left, 1 is right)
                if dx < -0.25 and now - self.last_gesture_time > 1.0:
                    current_event = "swipe_left"
                    self.last_gesture_time = now
                    self.history.clear()
                elif dx > 0.25 and now - self.last_gesture_time > 1.0:
                    current_event = "swipe_right"
                    self.last_gesture_time = now
                    self.history.clear()

        return current_event, scroll_delta

    def write_status(self, gesture, scroll_delta=0):
        data = {
            "gesture": gesture,
            "scroll_delta": scroll_delta,
            "timestamp": time.time()
        }
        try:
            tmp = GESTURE_STATUS_FILE + ".tmp"
            with open(tmp, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, GESTURE_STATUS_FILE)
        except Exception as e:
            print(f"[GESTURE] Error writing status: {e}")

    def run(self):
        self.running = True
        cap = cv2.VideoCapture(0) # Use default camera or specify camera_id
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        print("[GESTURE] Gesture engine running...")
        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue

                if self.hands is not None:
                    # Flip frame horizontally for natural mirror behavior
                    frame = cv2.flip(frame, 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self.hands.process(rgb)

                    gesture = None
                    scroll_delta = 0
                    if results.multi_hand_landmarks:
                        for hand_landmarks in results.multi_hand_landmarks:
                            gesture, scroll_delta = self.detect_gestures(hand_landmarks.landmark, frame.shape)
                            break
                    
                    if gesture:
                        print(f"[GESTURE] Detected: {gesture} (scroll_delta: {scroll_delta})")
                        self.write_status(gesture, scroll_delta)
                    else:
                        # Clear active transient gestures/scrolls periodically
                        self.write_status(None, 0)
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            cap.release()

if __name__ == "__main__":
    cam_id = 0
    if len(sys.argv) > 1:
        try:
            cam_id = int(sys.argv[1])
        except ValueError:
            pass
    engine = GestureEngine(cam_id)
    engine.run()
