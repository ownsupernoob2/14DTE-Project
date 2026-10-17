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
       print(
    f"[train] Kept {len(filtered)} / {len(encodings)} frames "
    f"(removed {outlier_count} outliers)",
    file=sys.stderr
)


    # ── Collision Check against other registered students ─────────────────
    # If this face closely matches an already registered user (< 0.38 distance),
    # reject to prevent account impersonation or duplicate registrations.
    enc_dir = os.path.dirname(os.path.abspath(output_pickle))
    target_basename = os.path.basename(output_pickle)
    if os.path.isdir(enc_dir):
        for fname in os.listdir(enc_dir):
            if fname.endswith(".pickle") and fname != target_basename:
                other_path = os.path.join(enc_dir, fname)
                try:
                    with open(other_path, "rb") as f:
                        other_encs = pickle.load(f)
                    if other_encs:
                        dists = [float(np.linalg.norm(median_enc - o)) for o in other_encs]
                        if min(dists) < 0.38:
                            matched_account = fname.replace('.pickle', '')
                            attempted_account = target_basename.replace('.pickle', '')

                            # Append collision record to audit log for admin tracing
                            try:
                                log_dir = os.path.join(os.path.dirname(enc_dir), "data")
                                os.makedirs(log_dir, exist_ok=True)
                                log_path = os.path.join(log_dir, "face_collisions.json")
                                logs = []
                                if os.path.exists(log_path):
                                    try:
                                        with open(log_path, 'r') as lf:
                                            logs = json.load(lf)
                                    except Exception:
                                        logs = []
                                logs.append({
                                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "attempted_user": attempted_account,
                                    "matched_user": matched_account,
                                    "min_distance": round(min(dists), 4),
                                    "action": "BLOCKED_REGISTRATION",
                                    "contact_email": "marminamina3@gmail.com"
                                })
                                with open(log_path, 'w') as lf:
                                    json.dump(logs, lf, indent=2)
                            except Exception as le:
                                print(f"[train] Could not write collision log: {le}", file=sys.stderr)

                            print(
                                f"ERROR:COLLISION:This face closely matches an already registered account ({fname}).",
                                file=sys.stderr
                            )
                            print(f"ERROR:COLLISION:Face already registered to another student ({fname})")
                            sys.exit(1)
                except Exception:
                    continue

    # Ensure output directory exists
    out_dir = os.path.dirname(output_pickle)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_pickle, 'wb') as f:
        pickle.dump(filtered, f)

    print(f"OK:{len(filtered)}")


if __name__ == "__main__":
    main()
