# Connecting KAMAR to the Smart Mirror (timetables only)

## Overview

This connects the school's KAMAR to the Smart Mirror server using KAMAR **Directory Services**, so the mirror can show a student's timetable from their student ID without each student pasting in their calendar link.

It is read-only by design. KAMAR *pushes* data to our server; our server never logs in to KAMAR and has no way to change anything in it. We ask KAMAR for **student timetables only**, nothing else: no names, addresses, caregivers, photos, attendance or results.

Official reference: <https://directoryservices.kamar.nz/>

---

## Part A — Instructions for the school's KAMAR administrator

### Step 1: Open Directory Services

Log into KAMAR and go to **Setup > Server**, then **Directory Services**, then click **New Service**.

### Step 2: Enter the connection details

| Setting | Value |
| --- | --- |
| Address | `https://api.smartmirror.me/api/kamar` |
| Port | 443 |
| Timeout | 30 seconds |
| Format | JSON |
| Username and Password | Supplied by the Smart Mirror team (sent separately, never by email in plain text) |
| Part Updates | Ticked ✓ |
| Full Update | Any time between 7pm and 7am, all 7 days ticked |

### Step 3: Check and Enable

Click **Check and Enable**. KAMAR will contact the server, which replies with exactly what it is asking for. You should see:

- **Timetables** (students) available and ticked
- **Calendars as ICS** ticked
- Everything else (details, photos, groups, attendance, assessments, pastoral, staff, notices, etc.) **unavailable**

Leave the defaults as they are. If anything other than student timetables shows as available, stop and contact us.

### Step 4: Confirm data has arrived

After the next full update (overnight), let us know and we'll confirm timetables are showing on the mirror.

### To turn it off

Untick or delete the service in **Setup > Server > Directory Services**. We'll then delete the stored timetables (see Part C).

---

## Part B — How the server handles it

KAMAR only pushes; there is no "look up student X" call into KAMAR. The server keeps what KAMAR sends and answers the mirror from that. Code: `server/kamar.go`.

### 1. `POST /api/kamar` (KAMAR → server)

**Login.** KAMAR sends `Authorization: Basic …` with the username and password from the server's `.env` (`KAMAR_DS_USERNAME`, `KAMAR_DS_PASSWORD`). Anything else gets:

```
HTTP 403
{"SMSDirectoryData": {"error": 403, "result": "Authentication Failed"}}
```

KAMAR deliberately tries wrong passwords during setup and in its daily check, and would disable the service if we accepted them. While either setting is blank, the route refuses everything.

**Messages**, by their `sync` value:

- **`check`**: sent on *Check and Enable* and every day between 4am and 5am. The reply is what limits the access. It asks for student timetables as ICS calendars and nothing else:

  ```json
  {"SMSDirectoryData": {
    "error": 0, "result": "OK",
    "service": "Smart Mirror", "version": 1.0, "status": "Ready",
    "infourl": "https://smartmirror.me/privacy",
    "privacystatement": "Stores each student's timetable only, keyed by their student ID, on a server in New Zealand.|Used only to show a student their own timetable on the Smart Mirror after they scan their ID card.|Deleted 30 days after KAMAR stops sending it (the student leaves or the service is turned off).",
    "countryDataStored": "New Zealand",
    "options": {"ics": true, "students": {"details": false, "timetables": true}}
  }}
  ```

  Changing these options later disables the service at the school until they accept the change.

- **`studenttimetables`**: the data. Each entry is `{"id": …, "grid": "2026TT", "timetable": "BEGIN:VCALENDAR…"}`. The server saves each calendar in the `kamar_timetables` table under the student ID, normalised the same way as a scanned card (upper case, no spaces). A student's new timetable replaces their old one.

- **Anything else**: answered "OK" and thrown away. An error reply would make KAMAR retry and eventually disable the service.

**Retention.** KAMAR re-sends every timetable each night, so any timetable not refreshed for 30 days (the student left, or the service was turned off) is deleted on the next push.

### 2. Scanning a card at the mirror

1. The mirror sends the scanned ID to `/api/verify-barcode`, as it already does.
2. **The student has an account with that ID linked:** they sign in as themselves, with their own layout.
3. **No account, but KAMAR sent a timetable for that ID:** they sign in as `kamar|<ID>`, with no name and the default layout. All that's personal on screen is their timetable.
4. **Neither:** "ID Not Recognised", as before.
5. The mirror then asks `/api/timetable` for that user. The server uses the KAMAR timetable for their student ID if there is one, otherwise the student's own calendar link.

Both routes need the mirror key, and `/api/verify-barcode` is rate limited, so student IDs can't be tried in bulk from outside.

### Credentials

- Set `KAMAR_DS_USERNAME` and `KAMAR_DS_PASSWORD` in the server's `.env` to long random values, then restart the server. Never put them in the repo.
- Give them to the school's KAMAR admin in person or through a password-sharing link, not in a plain email.

---

## Part C — Privacy and paperwork

KAMAR requires a Memorandum of Understanding with the school before sending data. It should cover:

- **What:** student timetables only (class code, teacher code, room, times), keyed by KAMAR student ID.
- **Why:** to show a student their own timetable on the Smart Mirror after they sign in.
- **Where:** the server's location (must match `countryDataStored`).
- **Security:** HTTPS only, Basic auth on the listener, timetables only readable by a signed-in student or a registered mirror.
- **Retention:** overwritten on each update; deleted within 30 days of the service being turned off or the student leaving.
- **Breaches:** we tell the school straight away, and the Privacy Commissioner if required (Privacy Act 2020).

---

## Things to confirm with the school

- That the KAMAR ID number (`id`) is the same number printed on the student ID card barcode. If not, we'll need `uniqueid` or `nsn` added as a field.
