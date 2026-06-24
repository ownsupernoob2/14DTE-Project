import os
import sys
import pickle
import json
import numpy as np

def main():
    encodings_dir = "encodings"
    export_path = "encodings/exported_encodings.json"

    if not os.path.exists(encodings_dir):
        os.makedirs(encodings_dir, exist_ok=True)

    vectors = []
    user_map = []

    # Read all pickle files in alphabetical order
    for filename in sorted(os.listdir(encodings_dir)):
        if filename.endswith(".pickle"):
            user_id = os.path.splitext(filename)[0]
            pickle_path = os.path.join(encodings_dir, filename)
            try:
                with open(pickle_path, 'rb') as f:
                    encodings = pickle.load(f)
                if encodings:
                    for enc in encodings:
                        # Convert numpy array / list of floats to standard python list for JSON
                        if isinstance(enc, np.ndarray):
                            vectors.append(enc.tolist())
                        else:
                            vectors.append(list(enc))
                        user_map.append(user_id)
            except Exception as e:
                print(f"Error loading {pickle_path}: {e}", file=sys.stderr)

    # Save to JSON
    with open(export_path, 'w') as f:
        json.dump({
            "vectors": vectors,
            "user_map": user_map
        }, f)

    print("OK")

if __name__ == "__main__":
    main()
