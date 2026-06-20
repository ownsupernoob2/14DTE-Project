"""
verify.py — Face verification against stored pickle encodings
Usage: python verify.py <target_image_path> <encodings_dir>

Loads all .pickle files in encodings_dir (each named <user_id>.pickle),
compares the target image against all stored encodings, prints MATCH:<user_id>
or NO_FACE. Output format is unchanged so the mirror remains compatible.
"""
import sys
import os
import pickle
import face_recognition
import numpy as np


def main():
    if len(sys.argv) < 3:
        print("ERROR:Usage: python verify.py <target_image> <encodings_dir>")
        sys.exit(1)

    target_image_path = sys.argv[1]
    encodings_dir = sys.argv[2]

    # Load and encode the target image
    try:
        target_image = face_recognition.load_image_file(target_image_path)
        target_encodings = face_recognition.face_encodings(target_image)
    except Exception as e:
        print("ERROR:Could not process target image")
        sys.exit(1)

    if not target_encodings:
        print("NO_FACE")
        sys.exit(0)

    target_encoding = target_encodings[0]

    best_match_user = "unknown"
    best_distance = 1.0

    if not os.path.isdir(encodings_dir):
        print(f"MATCH:{best_match_user}")
        return

    # Iterate over per-user pickle files
    for filename in os.listdir(encodings_dir):
        if not filename.endswith(".pickle"):
            continue

        user_id = os.path.splitext(filename)[0]
        pickle_path = os.path.join(encodings_dir, filename)

        try:
            with open(pickle_path, 'rb') as f:
                known_encodings = pickle.load(f)

            if not known_encodings:
                continue

            # Compare against all stored encodings for this user
            distances = face_recognition.face_distance(known_encodings, target_encoding)
            min_distance = float(np.min(distances))

            if min_distance < 0.38 and min_distance < best_distance:
                best_distance = min_distance
                best_match_user = user_id

        except Exception:
            continue

    print(f"MATCH:{best_match_user}")


if __name__ == "__main__":
    main()
