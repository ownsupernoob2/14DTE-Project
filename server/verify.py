import sys
import os
import face_recognition
import numpy as np

def main():
    if len(sys.argv) < 3:
        print("Usage: python verify.py <target_image> <faces_dir>")
        sys.exit(1)

    target_image_path = sys.argv[1]
    faces_dir = sys.argv[2]

    # Load target image
    try:
        target_image = face_recognition.load_image_file(target_image_path)
        target_encodings = face_recognition.face_encodings(target_image)
    except Exception as e:
        print("ERROR: Could not process target image")
        sys.exit(1)

    if len(target_encodings) == 0:
        print("NO_FACE")
        sys.exit(0)

    target_encoding = target_encodings[0]

    best_match = "unknown"
    best_distance = 1.0

    # Iterate over saved faces
    if os.path.exists(faces_dir):
        for filename in os.listdir(faces_dir):
            if filename.endswith(".jpg") or filename.endswith(".png"):
                user_id = os.path.splitext(filename)[0]
                filepath = os.path.join(faces_dir, filename)
                
                try:
                    known_image = face_recognition.load_image_file(filepath)
                    known_encodings = face_recognition.face_encodings(known_image)
                    if len(known_encodings) > 0:
                        known_encoding = known_encodings[0]
                        distance = face_recognition.face_distance([known_encoding], target_encoding)[0]
                        
                        if distance < 0.6 and distance < best_distance:
                            best_distance = distance
                            best_match = user_id
                except Exception as e:
                    pass

    print(f"MATCH:{best_match}")

if __name__ == "__main__":
    main()
