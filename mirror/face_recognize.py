import cv2
import time
import json
import os
import requests
import base64

FACE_STATUS_FILE = '/tmp/face_status.json'
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

# How often to ask the server to verify the face and fetch the latest layout
API_POLL_INTERVAL = float(os.environ.get('FACE_API_POLL_SEC', '1.0'))
# Clear the session this many seconds after no face is visible
IDLE_TIMEOUT_SEC = float(os.environ.get('FACE_IDLE_TIMEOUT_SEC', '5.0'))

cap = cv2.VideoCapture(10)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[ERROR] Cannot open camera")
    exit(1)

print("[INFO] Starting remote face recognition...")
print(f"[INFO] API poll every {API_POLL_INTERVAL}s, idle timeout {IDLE_TIMEOUT_SEC}s")

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

frame_count = 0
start_time = time.time()
last_detected_time = 0.0
last_api_call = 0.0
current_user = "idle"
current_widgets = []
confidence = 0.0
recognized = False


def write_status(detected, faces_count):
    data = {
        "detected": detected,
        "recognized": recognized,
        "confidence": float(confidence),
        "count": faces_count,
        "user_id": current_user,
        "user_name": current_user,
        "timestamp": time.time(),
        "widgets": current_widgets,
    }
    try:
        with open(FACE_STATUS_FILE + '.tmp', 'w') as f:
            json.dump(data, f)
        os.rename(FACE_STATUS_FILE + '.tmp', FACE_STATUS_FILE)
    except Exception as e:
        print(f"[ERROR] Writing JSON: {e}")


def clear_session():
    global current_user, current_widgets, confidence, recognized
    current_user = "idle"
    current_widgets = []
    confidence = 0.0
    recognized = False


while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % 3 != 0:
        continue

    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    detected = len(faces) > 0
    now = time.time()

    if detected:
        last_detected_time = now

        if now - last_api_call >= API_POLL_INTERVAL:
            last_api_call = now
            _, buffer = cv2.imencode('.jpg', small_frame)
            b64_img = base64.b64encode(buffer).decode('utf-8')

            try:
                res = requests.post(
                    f"{API_URL}/api/verify-face",
                    json={"image": f"data:image/jpeg;base64,{b64_img}"},
                    timeout=3,
                )

                if res.status_code == 200:
                    data = res.json()
                    current_user = data.get("user_id", "idle")
                    current_widgets = data.get("widgets", [])
                    confidence = 1.0
                    recognized = current_user not in ("", "idle")
                else:
                    # Face visible but not registered on the server yet
                    clear_session()
            except Exception as e:
                print(f"[ERROR] API call failed: {e}")
                # Keep the last known good session until the next successful poll

    elif now - last_detected_time >= IDLE_TIMEOUT_SEC:
        if current_user != "idle" or current_widgets or recognized:
            clear_session()

    write_status(detected, len(faces))

    if frame_count % 30 == 0:
        fps = 30 / (now - start_time)
        widget_count = len(current_widgets)
        print(
            f"[INFO] FPS: {fps:.1f}, face: {detected}, "
            f"recognized: {recognized}, user: {current_user}, widgets: {widget_count}"
        )
        start_time = now

cap.release()
