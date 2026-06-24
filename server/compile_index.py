import os
import sys
import pickle
import json
import numpy as np
import faiss

def main():
    encodings_dir = "encodings"
    index_path = "encodings/index.faiss"
    map_path = "encodings/user_map.json"

    if not os.path.exists(encodings_dir):
        os.makedirs(encodings_dir, exist_ok=True)

    # 128-dimensional space for face_recognition encodings
    dimension = 128
    index = faiss.IndexFlatL2(dimension)
    user_map = []

    # Read all pickle files in alphabetical order for consistency
    for filename in sorted(os.listdir(encodings_dir)):
        if filename.endswith(".pickle"):
            user_id = os.path.splitext(filename)[0]
            pickle_path = os.path.join(encodings_dir, filename)
            try:
                with open(pickle_path, 'rb') as f:
                    encodings = pickle.load(f)
                if encodings:
                    encodings_arr = np.array(encodings, dtype=np.float32)
                    index.add(encodings_arr)
                    for _ in range(len(encodings)):
                        user_map.append(user_id)
            except Exception as e:
                print(f"Error loading {pickle_path}: {e}", file=sys.stderr)

    # Write the compiled index and user map
    faiss.write_index(index, index_path)
    with open(map_path, 'w') as f:
        json.dump(user_map, f)

    print("OK")

if __name__ == "__main__":
    main()
