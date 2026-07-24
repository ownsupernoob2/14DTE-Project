# Implementation Plan - Redesign Web & Mirror UI to Match new-style.html

Redesign both the Web Application (`web/`) and Smart Mirror PyQt6 Application (`mirror/`) to match the high-contrast, dark minimal style of [examples/new-style.html](file:///d:/minali39/14DTE-Project/examples/new-style.html), as demonstrated in the user's reference design screenshot.

## Proposed Design System & Style Guide

- **Background & Panels**:
  - Main background: `#000000` (Pure Black)
  - Card & Panel background: `#0a0a0a` (Dark Gray Panel)
  - Borders & Dividers: `#1c1c1c` (Thin Crisp Border)
- **Typography**:
  - UI Display & Headers: `'Segoe UI', system-ui, sans-serif`
  - Time, Date, Counters & Code: `'Consolas', 'SFMono-Regular', monospace`
- **Color Palette & Accents**:
  - Primary High Text: `#ffffff` (Pure White)
  - Secondary Mid Text: `#d0d0d0` (Soft Gray)
  - Muted Low Text: `#8f8f8f` (Muted Gray)
  - Current Class / Active State Highlight: `#4fc3ff` (Cyan)
  - Urgent Alert: `#ff4d4d` (Vibrant Red)
  - Warning / Medium Importance: `#ffb020` (Amber)
  - Success / Normal: `#35d07f` (Green)

---

## Proposed Changes

### Web Application (`web/`)

#### [MODIFY] [index.html](file:///d:/minali39/14DTE-Project/web/index.html)
- Update Tailwind color tokens to reflect pure black background (`#000000`), `#0a0a0a` panel color, `#1c1c1c` borders, cyan accent (`#4fc3ff`), red (`#ff4d4d`), and amber (`#ffb020`).
- Update font definitions for display and monospace.

#### [MODIFY] [theme-constants.css](file:///d:/minali39/14DTE-Project/web/src/styles/theme-constants.css) & [index.css](file:///d:/minali39/14DTE-Project/web/src/index.css)
- Set root CSS variables (`--bg: #000000`, `--panel: #0a0a0a`, `--line: #1c1c1c`, `--text-hi: #ffffff`, `--text-mid: #d0d0d0`, `--text-low: #8f8f8f`, `--now: #4fc3ff`, `--urgent: #ff4d4d`, `--warn: #ffb020`).
- Remove old radial glowing background blobs to maintain pure dark minimal aesthetic.
- Update global card, button, chip, and scrollbar styles.

#### [MODIFY] [Navbar.jsx](file:///d:/minali39/14DTE-Project/web/src/components/Navbar.jsx)
- Style header with `#0a0a0a` background and `#1c1c1c` bottom border.
- Highlight active tab with cyan underline/accent text.

#### [MODIFY] [DailyNoticesWidget.jsx](file:///d:/minali39/14DTE-Project/web/src/components/DailyNoticesWidget.jsx)
- Style header with title `Notices` and mono count (`6 today`).
- Implement pill filter chips (`All`, `Academic`, `Sports`, `Arts`) with cyan border for active state.
- Render notice cards with `#0a0a0a` background and 3px left borders:
  - Red `#ff4d4d` left border & red meta text for Urgent notices.
  - Amber `#ffb020` left border & amber meta text for Medium/Academic notices.
  - Dark gray `#3a3a3a` left border & muted meta text for Low/General notices.
- Title in white `#ffffff`, body text in mid-gray `#d0d0d0` clamped to 2 lines.

#### [MODIFY] [TimetableWidget.jsx](file:///d:/minali39/14DTE-Project/web/src/components/TimetableWidget.jsx)
- Top clock row: Date (e.g. `Wed, 22 Jul`) left aligned, time (e.g. `10:36`) right aligned in monospace font with `#1c1c1c` bottom border.
- Hero class focus layout:
  - `CURRENT CLASS` cyan eyebrow (`#4fc3ff`).
  - Giant bold white subject title (`13DTE`).
  - Details row: `ROOM T5`, `ENDS 1:00pm`, `LEFT 19m` (mono countdown).
  - Divider line `#1c1c1c`.
  - `NEXT` block: `13PHY` next subject, `Lab 4 · 1:00pm` next meta.

#### [MODIFY] [Dashboard.jsx](file:///d:/minali39/14DTE-Project/web/src/pages/Dashboard.jsx) & [Simulator.jsx](file:///d:/minali39/14DTE-Project/web/src/pages/Simulator.jsx)
- Arrange main layout into the 34% / 66% grid split.
- Render top red alert banner if an important message exists.
- Support guest state (`Not recognized`) and recognized state transitions cleanly.

---

### Python Smart Mirror Application (`mirror/`)

#### [MODIFY] [style.py](file:///d:/minali39/14DTE-Project/mirror/widgets/style.py)
- Define new RGB color tuple constants: `COLOR_BG`, `COLOR_PANEL`, `COLOR_LINE`, `COLOR_TEXT_HI`, `COLOR_TEXT_MID`, `COLOR_TEXT_LOW`, `COLOR_NOW`, `COLOR_URGENT`, `COLOR_WARN`.

#### [MODIFY] [smart_mirror_pro.py](file:///d:/minali39/14DTE-Project/mirror/smart_mirror_pro.py)
- Update main background to solid `#000000` (disabling/simplifying ambient gradient orbs to match new dark style).
- Re-layout 2-column main grid (34% left for Notices, 66% right for Focus & Clock).
- Render top red banner: gradient `#3a0d0d` to `#1a0505`, red `NOTICE` tag pill.
- Guest layout: Guest CTA (`＋` glyph, `Not recognized`, `Register your face...`, `smartmirror.me/register`).
- Idle view: Dim monospace clock & date.

#### [MODIFY] [notices_widget.py](file:///d:/minali39/14DTE-Project/mirror/widgets/notices_widget.py)
- Header layout: `Notices` (22px bold white), `6 today` count (13px monospace).
- Category filter bar: `All`, `Academic`, `Sports`, `Arts` chips.
- Notice card layout: `#0a0a0a` background, 3px colored left border (`#ff4d4d` for urgent, `#ffb020` for medium, `#3a3a3a` for low), uppercase meta line, bold white title, mid-gray body text.

#### [MODIFY] [clock_widget.py](file:///d:/minali39/14DTE-Project/mirror/widgets/clock_widget.py)
- Format as clock row: Date string (e.g. `Wed, 22 Jul`) left aligned, digital time `10:36` right aligned in monospace font with bottom divider line `#1c1c1c`.

#### [MODIFY] [timetable_widget.py](file:///d:/minali39/14DTE-Project/mirror/widgets/timetable_widget.py)
- Render `CURRENT CLASS` cyan eyebrow (`#4fc3ff`), giant subject name `13DTE`, room `T5`, ends `1:00pm`, left `19m`, divider line, `NEXT` eyebrow, subject `13PHY`, and details `Lab 4 · 1:00pm`.

---

## Verification Plan

### Automated / Syntax & Build Verification
1. **Web App Build**: Run `npm run build` or `npx vite build` inside `web/` to verify there are no syntax errors, JSX errors, or broken imports.
2. **Python Syntax Check**: Run `python -m py_compile mirror/smart_mirror_pro.py mirror/widgets/*.py` to ensure all Python Qt scripts compile cleanly with zero syntax errors.

### Manual Verification
1. Inspect `web/src` components and verify layout matches `examples/new-style.html` colors, font hierarchy, notice list borders, clock header, class focus block, and next class block.
2. Test responsive layouts on desktop and simulator views.
