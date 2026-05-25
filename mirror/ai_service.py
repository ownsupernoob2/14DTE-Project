import os
import time
import json
import speech_recognition as sr
from contextlib import contextmanager
from ctypes import *

import google.generativeai as genai

from gtts import gTTS
import pygame

# --- CONFIGURATION ---
MIC_DEVICE_INDEX = None
API_KEY =  "AIzaSyC5f92F6Fz_MI1IKo-uciFgzAC16Wzp6UY"
AI_STATUS_FILE = '/tmp/ai_status.json'
AI_CONTROL_FILE = '/tmp/ai_control.json'

# --- ALSA silence hack ---
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def no_alsa_error():
    asound = None
    try:
        asound = cdll.LoadLibrary("libasound.so")
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
    finally:
        if asound:
            asound.snd_lib_error_set_handler(None)

# --- AI SETUP ---
genai.configure(api_key=API_KEY)
client = genai.GenerativeModel("gemini-2.0-flash")

def set_ai_state(state):
    data = {'state': state}
    with open(AI_STATUS_FILE, 'w') as f:
        json.dump(data, f)

def is_ai_active():
    if os.path.exists(AI_CONTROL_FILE):
        try:
            with open(AI_CONTROL_FILE, 'r') as f:
                data = json.load(f)
                return data.get('active', False)
        except:
            return False
    return False

def speak(text):
    print(f"AI: {text}")
    try:
        tts = gTTS(text=text, lang="en")
        tts.save("response.mp3")
        pygame.mixer.init()
        pygame.mixer.music.load("response.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.quit()
        os.remove("response.mp3")
    except Exception as e:
        print(f"Audio Error: {e}")

def listen():
    r = sr.Recognizer()
    with no_alsa_error():
        with sr.Microphone(device_index=MIC_DEVICE_INDEX) as source:
            print("Adjusting for noise...")
            r.adjust_for_ambient_noise(source, duration=1)
            print("Listening...")
            try:
                audio = r.listen(source, timeout=5, phrase_time_limit=8)
                text = r.recognize_google(audio)
                print(f"You said: {text}")
                return text
            except Exception as e:
                print(f"Speech Error: {e}")
                return None

def generate_ai_response(prompt: str) -> str:
    try:
        response = client.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"API Error: {e}")
        return "Sorry, I couldn't process that."

def main():
    print("AI mirror started.")
    
    # Quick test - Commented out to save quota on startup
    # test_resp = generate_ai_response("Say System Online.")
    # print("Test:", test_resp)

    while True:
        if not is_ai_active():
            set_ai_state('idle')
            time.sleep(1)
            continue
        
        set_ai_state('listening')
        text = listen()
        
        if text and "mirror" in text.lower():
            set_ai_state('thinking')
            user_prompt = text.lower().replace("mirror", "").strip()
            reply = user_prompt  # Repeat what user said
            set_ai_state('speaking')
            speak(reply)
            set_ai_state('idle')
        else:
            set_ai_state('idle')

if __name__ == "__main__":
    main()
