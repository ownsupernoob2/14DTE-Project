import cv2
import face_recognition
import pickle
import time
import json
import os
import requests
import numpy as np

# Paths & Endpoint
ENCODINGS_PATH = 'encodings.pickle'
FACE_DATA_FILE = '/tmp/face_status.json'
API_URL = os.environ.get('API_URL', 'https://api.smartmirror.me')

def download_encodings():
    """Attempt to download the latest unified encodings.pickle from the server."""
    try:
        print(f"[INFO] Fetching latest encodings from {API_URL}/api/encodings/download ...")
        res = requests.get(f"{API_URL}/api/encodings/download", timeout=10)
        if res.status_code == 200:
            with open(ENCODINGS_PATH, "wb") as f:
                f.write(res.content)
            print("[INFO] Successfully synchronized encodings from the backend server!")
            return True
        else:
            print(f"[WARNING] Server returned status code {res.status_code} for encodings download")
    except Exception as e:
        print(f"[WARNING] Could not sync encodings from server (using local backup): {e}")
    return False

# 1. Sync encodings at startup
download_encodings()

# 2. Load the known faces and embeddings (fail gracefully if none exists yet)
if not os.path.exists(ENCODINGS_PATH):
    print("[ERROR] No encodings.pickle found! Waiting for server sync...")
    while not download_encodings():
        time.sleep(5)

print("[INFO] Loading encodings...")
with open(ENCODINGS_PATH, "rb") as f:
    data = pickle.loads(f.read())
known_face_encodings = data["encodings"]
known_face_names = data["names"]

# Initialize camera
cap = cv2.VideoCapture(10)  # Use virtual camera /dev/video10
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    print("[ERROR] Cannot open camera")
    exit(1)

print("[INFO] Starting local face recognition with server encodings...")

frame_count = 0
start_time = time.time()
last_detected_time = 0
current_user = "idle"
last_sync_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % 3 != 0:
        continue

    # Periodically re-sync encodings in the background (every 5 minutes)
    if time.time() - last_sync_time > 300:
        last_sync_time = time.time()
        if download_encodings():
            # Reload encodings
            try:
                with open(ENCODINGS_PATH, "rb") as f:
                    data = pickle.loads(f.read())
                known_face_encodings = data["encodings"]
                known_face_names = data["names"]
                print("[INFO] Encodings reloaded successfully in background.")
            except Exception as e:
                print(f"[ERROR] Failed to reload encodings: {e}")

    # Resize for performance (0.25x scaling for super fast recognition on Pi)
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    # Detect faces
    face_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

    detected = len(face_locations) > 0
    user_id = "idle"
    user_name = "idle"
    confidence = 0.0

    if detected:
        # Find best match
        face_names = []
        face_confidences = []
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"

            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if face_distances.size > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
                    confidence = 1 - face_distances[best_match_index]  # Higher confidence = better match
                else:
                    confidence = 0.0
            else:
                confidence = 0.0

            face_names.append(name)
            face_confidences.append(confidence)

        # Use the best confidence match
        if face_confidences:
            best_idx = np.argmax(face_confidences)
            user_name = face_names[best_idx]
            confidence = face_confidences[best_idx]
            current_user = user_name if user_name != "Unknown" else current_user
            last_detected_time = time.time()

    # Check for idle timeout (no face for 30 seconds -> back to idle)
    if not detected and time.time() - last_detected_time > 30:
        current_user = "idle"

    user_name = current_user
    user_id = current_user

    # Prepare data for UI
    data = {
        "detected": detected,
        "confidence": float(confidence),
        "count": len(face_locations),
        "user_id": user_id,
        "user_name": user_name,
        "timestamp": time.time()
    }

    # Write to JSON (atomic write using rename to prevent UI reading blank files)
    try:
        with open(FACE_DATA_FILE + '.tmp', 'w') as f:
            json.dump(data, f)
        os.rename(FACE_DATA_FILE + '.tmp', FACE_DATA_FILE)
    except Exception as e:
        print(f"[ERROR] Writing JSON: {e}")

    # FPS calculation
    if frame_count % 10 == 0:
        fps = 10 / (time.time() - start_time)
        print(f"[INFO] FPS: {fps:.1f}, Detected: {detected}, User: {user_id}")
        start_time = time.time()

cap.release()
