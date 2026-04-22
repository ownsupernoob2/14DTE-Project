import cv2
import os
import pickle
import face_recognition
import numpy as np
from imutils import paths
import json

# Paths
DATASET_PATH = 'dataset'
ENCODINGS_PATH = 'encodings.pickle'
FACE_STATUS_FILE = '/tmp/face_status.json'

def train_model():
    print("[INFO] quantifying faces...")
    imagePaths = list(paths.list_images(DATASET_PATH))

    knownEncodings = []
    knownNames = []

    for (i, imagePath) in enumerate(imagePaths):
        print(f"[INFO] processing image {i + 1}/{len(imagePaths)}")
        name = imagePath.split(os.path.sep)[-2]

        image = cv2.imread(imagePath)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        boxes = face_recognition.face_locations(rgb, model='hog')
        encodings = face_recognition.face_encodings(rgb, boxes)

        for encoding in encodings:
            knownEncodings.append(encoding)
            knownNames.append(name)

    print("[INFO] serializing encodings...")
    data = {"encodings": knownEncodings, "names": knownNames}
    with open(ENCODINGS_PATH, "wb") as f:
        f.write(pickle.dumps(data))

if __name__ == "__main__":
    if not os.path.exists(DATASET_PATH):
        os.makedirs(DATASET_PATH)
        print(f"[INFO] Created dataset directory: {DATASET_PATH}")
        print("[INFO] Add subfolders with user names and photos inside them.")
    else:
        train_model()
        print("[INFO] Model trained and saved to encodings.pickle")
