import cv2
import os
import time
import sys
import subprocess

# Configuration
if len(sys.argv) > 1:
    PERSON_NAME = sys.argv[1]
else:
    PERSON_NAME = "john"  # Default

DATASET_PATH = f'dataset/{PERSON_NAME}'
NUM_PHOTOS = 10  # Number of photos to capture automatically
DELAY = 0.5  # Delay between captures in seconds

def capture_photos():
    if not os.path.exists(DATASET_PATH):
        os.makedirs(DATASET_PATH)

    print(f"[INFO] Capturing {NUM_PHOTOS} photos for {PERSON_NAME} automatically...")

    count = 0
    while count < NUM_PHOTOS:
        img_path = os.path.join(DATASET_PATH, f'{PERSON_NAME}_{count:04d}.jpg')
        
        # Use rpicam-still to capture image
        cmd = ['rpicam-still', '--width', '640', '--height', '480', '-o', img_path, '--nopreview']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"[INFO] Saved {img_path}")
            count += 1
        else:
            print(f"[ERROR] Failed to capture {img_path}: {result.stderr}")
            break
            
        time.sleep(DELAY)

    print(f"[INFO] Captured {count} photos for {PERSON_NAME}")

if __name__ == "__main__":
    capture_photos()
