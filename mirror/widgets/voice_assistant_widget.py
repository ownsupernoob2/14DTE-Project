# widgets/voice_assistant_widget.py
# Free voice-only assistant widget using local TTS/STT and Ollama

import pygame
import threading
import queue
import time
try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import pyttsx3
    _PYTTSX3_AVAILABLE = True
except ImportError:
    pyttsx3 = None
    _PYTTSX3_AVAILABLE = False

from .base_widget import Widget
from utils.fonts import get_font
from config import *
import subprocess
import json

class VoiceAssistantWidget(Widget):
    """Free voice-only assistant widget using local TTS/STT and Ollama."""

    def __init__(self, x, y, w, h):
        """Initialize the voice assistant widget.

        Args:
            x, y: Position coordinates
            w, h: Width and height
        """
        super().__init__(x, y, w, h, "Voice Assistant")
        self.font_status = get_font(24)
        self.font_message = get_font(18)

        # Voice interaction state
        self.is_listening = False
        self.is_speaking = False
        self.status_text = "Ready"
        self.last_message = ""
        self.conversation_history = []

        # Audio components
        self.recognizer = sr.Recognizer() if sr is not None else None
        if _PYTTSX3_AVAILABLE:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 180)  # Speed up speech
            self.tts_engine.setProperty('volume', 0.8)  # Volume
        else:
            self.tts_engine = None

        # Queues for thread communication
        self.audio_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Threads
        self.listen_thread = None
        self.speak_thread = None
        self.llm_thread = None
        self.running = False

        # Check if Ollama is available
        self.ollama_available = self._check_ollama()

    def _check_ollama(self):
        """Check if Ollama is installed and running."""
        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def start_voice_session(self):
        """Start the voice assistant session."""
        if self.running:
            return

        if not _PYTTSX3_AVAILABLE:
            self.status_text = "Voice assistant unavailable (pyttsx3 not installed)"
            return

        if not self.ollama_available:
            self.status_text = "Install Ollama first: curl -fsSL https://ollama.ai/install.sh | sh"
            return

        self.running = True
        self.status_text = "Starting..."
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.speak_thread = threading.Thread(target=self._speak_loop, daemon=True)
        self.llm_thread = threading.Thread(target=self._llm_loop, daemon=True)

        self.listen_thread.start()
        self.speak_thread.start()
        self.llm_thread.start()

    def stop_voice_session(self):
        """Stop the voice assistant session."""
        self.running = False
        self.status_text = "Stopped"
        self.is_listening = False
        self.is_speaking = False

        # Stop TTS if speaking
        try:
            if self.tts_engine is not None:
                self.tts_engine.stop()
        except:
            pass

    def _listen_loop(self):
        """Continuously listen for voice input."""
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.status_text = "Listening..."

                while self.running:
                    try:
                        self.is_listening = True
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                        self.is_listening = False

                        if not self.running:
                            break

                        # Recognize speech
                        text = self.recognizer.recognize_google(audio)
                        if text:
                            print(f"Heard: {text}")
                            self.conversation_history.append(f"You: {text}")
                            if len(self.conversation_history) > 5:
                                self.conversation_history.pop(0)
                            self.audio_queue.put(text)
                            self.status_text = "Processing..."
                            self.needs_redraw = True

                    except sr.WaitTimeoutError:
                        # Timeout is normal, continue listening
                        pass
                    except sr.UnknownValueError:
                        self.status_text = "Didn't understand"
                        time.sleep(1)
                        self.status_text = "Listening..."
                    except sr.RequestError as e:
                        self.status_text = f"Speech service error: {e}"
                        time.sleep(2)
                        self.status_text = "Listening..."

        except Exception as e:
            print(f"Listen loop error: {e}")
            self.status_text = f"Microphone error: {str(e)[:20]}..."
            self.running = False

    def _speak_loop(self):
        """Handle text-to-speech output."""
        while self.running:
            try:
                if not self.response_queue.empty():
                    text = self.response_queue.get()
                    self.is_speaking = True
                    self.status_text = "Speaking..."
                    self.needs_redraw = True

                    # Speak the text
                    if self.tts_engine is not None:
                        self.tts_engine.say(text)
                        self.tts_engine.runAndWait()

                    self.is_speaking = False
                    self.status_text = "Listening..."
                    self.needs_redraw = True

                time.sleep(0.1)
            except Exception as e:
                print(f"Speak loop error: {e}")
                self.is_speaking = False
                self.status_text = "TTS Error"
                time.sleep(1)

    def _llm_loop(self):
        """Handle LLM conversation processing."""
        while self.running:
            try:
                if not self.audio_queue.empty():
                    user_text = self.audio_queue.get()

                    # Get response from Ollama
                    response = self._query_ollama(user_text)
                    if response:
                        self.last_message = response
                        self.conversation_history.append(f"Assistant: {response}")
                        if len(self.conversation_history) > 5:
                            self.conversation_history.pop(0)
                        self.response_queue.put(response)
                        self.needs_redraw = True

                time.sleep(0.1)
            except Exception as e:
                print(f"LLM loop error: {e}")
                error_msg = "Sorry, I encountered an error processing your request."
                self.response_queue.put(error_msg)

    def _query_ollama(self, prompt):
        """Query Ollama for a response."""
        try:
            # Use a small, fast model like llama2:7b or mistral
            cmd = [
                'ollama', 'run', 'llama2:7b',
                '--format', 'json',
                '-p', f"User: {prompt}\nAssistant: Keep your response under 50 words and be helpful."
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse the response
                response_text = result.stdout.strip()
                # Clean up the response
                if "Assistant:" in response_text:
                    response_text = response_text.split("Assistant:")[-1].strip()
                return response_text[:100]  # Limit response length
            else:
                print(f"Ollama error: {result.stderr}")
                return "Sorry, I'm having trouble connecting to my brain right now."

        except subprocess.TimeoutExpired:
            return "That took too long to think about. Try asking something simpler."
        except Exception as e:
            print(f"Ollama query error: {e}")
            return "I encountered an error. Please try again."

    def update(self, scroll_y=0):
        """Update the widget."""
        super().update(scroll_y)

        # Check if content needs updating
        if self.needs_redraw:
            self._update_content_surface()

    def _update_content_surface(self):
        """Update the content surface with current status and conversation."""
        content_height = 200
        self.content_surface = pygame.Surface((self.rect.w - 40, content_height), pygame.SRCALPHA)

        y_offset = 0

        # Status text
        status_color = COLOR_WHITE if self.ollama_available else COLOR_RED
        status_surf = self.font_status.render(self.status_text, True, status_color)
        self.content_surface.blit(status_surf, (0, y_offset))
        y_offset += 35

        # Connection indicator
        if self.running:
            indicator_color = (0, 255, 0) if not self.is_speaking else (255, 255, 0)
            pygame.draw.circle(self.content_surface, indicator_color, (10, y_offset - 10), 5)
            indicator_text = "Active" if not self.is_speaking else "Speaking"
            indicator_surf = self.font_message.render(indicator_text, True, COLOR_TEXT_DIM)
            self.content_surface.blit(indicator_surf, (25, y_offset - 20))
            y_offset += 25

        # Recent conversation
        for message in self.conversation_history[-3:]:  # Show last 3 messages
            # Truncate long messages
            if len(message) > 30:
                message = message[:27] + "..."

            msg_surf = self.font_message.render(message, True, COLOR_TEXT_DIM)
            self.content_surface.blit(msg_surf, (0, y_offset))
            y_offset += 22

        # Instructions
        if not self.running and self.ollama_available:
            instr_surf = self.font_message.render("Tap to start voice assistant", True, COLOR_TEXT_DIM)
            self.content_surface.blit(instr_surf, (0, y_offset))

    def draw(self, surface, font_title, font_content, scroll_y=0):
        """Draw the widget."""
        super().draw(surface, font_title, font_content, scroll_y)

    def handle_click(self, x, y, scroll_y=0):
        """Handle click events on the widget."""
        adj_y = y + scroll_y
        if self.rect.collidepoint(x, adj_y):
            if self.running:
                self.stop_voice_session()
            else:
                self.start_voice_session()
            return True
        return False
