"""
train.py — turn face-scan photos into face encodings.

Usage: python train.py <images_dir> <output_json>

Computes a 128-number face_recognition encoding per photo, drops photos whose
encoding is far from the median (side-on, blinking, someone else in frame), and
writes {"encodings": [[...128 floats], ...], "median": [...]} to output_json.
Prints OK:<frames kept> on success or ERROR:<message> on failure.

Duplicate-face checks and storage happen in the Go server; this script only
does the maths that needs dlib.
"""
import json
import os
import sys

import face_recognition
import numpy as np

OUTLIER_THRESHOLD = 0.40


def main():
    if len(sys.argv) != 3:
        print("ERROR:Usage: python train.py <images_dir> <output_json>")
        return 1
    images_dir, output_json = sys.argv[1], sys.argv[2]

    files = sorted(f for f in os.listdir(images_dir) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if not files:
        print("ERROR:No photos were received")
        return 1

    encodings = []
    for name in files:
        try:
            image = face_recognition.load_image_file(os.path.join(images_dir, name))
            found = face_recognition.face_encodings(image)
        except Exception:
            continue
        if found:
            encodings.append(found[0])

    if not encodings:
        print("ERROR:No face was found in the photos. Face the camera in good light and try again.")
        return 1

    median = np.median(np.array(encodings), axis=0)
    kept = [e for e in encodings if float(np.linalg.norm(e - median)) <= OUTLIER_THRESHOLD] or encodings
    median = np.median(np.array(kept), axis=0)

    with open(output_json, "w") as f:
        json.dump({"encodings": [e.tolist() for e in kept], "median": median.tolist()}, f)
    print(f"OK:{len(kept)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
