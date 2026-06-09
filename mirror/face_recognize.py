import cv2
import time
import json
import os
import requests
import base64

FACE_STATUS_FILE = '/tmp/face_status.json'
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

cap = cv2.VideoCapture(10)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[ERROR] Cannot open camera")
    exit(1)

print("[INFO] Starting remote face recognition...")

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

frame_count = 0
start_time = time.time()
last_detected_time = 0
current_user = "idle"
last_api_call = 0
current_widgets = []

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

    confidence = 0.0

    if detected:
        last_detected_time = time.time()

        if time.time() - last_api_call > 2.0:
            last_api_call = time.time()
            _, buffer = cv2.imencode('.jpg', small_frame)
            b64_img = base64.b64encode(buffer).decode('utf-8')

            try:
                res = requests.post(
                    f"{API_URL}/api/verify-face",
                    json={"image": f"data:image/jpeg;base64,{b64_img}"},
                    timeout=3
                )

                if res.status_code == 200:
                    data = res.json()
                    current_user = data.get("user_id", "idle")
                    current_widgets = data.get("widgets", [])
                    confidence = 1.0
                else:
                    confidence = 0.0
                    current_widgets = []
            except Exception as e:
                print(f"[ERROR] API Call failed: {e}")

    if not detected and time.time() - last_detected_time > 30:
        current_user = "idle"
        current_widgets = []

    data = {
        "detected": detected,
        "confidence": float(confidence),
        "count": len(faces),
        "user_id": current_user,
        "user_name": current_user,
        "timestamp": time.time(),
        "widgets": current_widgets
    }

    try:
        with open(FACE_STATUS_FILE + '.tmp', 'w') as f:
            json.dump(data, f)
        os.rename(FACE_STATUS_FILE + '.tmp', FACE_STATUS_FILE)
    except Exception as e:
        print(f"[ERROR] Writing JSON: {e}")

    if frame_count % 10 == 0:
        fps = 10 / (time.time() - start_time)
        print(f"[INFO] FPS: {fps:.1f}, Detected: {detected}, User: {current_user}")
        start_time = time.time()

cap.release()
