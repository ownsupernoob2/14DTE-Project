#!/usr/bin/env python3
"""
Google Calendar Authentication Script for Smart Mirror Users

This script handles OAuth authentication for Google Calendar API for each user.
Run this script for each user to authenticate their Google account.

Usage: python calendar_auth.py <user_name>
"""

import sys
import os
from google_calendar import get_credentials

def main():
    if len(sys.argv) != 2:
        print("Usage: python calendar_auth.py <user_name>")
        sys.exit(1)

    user_name = sys.argv[1]
    print(f"Authenticating Google Calendar for user: {user_name}")
    print("This will start a local web server on port 8080.")
    print("If you're on a headless Raspberry Pi:")
    print("1. Copy the authorization URL that appears below")
    print("2. Open it on any device with a browser (phone, computer, etc.)")
    print("3. Sign in with the Google account for this user")
    print("4. Grant permission for Calendar access")
    print("5. The browser will redirect to localhost:8080 - this is normal")
    print("6. Return to this terminal - authentication should complete automatically")
    print()

    try:
        creds = get_credentials(user_name)
        print(f"Authentication successful for {user_name}!")
        print("You can now use the Google Calendar widget for this user.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
