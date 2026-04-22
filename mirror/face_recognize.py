import cv2
import face_recognition
import pickle
import time
import json
import os
import numpy as np

# Paths
ENCODINGS_PATH = 'encodings.pickle'
FACE_STATUS_FILE = '/tmp/face_status.json'

# Load the known faces and embeddings
print("[INFO] loading encodings...")
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

print("[INFO] Starting face recognition...")

frame_count = 0
start_time = time.time()
last_detected_time = 0
current_user = "idle"

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % 3 != 0:
        continue

    # Resize for performance
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
                    confidence = 1 - face_distances[best_match_index]  # Higher is better match
                else:
                    confidence = 0.0
            else:
                confidence = 0.0

            face_names.append(name)
            face_confidences.append(confidence)

        # Use the best confidence
        if face_confidences:
            best_idx = np.argmax(face_confidences)
            user_name = face_names[best_idx]
            confidence = face_confidences[best_idx]
            current_user = user_name if user_name != "Unknown" else current_user
            last_detected_time = time.time()

    # Check for idle timeout
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

    # Write to JSON
    try:
        with open(FACE_STATUS_FILE + '.tmp', 'w') as f:
            json.dump(data, f)
        os.rename(FACE_STATUS_FILE + '.tmp', FACE_STATUS_FILE)
    except Exception as e:
        print(f"[ERROR] Writing JSON: {e}")

    # FPS calculation
    frame_count += 1
    if frame_count % 10 == 0:
        fps = 10 / (time.time() - start_time)
        print(f"[INFO] FPS: {fps:.1f}, Detected: {detected}, User: {user_id}")
        start_time = time.time()

cap.release()
