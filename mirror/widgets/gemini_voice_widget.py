# widgets/gemini_voice_widget.py
# Gemini Live API voice interaction widget

import pygame
import asyncio
import threading
import queue
import time
from .base_widget import Widget
from utils.fonts import get_font
from config import *
import os

class GeminiVoiceWidget(Widget):
    """Widget for voice interaction with Gemini Live API."""

    def __init__(self, x, y, w, h):
        """Initialize the Gemini voice widget.

        Args:
            x, y: Position coordinates
            w, h: Width and height
        """
        super().__init__(x, y, w, h, "Gemini Voice")
        self.font_status = get_font(24)
        self.font_message = get_font(18)

        # Voice interaction state
        self.is_listening = False
        self.is_speaking = False
        self.status_text = "Ready"
        self.last_message = ""
        self.conversation_history = []

        # Audio handling
        self.audio_queue = queue.Queue()
        self.response_queue = queue.Queue()

        # Gemini Live API connection
        self.gemini_thread = None
        self.running = False

        # Check if Google Cloud project is configured
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT', '')
        self.api_available = bool(self.project_id)

        if not self.api_available:
            self.status_text = "Configure GOOGLE_CLOUD_PROJECT"

    def start_voice_session(self):
        """Start the Gemini Live API voice session."""
        if not self.api_available:
            self.status_text = "Google Cloud project not configured"
            return

        if self.running:
            return

        self.running = True
        self.status_text = "Connecting..."
        self.gemini_thread = threading.Thread(target=self._run_gemini_session, daemon=True)
        self.gemini_thread.start()

    def stop_voice_session(self):
        """Stop the Gemini Live API voice session."""
        self.running = False
        self.status_text = "Disconnected"
        self.is_listening = False
        self.is_speaking = False

    def _run_gemini_session(self):
        """Run the Gemini Live API session in a separate thread."""
        try:
            from google import genai

            # Initialize the client
            client = genai.Client()

            # Configure the session
            config = genai.LiveConnectConfig(
                generation_config=genai.GenerationConfig(
                    temperature=0.8,
                    response_modalities=['text', 'audio'],
                ),
                speech_config=genai.SpeechConfig(
                    voice_config=genai.VoiceConfig(
                        prebuilt_voice_config=genai.PrebuiltVoiceConfig(
                            voice_name='Puck',
                        ),
                    ),
                ),
            )

            self.status_text = "Connected"

            # Start the live session
            with client.aio.live.connect(model='gemini-2.0-flash-exp', config=config) as session:
                # Set up audio input/output tasks
                tasks = []

                # Audio input task (would need actual audio capture)
                # For now, we'll simulate text input
                tasks.append(self._handle_text_input(session))

                # Audio output task
                tasks.append(self._handle_audio_output(session))

                # Run all tasks
                asyncio.run(asyncio.gather(*tasks))

        except Exception as e:
            print(f"Gemini session error: {e}")
            self.status_text = f"Error: {str(e)[:20]}..."
            self.running = False

    async def _handle_text_input(self, session):
        """Handle text input to Gemini (placeholder for voice input)."""
        while self.running:
            try:
                # For now, we'll use text input instead of voice
                # In a full implementation, this would capture audio
                if not self.audio_queue.empty():
                    text = self.audio_queue.get()
                    await session.send(text, end_of_turn=True)
                    self.status_text = "Processing..."
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Text input error: {e}")
                break

    async def _handle_audio_output(self, session):
        """Handle audio output from Gemini."""
        try:
            while self.running:
                async for response in session.listen():
                    if not self.running:
                        break

                    if response.text:
                        self.last_message = response.text
                        self.conversation_history.append(f"Gemini: {response.text}")
                        if len(self.conversation_history) > 5:
                            self.conversation_history.pop(0)
                        self.status_text = "Speaking..."
                        self.is_speaking = True
                        self.needs_redraw = True

                    if response.audio:
                        # In a full implementation, this would play the audio
                        # For now, we'll just indicate audio is available
                        self.status_text = "Playing audio..."
                        await asyncio.sleep(0.5)  # Simulate audio playback time

                    if response.audio_done:
                        self.is_speaking = False
                        self.status_text = "Ready"
                        self.needs_redraw = True

        except Exception as e:
            print(f"Audio output error: {e}")
            self.running = False

    def send_text_message(self, message):
        """Send a text message to Gemini."""
        if self.running:
            self.audio_queue.put(message)
            self.conversation_history.append(f"You: {message}")
            if len(self.conversation_history) > 5:
                self.conversation_history.pop(0)
            self.status_text = "Sending..."
            self.needs_redraw = True

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
        status_color = COLOR_WHITE if self.api_available else COLOR_RED
        status_surf = self.font_status.render(self.status_text, True, status_color)
        self.content_surface.blit(status_surf, (0, y_offset))
        y_offset += 35

        # Connection indicator
        if self.running:
            indicator_color = (0, 255, 0) if not self.is_speaking else (255, 255, 0)
            pygame.draw.circle(self.content_surface, indicator_color, (10, y_offset - 10), 5)
            indicator_text = "Connected" if not self.is_speaking else "Speaking"
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
        if not self.running and self.api_available:
            instr_surf = self.font_message.render("Tap to start voice session", True, COLOR_TEXT_DIM)
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
