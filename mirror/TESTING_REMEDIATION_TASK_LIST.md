# Day 1 Testing Remediation & Updated A/B Experimentation Plan

> **NCEA Level 3 / Year 14 DTE Smart Mirror Project**  
> **Evaluation Period:** October 2026  
> **Source:** Real-World Student Testing Feedback (Kevin, Austin, Eros, Omar, Kartik, Edward, Nico)

---

## 1. Executive Summary & Root Cause Matrix

The first day of real-world mirror testing produced invaluable empirical findings. The failures and confusion experienced by users fall into four distinct layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. OPTICAL & PHYSICAL LAYER                                            │
│    • Direct window backlight → Camera silhouette → Vision failure      │
│    • Two-way mirror 25% transmission → Washed-out screen in daylight   │
│    • Barcode slot recess → Partial beam truncation → Read errors       │
├────────────────────────────────────────────────────────────────────────┤
│ 2. COGNITIVE / MENTAL MODEL LAYER                                      │
│    • Screen on glass → Touchscreen expectation → Users tap surface     │
│    • No visual hand cursor → Zero feedback on whether hands are seen   │
│    • Pinch-to-scroll counter-intuitive → Users naturally wave / swipe  │
├────────────────────────────────────────────────────────────────────────┤
│ 3. IDENTITY & BIOMETRIC LAYER                                          │
│    • Face training 500 error → Server Python/dlib environment glitch   │
│    • Unbound face scans → Risk of account hijacking / face collision   │
│    • Telemetry race condition → Barcode logins mislogged as face scans │
├────────────────────────────────────────────────────────────────────────┤
│ 4. WEB PLATFORM & APPLICATION LAYER                                    │
│    • Dashboard timetable button dead link (`showSetup` logic bug)      │
│    • No Kamar ICS export instructions with screenshots                 │
│    • Unclickable notice cards → No summary / detail expansion          │
│    • Theme & language settings are non-functional dummy controls       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Master Remediation Task List (Ranked by Priority)

### Priority P0: Critical Blockers (Must Fix Before Friday Testing)

#### P0-1. Fix Face Training 500 Error (`POST /api/faces/train`)
* **Problem:** Web face enrollment crashes with HTTP 500: `Failed to load resource: the server responded with a status of 500 (api.smartmirror.me/api/faces/train:1)`.
* **Root Cause:** In `server/handlers_face.go`, `getPythonCmd()` runs `python3` or `python`. On the Linux host/VM, `face_recognition` and `dlib` reside inside a Python virtual environment (`venv/bin/python`). Running system Python throws `ModuleNotFoundError`. Additionally, `stderr` was not being relayed to the response JSON.
* **Actionable Fix:**
  1. Update `getPythonCmd()` to probe `venv/bin/python`, `.venv/bin/python`, or `$PYTHON_BIN`.
  2. Capture `errOut.String()` and return descriptive errors (e.g., *"No face detected in frames — ensure good lighting"*).
  3. Ensure `encodings/` directory exists and has `0755` write permissions.

