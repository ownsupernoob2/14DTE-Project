import json
import os
import tempfile
import sys
import time

def _get_temp_path(filename):
    if os.name != 'nt' and os.path.exists('/tmp'):
        return os.path.join('/tmp', filename)
    return os.path.join(tempfile.gettempdir(), filename)

FACE_DATA_FILE = _get_temp_path('face_status.json')

def write_state(state_type):
    data = {
        "detected": False,
        "recognized": False,
        "confidence": 0.0,
        "in_grace": False,
        "state": "idle",
        "user_id": "idle",
        "user_name": "",
        "config": {}
    }

    if state_type == "idle":
        pass
    elif state_type == "guest":
        data["detected"] = True
        data["state"] = "guest"
        data["in_grace"] = True
    elif state_type == "user":
        data["detected"] = True
        data["recognized"] = True
        data["confidence"] = 0.99
        data["state"] = "user"
        data["user_id"] = "google-oauth2_106749058814716632636"
        data["user_name"] = "Mock User"

    try:
        # Write atomically
        temp_file = FACE_DATA_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f)
        os.replace(temp_file, FACE_DATA_FILE)
        print(f"[OK] Successfully set mirror mode to: {state_type.upper()}")
        print(f"Data written to: {FACE_DATA_FILE}")
    except Exception as e:
        print(f"[ERROR] Error writing state: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode in ["idle", "guest", "user"]:
            write_state(mode)
        else:
            print("Usage: python mock_face.py [idle|guest|user]")
    else:
        while True:
            print("\n--- Mock Smart Mirror State ---")
            print("1. Idle Mode")
            print("2. Guest Mode")
            print("3. User Mode (google-oauth2_106749058814716632636)")
            print("q. Quit")
            choice = input("Select mode (1/2/3/q): ")
            
            if choice == "1":
                write_state("idle")
            elif choice == "2":
                write_state("guest")
            elif choice == "3":
                write_state("user")
            elif choice.lower() == "q":
                break
            else:
                print("Invalid choice")
