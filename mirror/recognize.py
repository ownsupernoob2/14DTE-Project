# Copyright 2023 The MediaPipe Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Main scripts to run gesture recognition."""
# Copyright 2023 The MediaPipe Authors. All Rights Reserved.
# ... (License header omitted for brevity) ...

import argparse
import sys
import time
import json
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.framework.formats import landmark_pb2

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# Global variables
COUNTER, FPS = 0, 0
START_TIME = time.time()
TIMESTAMP_COUNTER = 0

# Use Shared Memory for the image (Faster, no SD card wear)
VISION_FILE = '/dev/shm/ai_view.jpg'

def run(model: str, num_hands: int,
        min_hand_detection_confidence: float,
        min_hand_presence_confidence: float, min_tracking_confidence: float,
        camera_id: int, width: int, height: int) -> None:

  cap = None
  while cap is None or not cap.isOpened():
    cap = cv2.VideoCapture(camera_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
      print(f'Waiting for camera {camera_id} to be available...')
      time.sleep(1)
  
  print(f'Camera {camera_id} opened successfully.')

  # Visualization parameters
  row_size = 50 
  left_margin = 24
  text_color = (0, 0, 0)
  font_size = 1
  font_thickness = 1
  fps_avg_frame_count = 10
  label_text_color = (255, 255, 255)
  label_font_size = 1
  label_thickness = 2

  recognition_frame = None
  recognition_result_list = []

  def save_result(result: vision.GestureRecognizerResult,
                  unused_output_image: mp.Image, timestamp_ms: int):
      global FPS, COUNTER, START_TIME
      if COUNTER % fps_avg_frame_count == 0:
          FPS = fps_avg_frame_count / (time.time() - START_TIME)
          START_TIME = time.time()
      recognition_result_list.append(result)
      COUNTER += 1

  base_options = python.BaseOptions(model_asset_path=model)
  options = vision.GestureRecognizerOptions(base_options=base_options,
                                          running_mode=vision.RunningMode.LIVE_STREAM,
                                          num_hands=num_hands,
                                          min_hand_detection_confidence=min_hand_detection_confidence,
                                          min_hand_presence_confidence=min_hand_presence_confidence,
                                          min_tracking_confidence=min_tracking_confidence,
                                          result_callback=save_result)
  recognizer = vision.GestureRecognizer.create_from_options(options)

  frame_counter = 0
  
  while True:
    ret, image = cap.read()
    if not ret:
      sys.exit('ERROR: Unable to read from camera.')

    frame_counter += 1
    
    # --- SAVE FRAME FOR AI SERVICE ---
    # We save every 5th frame to save CPU, which is plenty for the AI to "see"
    if frame_counter % 5 == 0:
        try:
            # We save the 'image' variable directly (before flipping) 
            # so the AI can read text correctly.
            cv2.imwrite(VISION_FILE, image)
        except Exception:
            pass

    # Optimization: process every 4th frame for hand tracking
    if frame_counter % 4 != 0:
      continue

    # Flip for Mirror Effect (Visuals only)
    image = cv2.flip(image, 1)
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)

    global TIMESTAMP_COUNTER
    recognizer.recognize_async(mp_image, TIMESTAMP_COUNTER)
    TIMESTAMP_COUNTER += 1

    # Show FPS
    fps_text = 'FPS = {:.1f}'.format(FPS)
    text_location = (left_margin, row_size)
    current_frame = image
    cv2.putText(current_frame, fps_text, text_location, cv2.FONT_HERSHEY_DUPLEX,
                font_size, text_color, font_thickness, cv2.LINE_AA)

    while recognition_result_list:
      result = recognition_result_list.pop(0)
      
      # Process Hand Landmarks
      for hand_index, hand_landmarks in enumerate(result.hand_landmarks):
        
        # Calculate Hand Center
        frame_height, frame_width = current_frame.shape[:2]
        avg_x = sum(landmark.x for landmark in hand_landmarks) / len(hand_landmarks)
        avg_y = sum(landmark.y for landmark in hand_landmarks) / len(hand_landmarks)
        hand_center_x = int(avg_x * frame_width)
        hand_center_y = int(avg_y * frame_height)

        # Detect pinch (click)
        thumb_index_touch = False
        if len(hand_landmarks) > 8:
          thumb_tip = hand_landmarks[4]
          index_tip = hand_landmarks[8]
          distance = ((thumb_tip.x - index_tip.x)**2 + (thumb_tip.y - index_tip.y)**2)**0.5
          if distance < 0.05:
            thumb_index_touch = True

        # Draw Landmarks
        hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
        hand_landmarks_proto.landmark.extend([
          landmark_pb2.NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z) 
          for landmark in hand_landmarks
        ])
        mp_drawing.draw_landmarks(
          current_frame,
          hand_landmarks_proto,
          mp_hands.HAND_CONNECTIONS,
          mp_drawing_styles.get_default_hand_landmarks_style(),
          mp_drawing_styles.get_default_hand_connections_style())

        # Write Data to JSON (Atomic Write)
        gesture_name = result.gestures[0][0].category_name if result.gestures and len(result.gestures) > 0 and len(result.gestures[0]) > 0 else ""
        
        data = {
            'hand_center_x': hand_center_x,
            'hand_center_y': hand_center_y,
            'thumb_index_touch': thumb_index_touch,
            'gesture': gesture_name,
            'timestamp': time.time()
        }
        
        temp_file = '/tmp/hand_data.json.tmp'
        target_file = '/tmp/hand_data.json'
        try:
            with open(temp_file, 'w') as f:
                json.dump(data, f)
            os.rename(temp_file, target_file)
        except Exception:
            pass

      recognition_frame = current_frame

  recognizer.close()
  cap.release()

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--model', default='gesture_recognizer.task')
  parser.add_argument('--numHands', default=1, type=int)
  parser.add_argument('--minHandDetectionConfidence', default=0.5, type=float)
  parser.add_argument('--minHandPresenceConfidence', default=0.5, type=float)
  parser.add_argument('--minTrackingConfidence', default=0.5, type=float)
  parser.add_argument('--cameraId', default=10, type=int)
  parser.add_argument('--frameWidth', default=640, type=int)
  parser.add_argument('--frameHeight', default=480, type=int)
  args = parser.parse_args()

  run(args.model, args.numHands, args.minHandDetectionConfidence,
      args.minHandPresenceConfidence, args.minTrackingConfidence,
      args.cameraId, args.frameWidth, args.frameHeight)

if __name__ == '__main__':
  main()