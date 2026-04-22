#!/home/raspi/.pyenv/versions/3.10.7/envs/mediapipe/bin/python3
import os
import json
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CREDENTIALS_FILE = 'google_auth/credentials.json'
TOKEN_DIR = 'google_auth/tokens'

def get_credentials(user_name):
    """Get OAuth2 credentials for a user."""
    if not os.path.exists(TOKEN_DIR):
        os.makedirs(TOKEN_DIR)
    
    token_file = os.path.join(TOKEN_DIR, f'{user_name}_token.json')
    
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # For headless Raspberry Pi, use local server (will prompt for URL)
            creds = flow.run_local_server(port=8080)
        
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    
    return creds

def get_calendar_events(user_name, max_results=10):
    """Fetch upcoming calendar events for a user."""
    try:
        creds = get_credentials(user_name)
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        return events
    except Exception as e:
        print(f"Error fetching calendar for {user_name}: {e}")
        return []

if __name__ == "__main__":
    # Test with a user
    events = get_calendar_events("john")
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(f"{start}: {event['summary']}")
