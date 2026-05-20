import os
import pickle
import sys

def main():
    encodings_dir = "encodings"
    output_path = "encodings.pickle"
    
    known_encodings = []
    known_names = []
    
    if not os.path.exists(encodings_dir):
        os.makedirs(encodings_dir)
        
    for filename in os.listdir(encodings_dir):
        if filename.endswith(".pickle") and filename != "encodings.pickle":
            user_id = os.path.splitext(filename)[0]
            try:
                with open(os.path.join(encodings_dir, filename), "rb") as f:
                    user_encs = pickle.load(f)
                for enc in user_encs:
                    known_encodings.append(enc)
                    known_names.append(user_id)
            except Exception as e:
                print(f"Error loading {filename}: {e}", file=sys.stderr)
                
    data = {"encodings": known_encodings, "names": known_names}
    with open(output_path, "wb") as f:
        pickle.dump(data, f)
    print("OK")

if __name__ == "__main__":
    main()