#### P0-2. Physical Mirror Relocation (Window Backlight & Silhouette Fix)
* **Problem:** Mirror is placed directly facing an outdoor window. Background daylight (10,000+ lux) crushes user faces into dark silhouettes (200 lux). Increasing exposure causes extreme bloom, hair wash-out, and reflections off the two-way glass.
* **Root Cause:** Computer vision (MediaPipe and dlib) requires feature contrast. Silhouettes cannot be tracked.
* **Actionable Fix (Austin's recommendation):**
  1. Move the mirror to a shaded corridor wall or perpendicular to windows.
  2. Ensure ambient light falls onto the user's *front*, not into the camera lens.
  3. Maximize display brightness and contrast to 100% on monitor hardware controls (Eros's fix).

#### P0-3. Fix Dashboard Timetable Redirect Dead Link
* **Problem:** Clicking "Configure Calendar Link" on the web dashboard does nothing (`Fix that bruh`).
* **Root Cause:** In `web/src/components/TimetableWidget.jsx` line 321:
  ```jsx
  // Inside: if (showSetup) { if (readonly) { ... } }
  <button onClick={() => setShowSetup(true)}>Configure Calendar Link</button>
  ```
  `showSetup` is already true, so clicking `setShowSetup(true)` does nothing.
* **Actionable Fix:** Replace `onClick={() => setShowSetup(true)}` with `navigate('/timetable')` or trigger the setup modal directly.

#### P0-4. Fix Barcode Telemetry Attribution Race Condition
* **Problem:** Barcode scans were recorded in analytics as face scans.
* **Root Cause:** In `mirror/smart_mirror_pro.py`, face detection triggers first upon user approach, setting state to `guest`/`user` and defaulting `auth_method` to `'face'`. When the barcode is verified 1 second later, the active telemetry session does not update its `auth_method`.
* **Actionable Fix:** In `_on_barcode_verified()`, explicitly call `self.telemetry.current_session['auth_method'] = 'barcode'` or start a dedicated barcode session.

---

### Priority P1: Core HCI, Gestures & Biometrics

#### P1-1. Real-Time On-Screen Hand Tracking Cursor (Omar & Edward's Request)
* **Problem:** Users have no idea if the mirror detects their hand, where it is pointing, or why an action failed.
* **Actionable Fix:**
  1. Read smoothed palm coordinates $(x, y)$ from `gesture_engine.py` (published to `gesture_status.json`).
  2. Render a glowing 24px circular dot or hand avatar on the PySide6 mirror overlay corresponding to normalized coordinates:
     $$\text{screen\_x} = (1.0 - \text{hand\_x}) \times \text{screen\_w}, \quad \text{screen\_y} = \text{hand\_y} \times \text{screen\_h}$$
  3. Change cursor color when pinching/active (e.g., cyan `#4fc3ff` for hover, emerald `#22c55e` for active).

#### P1-2. Support Open-Palm Wave / Swipe Scrolling (Edward & Nico's Discovery)
* **Problem:** Users instinctively wave or flick their hand down to scroll; they do not naturally pinch thumb and index finger together in mid-air.
* **Actionable Fix:**
  1. In `gesture_engine.py`, add a vertical velocity detector for **open palms** (`is_extended_fingers >= 3`):
     $$\Delta y = y_{\text{current}} - y_{\text{previous}}, \quad v_y = \frac{\Delta y}{\Delta t}$$
  2. If $|v_y| > \text{threshold}$, generate smooth scroll ticks in the direction of the swipe without requiring a pinch.
  3. Retain pinch-and-drag for precision inspection.

#### P1-3. Anti-Touchscreen Tutorial Video & Visual Warning (The ❌ & ✔️ Graphic)
* **Problem:** Students instinctively touch the glass thinking it is an iPad or fast-food touchscreen.
* **Actionable Fix:**
  1. Update tutorial intro with an animated graphic:
     * A hand touching the glass with a large glowing red **❌ ("INERT GLASS — DO NOT TOUCH")**.
     * A hand moving 30 cm away in the air with a glowing green **✔️ ("MOVE HAND IN THE AIR")**.
  2. Allow any gesture made during tutorial playback to instantly dismiss the demo and execute the action immediately without lag.

#### P1-4. Require Barcode ID Before Face Registration
* **Problem:** Users can attempt to register faces without verified student identity, and face recognition can occasionally misidentify students in poor lighting.
* **Actionable Fix:**
  1. On the web portal, lock the "Face Registration" card until the student successfully links their Student Barcode ID.
  2. On the mirror: If face confidence is borderline ($0.45 \le c < 0.60$), prompt:  
     `"Unsure match — please scan your Student ID barcode to confirm."`

#### P1-5. Face Collision Detection & Admin Traceability
* **Problem:** What happens if a student attempts to register someone else's face, or a face is registered twice?
* **Actionable Fix:**
  1. Before saving a new face encoding in `server/train.py`, calculate the Euclidean distance against all existing `.pickle` files in `encodings/`.
  2. If $\min(\text{distance}) < 0.40$ (matching an existing student `user_B`):
     * Abort registration with HTTP 409 Conflict:  
       `"This face is already registered to a student account. If this is an error, contact marminamina3@gmail.com."`
     * Append record to `data/face_collision_log.json` with timestamp, IP, new user ID, and matched user ID so the admin can trace the attempt.

---

### Priority P2: Web Experience & Information Quality

#### P2-1. Step-by-Step King's High KAMAR ICS Guide with Screenshots
* **Problem:** Users do not know how or where to obtain their `.ics` timetable URL.
* **Actionable Fix:**
  1. Build a modal in `TimetableWidget.jsx` with four clear steps and visual diagrams:
     * **Step 1:** Log in to `kingshigh.school.kiwi`.
     * **Step 2:** Open the **Timetable** tab.
     * **Step 3:** Click **"Subscribe / Export iCal Feed"** at the bottom.
     * **Step 4:** Copy the URL ending in `.ics` and paste it into the mirror web app.
  2. Validate that the URL strictly matches `https://kingshigh.school.kiwi/ics/...`.

#### P2-2. Interactive Notice Cards & Key Details Summary (Web & Mirror)
* **Problem:** Users click on notices to read the full content, but cards are inert. Users requested a summary of key details.
* **Actionable Fix:**
  1. In `DailyNoticesWidget.jsx`, add an `onClick={() => setSelectedNotice(n)}` modal.
  2. In the modal, show full notice body plus an auto-extracted **Quick Brief Box**:
     * 📍 **Location:** (e.g., *Auditorium / Gym*)
     * ⏰ **Time / Bell:** (e.g., *12:45 PM Lunchtime*)
     * 👤 **Staff Contact:** (e.g., *Mr. Smith*)
     * ⚠️ **Deadline / Year Group:** (e.g., *Year 12 & 13 only*)
  3. Enable opening this modal on the mirror via gesture tap.

#### P2-3. Post-Signup Onboarding Wizard
* **Problem:** New users don't know where to go or what to do after signing up.
* **Actionable Fix:**
  1. Show a 3-step checklist banner on first login:
     * 1️⃣ Connect Timetable (`.ics` URL)
     * 2️⃣ Link Student ID Barcode
     * 3️⃣ Register Face Scan
  2. Progress bar (`0%`, `33%`, `66%`, `100%`) guiding students to full mirror readiness.

#### P2-4. Fix Notices "Apply Changes" & Timetable Customization UI
* **Problem:** In notices, clicking "APPLY" provides no visual feedback. In timetable, customization is limited.
* **Actionable Fix:**
  1. Add an animated success toast: `"✓ Settings Applied & Synced to Mirror"`.
  2. In timetable view, allow students to toggle custom display preferences (e.g., hide completed classes, highlight study periods).

#### P2-5. Interval & Lunch Bell Indicators on Mirror Timetable
* **Problem:** During Interval (10:30–10:50 AM) and Lunch (12:45–1:30 PM), the mirror shows "No Active Class", which looks broken.
* **Actionable Fix:** Add dedicated schedule blocks for school breaks:
  * **10:30–10:50 AM:** `"INTERVAL — Recess (Next: Period 3 at 10:50 AM)"`
  * **12:45–1:30 PM:** `"LUNCH — Lunchtime (Next: Period 5 at 1:30 PM)"`

---

### Priority P3: School Integrations & Hardware Polish

#### P3-1. Library Books Integration (Overdue & Borrowed)
* **Problem:** Students want to see borrowed and overdue books on their dashboard.
* **Actionable Fix:** Add a "Library" card displaying current loans and due dates, with warning badges for overdue items.

#### P3-2. Working Themes & Clean Settings
* **Problem:** Theme and language options in Settings are dummy HTML elements.
* **Actionable Fix:** Either wire dark/light mode toggle with working CSS tokens and persist to `localStorage`, or remove dummy selectors to eliminate confusion.

#### P3-3. Barcode Scanner Hardware Slot Alignment
* **Problem:** Barcode scanner uncommonly emits error beeps due to card misalignment.
* **Actionable Fix:** Chamfer the timber cutout using a ruler/file to create a tapered guide slot, ensuring cards sit flush at the focal distance (5–8 cm).

#### P3-4. Home Raspberry Pi Latency & Optimization Benchmark
* **Problem:** Kartik reported gestures felt laggy.
* **Actionable Fix:** Profile MediaPipe Hand Landmarker on the Raspberry Pi:
  * Reduce camera resolution to $640 \times 480$.
  * Use lightweight TFLite model delegate.
  * Verify thermal throttling (install small fan/heatsink if CPU drops below 1.5 GHz).

#### P3-5. Enclosure Wood Finish / Stain (Cosmetic)
* **Feedback:** Nico noted: *"Picky: prefer another wood color"*.
* **Actionable Fix:** Apply a darker walnut stain or satin black finish to match the black glass aesthetic.

---

## 3. Revised A/B Testing Framework (Addressing Real-World Issues)

Based on your Day 1 testing, we can evolve the A/B experiment from a subtle text cue test into a **definitive test of multimodal affordances**:

```
                       ┌────────────────────────────────────────┐
                       │          Session Initialized           │
                       └───────────────────┬────────────────────┘
                                           │
                          [50/50 Deterministic Assignment]
                                           │
                   ┌───────────────────────┴───────────────────────┐
                   ▼                                               ▼
       ┌───────────────────────┐                       ┌───────────────────────┐
       │  Variant A (Control)  │                       │ Variant B (Treatment) │
       ├───────────────────────┤                       ├───────────────────────┤
       │ • Legacy Video Demo   │                       │ • Anti-Touch Graphic  │
       │ • No Hand Cursor Dot  │                       │   (❌ Touch, ✔️ Air)   │
       │ • Pinch-Only Scroll   │                       │ • Live Cursor Dot     │
       │ • Hidden Dwell Cue    │                       │ • Open-Palm Swipe     │
       │                       │                       │ • Proactive Dwell Bar │
       └───────────────────────┘                       └───────────────────────┘
```

### Revised Experimental Hypotheses

| Hypothesis | Independent Variable | Expected Impact on Variant B | Key Metric |
| :--- | :--- | :--- | :--- |
| **$H_1$: False-Touchscreen Bounce Mitigation** | ❌ Touchscreen warning graphic | Dismantles capacitive touch instinct; users stop touching glass | Zero-interaction bounce drops from $> 45\%$ to $< 15\%$ |
| **$H_2$: Cursor Closed-Loop Control** | Live on-screen hand cursor dot | Bridges the gulf of execution; users immediately understand tracking | Time-to-first-gesture drops from $> 12\text{s}$ to $< 4\text{s}$ |
| **$H_3$: Natural Swipe Usability** | Open-palm vertical swipe scrolling | Matches natural student instinct discovered by Edward & Nico | Total scroll gestures increase by $> 150\%$ |
| **$H_4$: Dwell Toggle Completion** | Proactive corner pill with % feedback | Converts accidental triggers into intentional timetable returns | Dwell completion ratio increases from $< 35\%$ to $> 85\%$ |

---

## 4. Implementation Checklist Status

### Software Tasks Completed & Deployed
- [x] **Step 2:** Fix `/api/faces/train` 500 error & add biometric collision detection (< 0.38 distance).
- [x] **Step 3:** Fix Dashboard timetable link redirect (`navigate('/timetable')`).
- [x] **Step 4:** Fix telemetry barcode session attribution in `smart_mirror_pro.py` & `face_recognize.py`.
- [x] **Step 5:** Add floating hand cursor dot to PySide6 mirror overlay (Variant B).
- [x] **Step 6:** Add open-palm vertical swipe detection to `gesture_engine.py`.
- [x] **Step 7:** Add anti-touchscreen tutorial overlay (❌ Touch / ✔️ Air) and instant skip on gesture.
- [x] **Step 8:** Add interactive modal for notices with AI summary on web (`DailyNoticesWidget.jsx`) and mirror (`notices_widget.py`).
- [x] **Step 9:** Add step-by-step KAMAR ICS guide with visual step cards in `TimetableWidget.jsx`.
- [x] **Step 10:** Add Interval (10:30–10:55 AM) & Lunch (12:45–1:30 PM) break countdowns & indicators to web and mirror.
- [x] **Step 11:** Gate face registration behind student ID barcode link on web (`FaceCaptureModal.jsx`) and mirror unsure face prompt.
- [x] **Step 12:** Add Biometric Collisions & Enrolled Faces Audit tab to Admin Analytics for `marminamina3@gmail.com`.
- [x] **Step 13:** Fix Notices "Apply Changes" visual feedback & add Timetable display customization toggles.
- [x] **Step 14:** Add King's Library & Book Loans tracker with overdue alerts.
- [x] **Step 15:** Implement functional Theme switcher (OLED, Cyber Cyan, Midnight) and Language switcher (English / Te Reo Māori).

### Physical / Hardware Actions Checklist (User Action Required)
- [ ] **Physical Step 1: Mirror Relocation** — Move mirror away from direct window backlight onto a shaded corridor wall or perpendicular to windows so facial features are not crushed into silhouettes.
- [ ] **Physical Step 2: Display Brightness** — Set monitor hardware brightness and contrast to 100% to maximize luminance through the two-way mirror glass.
- [ ] **Physical Step 3: Barcode Slot Chamfering** — Chamfer/file the wooden barcode cutout slot with a ruler or file to ensure student ID cards slide flat and flush at the 5–8 cm focal plane.
- [ ] **Physical Step 4: KAMAR Photos** — Capture and drop real King's High School KAMAR portal screenshots into `web/public/assets/kamar/` to replace the illustrative diagrams.
- [ ] **Physical Step 5: Wood Stain (Optional)** — Apply walnut or satin black wood finish to the timber frame to match the black glass aesthetic.
