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
        "config": {},
        "server_online": True,
        "server_status": "online",
        "timestamp": time.time(),
    }

    if state_type == "idle":
        pass
    elif state_type == "guest":
        data["detected"] = True
        data["state"] = "guest"
        data["in_grace"] = True
    elif state_type == "guest_offline":
        data["detected"] = True
        data["state"] = "guest"
        data["in_grace"] = False
        data["server_online"] = False
        data["server_status"] = "offline"
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

def simulate_walk_up(duration=6.0):
    print(f"\n[SIMULATION] Person approaches mirror (Server Offline)...")
    write_state("guest_offline")
    print(f"[SIMULATION] Holding guest mode for {duration}s...")
    time.sleep(duration)
    print(f"[SIMULATION] Person walks away — returning to IDLE...")
    write_state("idle")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        if mode in ["idle", "guest", "user", "guest_offline"]:
            write_state(mode)
        elif mode in ["offline", "4"]:
            write_state("guest_offline")
        elif mode in ["simulate", "5", "walk"]:
            dur = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
            simulate_walk_up(dur)
        else:
            print("Usage: python mock_face.py [idle|guest|user|guest_offline|simulate]")
    else:
        while True:
            print("\n--- Mock Smart Mirror State ---")
            print("1. Idle Mode")
            print("2. Guest Mode (Online)")
            print("3. User Mode (google-oauth2_106749058814716632636)")
            print("4. Guest Mode (Server Offline - Permanent)")
            print("5. Simulate Walk-Up & Leave (Offline Guest for 6s -> Idle)")
            print("q. Quit")
            choice = input("Select mode (1/2/3/4/5/q): ")
            
            if choice == "1":
                write_state("idle")
            elif choice == "2":
                write_state("guest")
            elif choice == "3":
                write_state("user")
            elif choice == "4":
                write_state("guest_offline")
            elif choice == "5":
                simulate_walk_up(6.0)
            elif choice.lower() == "q":
                break
            else:
                print("Invalid choice")
