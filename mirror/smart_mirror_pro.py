import pygame
import threading
import time
import json
import os
import requests
import math
import random
from datetime import datetime
from config import *

# Load Modules
from ui.menu import GlobalMenu
from ui.keyboard import VirtualKeyboard
from ui.loading_screen import LoadingScreen
from utils.fonts import get_font
from widgets import Widget, ClockWidget, WeatherWidget, GoogleCalendarWidget, VoiceAssistantWidget

class SmartMirrorPro:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.width, self.height = self.screen.get_size()
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # Core Fonts
        self.font_title = get_font(16, bold=True)
        self.font_content = get_font(18)

        # Components
        self.menu = GlobalMenu(self.width, self.height, self)
        self.keyboard = VirtualKeyboard(self.width, self.height)
        self.loading_screen = LoadingScreen(self.width, self.height)
        
        # State
        self.show_background = True
        self.scroll_y = 0
        self.target_scroll_y = 0
        self.bg_image = None
        self.setup_background()
        
        # Hand / Input
        self.hand_x = self.width // 2
        self.hand_y = self.height // 2
        # Smooth Cursor Logic
        self.target_hand_x = self.width // 2
        self.target_hand_y = self.height // 2
        
        self.thumb_index_touch = False
        self.prev_touch = False
        self.last_tap = 0
        
        # User
        self.current_user_id = None
        self.current_user_name = ""
        self.previous_user_id = None
        self.face_detected = False
        self.face_confidence = 0.0
        self.unknown_user_detected = None  # Track unknown users for "Add User" option
        self.user_profiles = {}
        if os.path.exists(USER_PROFILES_FILE):
            try:
                with open(USER_PROFILES_FILE) as f:
                    self.user_profiles = json.load(f)
            except: pass
        
        # Widgets
        self.widgets = []
        self.load_widgets(["clock", "weather"]) # Default
        self.dragging_widget = None

    def setup_background(self):
        self.bg_image = pygame.Surface((self.width, self.height))
        self.bg_image.fill((0,0,0))

    def load_widgets(self, widget_list, user_name=""):
        self.widgets = []
        x, y = 50, 50
        for name in widget_list:
            if name == "clock": self.widgets.append(ClockWidget(x, y, 400, 200))
            if name == "weather": self.widgets.append(WeatherWidget(x, y + 220, 300, 200))
            if name == "calendar": self.widgets.append(GoogleCalendarWidget(x + 320, y + 220, 400, 300, user_name))

    # --- Actions called by Menu ---
    def toggle_bg(self):
        self.show_background = not self.show_background

    def save_profile(self, user_id):
        widgets_data = [{"x": w.rect.x, "y": w.rect.y, "type": type(w).__name__} for w in self.widgets]
        self.user_profiles[user_id] = {"widgets": widgets_data}
        try:
            with open(USER_PROFILES_FILE, 'w') as f:
                json.dump(self.user_profiles, f)
        except: pass

    def load_profile(self, user_id):
        if user_id in self.user_profiles:
            profile = self.user_profiles[user_id]
            self.widgets = []
            user_name = self.current_user_name if self.current_user_name else ""
            for wd in profile.get('widgets', []):
                x, y = wd['x'], wd['y']
                if wd['type'] == 'ClockWidget':
                    self.widgets.append(ClockWidget(x, y, 400, 200))
                elif wd['type'] == 'WeatherWidget':
                    self.widgets.append(WeatherWidget(x, y, 300, 200))
                elif wd['type'] == 'GoogleCalendarWidget':
                    self.widgets.append(GoogleCalendarWidget(x, y, 400, 300, user_name))
        else:
            self.load_widgets(["clock", "weather"], self.current_user_name) # Default

    def add_widget(self, widget_type):
        # Find a good position for the new widget
        x, y = 50, 50
        for w in self.widgets:
            if w.rect.x + w.rect.w > x: x = w.rect.x + w.rect.w + 20
            if w.rect.y + w.rect.h > y: y = w.rect.y + w.rect.h + 20
        
        if widget_type == "clock":
            self.widgets.append(ClockWidget(x, y, 400, 200))
        elif widget_type == "weather":
            self.widgets.append(WeatherWidget(x, y, 300, 200))
        elif widget_type == "calendar":
            self.widgets.append(GoogleCalendarWidget(x, y, 400, 300, self.current_user_name))
        elif widget_type == "voice":
            self.widgets.append(VoiceAssistantWidget(x, y, 400, 250))

    def start_user_creation(self):
        # Callback when user types name and hits ENTER
        def on_name_entered(name):
            print(f"Creating User: {name}")

            # Show loading screen
            self.loading_screen.show("Scanning face... Please look at the camera", show_progress=True)

            # Start face capture in a separate thread
            import threading
            def capture_process():
                try:
                    # Stop camera pipeline
                    import subprocess
                    python_path = '/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python'
                    subprocess.run(['pkill', '-f', 'rpicam-vid'], check=False)
                    subprocess.run(['pkill', '-f', 'ffmpeg'], check=False)
                    time.sleep(2)  # Wait for cleanup

                    # Update progress
                    self.loading_screen.update_progress(0.1)

                    # Run face capture
                    self.loading_screen.message = "Capturing face images..."
                    subprocess.run([python_path, 'face_capture.py', name], check=True)

                    self.loading_screen.update_progress(0.7)
                    self.loading_screen.message = "Training recognition model..."

                    # Retrain the model
                    subprocess.run([python_path, 'face_train.py'], check=True)

                    self.loading_screen.update_progress(1.0)
                    self.loading_screen.message = "Setup complete!"

                    time.sleep(1)  # Show completion message

                    print(f"Face capture completed for {name}")
                    print("Model retrained")

                except subprocess.CalledProcessError as e:
                    print(f"Error during face capture or training: {e}")
                    self.loading_screen.message = "Error occurred. Please try again."
                    time.sleep(2)
                finally:
                    # Restart camera pipeline
                    subprocess.run(['./start_camera.sh'], check=False)
                    # Restart AI processes
                    subprocess.Popen([python_path, 'face_recognize.py'])
                    subprocess.Popen([python_path, 'recognize.py', '--cameraId', '11', '--frameWidth', '640', '--frameHeight', '480'])

                    # Hide loading screen
                    self.loading_screen.hide()

            # Start the capture process in background
            capture_thread = threading.Thread(target=capture_process, daemon=True)
            capture_thread.start()

        self.keyboard.open(on_name_entered)

    def delete_user(self, user_name):
        import shutil
        dataset_path = f'dataset/{user_name}'
        if os.path.exists(dataset_path):
            shutil.rmtree(dataset_path)
            print(f"Deleted user: {user_name}")

            # Retrain model
            import subprocess
            python_path = '/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python'
            try:
                subprocess.run([python_path, 'face_train.py'], check=True)
                print("Model retrained after deletion")

                # Restart face recognition process with updated model
                subprocess.run(['pkill', '-f', 'face_recognize.py'], check=False)
                time.sleep(1)  # Wait for process to stop
                subprocess.Popen([python_path, 'face_recognize.py'])

                print("Face recognition restarted with updated model")

                print("Face recognition restarted with updated model")

            except subprocess.CalledProcessError as e:
                print(f"Error retraining model: {e}")
        else:
            print(f"User {user_name} not found")

        # Refresh menu options after user deletion
        self.menu.users_options = self.menu.get_users_options()

    def auth_calendar(self, user_name):
        import subprocess
        python_path = '/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python'
        try:
            subprocess.run([python_path, 'calendar_auth.py', user_name], check=True)
            print(f"Calendar authentication completed for {user_name}")
        except subprocess.CalledProcessError as e:
            print(f"Error during calendar authentication: {e}")

    def toggle_calendar(self, user_name):
        """Enable or disable Google Calendar for a user."""
        import os
        token_file = f'google_auth/tokens/{user_name}_token.json'

        if os.path.exists(token_file):
            # Disable calendar - remove token
            os.remove(token_file)
            print(f"Google Calendar disabled for {user_name}")
            # Update any calendar widgets
            for w in self.widgets:
                if isinstance(w, GoogleCalendarWidget) and w.user_name == user_name:
                    w.events = []
                    w.needs_redraw = True
        else:
            # Enable calendar - run authentication
            self.auth_calendar(user_name)

    def reset_widgets(self, user_name):
        """Reset widget positions to default for a user."""
        if user_name in self.user_profiles:
            del self.user_profiles[user_name]
            try:
                with open(USER_PROFILES_FILE, 'w') as f:
                    json.dump(self.user_profiles, f)
            except:
                pass

        # Reload default widgets
        self.load_widgets(["clock", "weather", "calendar"], user_name)
        print(f"Widget positions reset for {user_name}")

    def add_unknown_user(self, detected_user_name):
        """Add a user that was detected but not recognized."""
        # Pre-fill the keyboard with the detected name
        def on_name_entered(name):
            # Use the entered name (allows user to correct if needed)
            self.start_user_creation_with_name(name)

        self.keyboard.open(on_name_entered, initial_text=detected_user_name)

    def start_user_creation_with_name(self, name):
        """Start user creation with a pre-filled name."""
        # This is similar to start_user_creation but skips the name entry
        print(f"Creating User: {name}")

        # Show loading screen
        self.loading_screen.show("Scanning face... Please look at the camera", show_progress=True)

        # Start face capture in a separate thread
        import threading
        def capture_process():
            try:
                # Stop camera pipeline
                import subprocess
                python_path = '/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python'
                subprocess.run(['pkill', '-f', 'rpicam-vid'], check=False)
                subprocess.run(['pkill', '-f', 'ffmpeg'], check=False)
                time.sleep(2)  # Wait for cleanup

                # Update progress
                self.loading_screen.update_progress(0.1)

                # Run face capture
                self.loading_screen.message = "Capturing face images..."
                subprocess.run([python_path, 'face_capture.py', name], check=True)

                self.loading_screen.update_progress(0.7)
                self.loading_screen.message = "Training recognition model..."

                # Retrain the model
                subprocess.run([python_path, 'face_train.py'], check=True)

                self.loading_screen.update_progress(1.0)
                self.loading_screen.message = "Setup complete!"

                time.sleep(1)  # Show completion message

                print(f"Face capture completed for {name}")
                print("Model retrained")

                # Clear the unknown user flag since we've added them
                self.unknown_user_detected = None

                # Refresh menu options to reflect the new user
                self.menu.users_options = self.menu.get_users_options()

            except subprocess.CalledProcessError as e:
                print(f"Error during face capture or training: {e}")
                self.loading_screen.message = "Error occurred. Please try again."
                time.sleep(2)
            finally:
                # Restart camera pipeline
                subprocess.run(['./start_camera.sh'], check=False)
                # Restart AI processes
                subprocess.Popen([python_path, 'face_recognize.py'])
                subprocess.Popen([python_path, 'recognize.py', '--cameraId', '11', '--frameWidth', '640', '--frameHeight', '480'])

                # Hide loading screen
                self.loading_screen.hide()

        # Start the capture process in background
        capture_thread = threading.Thread(target=capture_process, daemon=True)
        capture_thread.start()

    # --- Main Loop ---
    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); return

            self.update_inputs()

            # Render
            self.screen.fill(COLOR_BLACK)
            if self.show_background and self.bg_image:
                self.screen.blit(self.bg_image, (0,0))

            # Widgets
            for w in self.widgets:
                w.update(self.scroll_y)
                w.draw(self.screen, self.font_title, self.font_content, self.scroll_y)

            # Overlays (Menu / Keyboard / Loading)
            if self.menu.active:
                self.menu.draw(self.screen, (self.hand_x, self.hand_y))

            if self.keyboard.active:
                self.keyboard.draw(self.screen)

            if self.loading_screen.active:
                self.loading_screen.update()
                self.loading_screen.draw(self.screen)

            # Cursor
            self.draw_cursor()
            
            pygame.display.flip()
            self.clock.tick(60)

    def update_inputs(self):
        # Read /tmp/hand_data.json logic here (same as before)
        if os.path.exists(HAND_DATA_FILE):
            try:
                with open(HAND_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    
                    # Read Targets
                    raw_x = int(data.get('hand_center_x', 320) * self.width / 640)
                    raw_y = int(data.get('hand_center_y', 240) * self.height / 480)
                    
                    self.target_hand_x = raw_x 
                    self.target_hand_y = raw_y

                    self.thumb_index_touch = data.get('thumb_index_touch', False)
                    
                    if self.thumb_index_touch and not self.prev_touch:
                         self.handle_click()
                    
                    # Fix sticky widget bug: Cleanly release if touch ends
                    if not self.thumb_index_touch and self.prev_touch:
                         if self.dragging_widget:
                            self.dragging_widget.handle_drag_end(self.width, self.height)
                            self.dragging_widget = None

                    self.prev_touch = self.thumb_index_touch
                    
                    # Read face data
                    if os.path.exists(FACE_DATA_FILE):
                        try:
                            with open(FACE_DATA_FILE) as f:
                                fdata = json.load(f)
                                new_user_id = fdata.get('user_id')
                                self.face_detected = fdata.get('detected', False)
                                self.face_confidence = fdata.get('confidence', 0.0)

                                # Check if detected user exists in dataset
                                user_exists = False
                                if new_user_id and new_user_id != "unknown":
                                    dataset_path = f'dataset/{new_user_id}'
                                    user_exists = os.path.exists(dataset_path)
                                elif not self.face_detected:
                                    # No face detected, clear unknown user flag
                                    self.unknown_user_detected = None

                                if new_user_id != self.current_user_id:
                                    if self.current_user_id:
                                        self.save_profile(self.current_user_id)
                                    self.current_user_id = new_user_id
                                    self.current_user_name = fdata.get('user_name', '')

                                    if user_exists:
                                        # Known user - load their profile
                                        self.load_profile(self.current_user_id)
                                        self.unknown_user_detected = None  # Clear unknown user flag
                                        # Update calendar widgets with new user
                                        for w in self.widgets:
                                            if isinstance(w, GoogleCalendarWidget):
                                                w.user_name = self.current_user_name
                                                w.fetch_events()
                                                w.needs_redraw = True
                                    else:
                                        # Unknown user detected
                                        self.unknown_user_detected = new_user_id
                                        self.load_widgets(["clock", "weather"])  # Load defaults
                        except: pass
            except: pass
            
        # Smooth interpolation
        self.hand_x += (self.target_hand_x - self.hand_x) * 0.3
        self.hand_y += (self.target_hand_y - self.hand_y) * 0.3

        # Dragging logic
        if self.dragging_widget:
            self.dragging_widget.handle_drag_update(self.hand_x, self.hand_y, self.scroll_y)


    def handle_click(self):
        # Priority: Keyboard -> Menu -> Widgets
        if self.keyboard.active:
            if self.keyboard.handle_click(self.hand_x, self.hand_y): return
        
        if self.menu.active:
            if self.menu.handle_click(self.hand_x, self.hand_y): return
        
        # Double tap for menu
        if time.time() - self.last_tap < 0.5:
             self.menu.active = not self.menu.active
             self.last_tap = 0
             return
        self.last_tap = time.time()

        # Check for rename click on face status
        if self.current_user_id and self.current_user_id != "idle":
            dot_x = self.width - 20
            dot_y = 20
            if abs(self.hand_x - dot_x) < 50 and abs(self.hand_y - dot_y) < 20:
                def on_rename(name):
                    try:
                        with open(RENAME_REQUEST_FILE, 'w') as f:
                            json.dump({"user_id": self.current_user_id, "new_name": name}, f)
                    except: pass
                self.keyboard.open(on_rename, initial_text=self.current_user_name)
                return

        # Widgets - check for clicks first
        for w in reversed(self.widgets):
            if hasattr(w, 'handle_click') and w.handle_click(self.hand_x, self.hand_y, self.scroll_y):
                return  # Widget handled the click

        # Widgets - then check for drag
        for w in reversed(self.widgets):
            if w.handle_drag_start(self.hand_x, self.hand_y, self.scroll_y):
                self.dragging_widget = w
                self.widgets.remove(w); self.widgets.append(w)
                break
        
        if not self.dragging_widget and self.thumb_index_touch:
             # Stop dragging
             if self.dragging_widget:
                 self.dragging_widget.handle_drag_end(self.width, self.height)
                 self.dragging_widget = None

    def draw_cursor(self):
         color = COLOR_ACCENT if self.thumb_index_touch else COLOR_WHITE
         pygame.draw.circle(self.screen, color, (int(self.hand_x), int(self.hand_y)), 10, 2)
         pygame.draw.circle(self.screen, color, (int(self.hand_x), int(self.hand_y)), 4)
         
         # Draw Face Status Dot
         if not self.face_detected:
             dot_color = (255, 0, 0)  # Red if no face
         elif self.face_confidence < 0.5:
             dot_color = (255, 165, 0)  # Orange if low confidence
         else:
             dot_color = (0, 255, 0)  # Green if high confidence
         
         pygame.draw.circle(self.screen, dot_color, (self.width - 20, 20), 5)
         
         # Display user name/ID only if high confidence
         if self.face_detected and self.face_confidence >= 0.5 and self.current_user_id and self.current_user_id != "idle":
             display_text = self.current_user_name if self.current_user_name else self.current_user_id
             if self.current_user_name and self.current_user_name != "default_user":
                 display_text += f" ({self.current_user_id})"
             else:
                 display_text = self.current_user_id
             
             name_lbl = self.font_title.render(display_text, True, dot_color)
             self.screen.blit(name_lbl, (self.width - 30 - name_lbl.get_width(), 12))

if __name__ == '__main__':
    app = SmartMirrorPro()
    app.run()
