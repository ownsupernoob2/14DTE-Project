"""
train.py — Face encoding trainer
Usage: python train.py <images_dir> <output_pickle>

Loads all JPEG images from images_dir, computes face_recognition encodings,
filters out outlier frames (distance > 0.40 from the median encoding),
saves the list of encodings to output_pickle. Prints OK:<N> or ERROR:<msg>.
"""
import sys
import os
import pickle
import face_recognition
import numpy as np


def main():
    if len(sys.argv) < 3:
        print("ERROR:Usage: python train.py <images_dir> <output_pickle>")
        sys.exit(1)

    images_dir = sys.argv[1]
    output_pickle = sys.argv[2]

    if not os.path.isdir(images_dir):
        print(f"ERROR:Images directory not found: {images_dir}")
        sys.exit(1)

    encodings = []
    skipped = 0

    image_files = [
        f for f in os.listdir(images_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]

    if not image_files:
        print("ERROR:No image files found in directory")
        sys.exit(1)

    for filename in image_files:
        filepath = os.path.join(images_dir, filename)
        try:
            image = face_recognition.load_image_file(filepath)
            found = face_recognition.face_encodings(image)
            if found:
                encodings.append(found[0])
            else:
                skipped += 1
        except Exception as e:
            skipped += 1
            continue

    if not encodings:
        print("ERROR:No faces detected in any of the provided images")
        sys.exit(1)

    # ── Outlier filtering ─────────────────────────────────────────────────
    # Compute the median encoding and remove any frame whose distance from the
    # median exceeds 0.40. This discards bad scans (side-profiles, blinks, or
    # background faces) that would otherwise pollute the recognition model.
    OUTLIER_THRESHOLD = 0.40
    enc_array = np.array(encodings)
    median_enc = np.median(enc_array, axis=0)

    filtered = []
    outlier_count = 0
    for enc in encodings:
        dist = float(np.linalg.norm(enc - median_enc))
        if dist <= OUTLIER_THRESHOLD:
            filtered.append(enc)
        else:
            outlier_count += 1

    if not filtered:
        # All frames were outliers — fall back to all encodings (better than nothing)
        print(f"WARNING:All {len(encodings)} encodings were outliers; using unfiltered set")
        filtered = encodings
    else:
        print(f"[train] Kept {len(filtered)} / {len(encodings)} frames (removed {outlier_count} outliers)")

    # Ensure output directory exists
    out_dir = os.path.dirname(output_pickle)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_pickle, 'wb') as f:
        pickle.dump(filtered, f)

    print(f"OK:{len(filtered)}")


if __name__ == "__main__":
    main()
