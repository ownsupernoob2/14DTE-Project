# Smart Mirror API

Base URL: `https://api.smartmirror.me` (or `http://localhost:8080` in development).

Every route belongs to one of four groups, which decides who may call it:

| Group | How a caller proves itself |
|---|---|
| **Public** | Nothing. |
| **Mirror** | `X-Mirror-Key: <MIRROR_API_KEY>` — the shared secret in the server's `.env` and each Pi's `~/.config/smart-mirror/env`. While the key is unset on the server these routes are open (a warning is logged). |
| **User** | `Authorization: Bearer <Auth0 access token>`. The account row is created on first use. |
| **Admin** | A user token whose Auth0 email is verified and listed in `ADMIN_EMAILS`. |

Errors are JSON: `{"error": "message a person can read"}`.

## Public

| Method | Path | Returns |
|---|---|---|
| GET | `/health`, `/api/health` | `{status, version}` |
| GET | `/api/version` | `{version, service}` |
| GET | `/api/notices` | Today's school notices |
| GET | `/api/notices/config` | Notice filters the mirrors apply |
| GET | `/api/kings-week` | King's Week articles |
| GET | `/api/banner` | `{message}` — campus banner, empty when none |
| GET | `/api/analytics/config` | `{mode, active_variant}` — A/B variant to serve |
| GET | `/api/screensaver` | `{mode: demo\|slideshow\|logo, slide_seconds, slides: [img], logo: img\|null}` |
| GET | `/api/screensaver/files/<sha256>.<ext>` | An uploaded screensaver image (immutable) |
| GET | `/api/timetable` | User token: your week. Mirror key + `?user_id=`: that student's. |

## Mirror

| Method | Path | Body → Returns |
|---|---|---|
| GET | `/api/download-index` | `{vectors: [[128 floats]], user_map: [user_id]}` — every enrolled face |
| POST | `/api/verify-face` | `{user_id}` (matched locally) → `{user_id, user_name, language, widgets, config}` |
| POST | `/api/verify-barcode` | `{barcode}` → same as verify-face. Rate limited per IP. |
| POST | `/api/analytics/events` | One visit (see `SessionAnalyticsEvent` in handlers_analytics.go) |
| GET | `/api/users/language?user_id=\|barcode=` | `{language}` |
| POST | `/api/logs` | `{logs: {name: content}}` or `{name, content}` → `{status: "ok", saved: [filenames]}` |

## User

| Method | Path | Notes |
|---|---|---|
| GET | `/api/users/me` | `{id, email, name, provider, has_face, has_barcode, is_admin, messages, contact_email}` |
| POST | `/api/users/me/messages/seen` | Dismiss removal notices |
| DELETE | `/api/users/me/data` | Delete your face scan, student ID, timetable link, layout and language |
| POST | `/api/faces/train` | `{images: [base64 JPEG/PNG, ≤15]}` → 202 `{status: "processing", job_id}`. Training runs in the background because it can outlast Cloudflare's wait. 400 if no photo is readable, 429 within 24 h of the last scan. |
| GET | `/api/faces/train/:job_id` | `{status: "processing"}` until done, then the result with its own status: 200 `{status: "trained", frames_used}`, 409 face belongs to another account, 422 no face found, 503 no face Python on the server. |
| DELETE | `/api/faces/me` | Delete your face scan |
| GET / PUT / DELETE | `/api/users/me/barcode` | `{barcode}` — your student ID (409 if another account has it) |
| GET / PUT / POST | `/api/users/me/language` | `{language: en-NZ\|mi-NZ}` |
| GET / POST / DELETE | `/api/timetable/ics` | `{ics_url}` — must be a King's High calendar link |
| GET | `/api/dashboard`, `/api/dashboard/widgets` | Your mirror layout |
| POST / PUT / DELETE | `/api/dashboard/widgets[/:id]`, PUT `/api/dashboard/widgets/bulk` | Edit it |

## Admin

| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/users?q=` | Everyone signed up: email, sign-in method, student ID, face scan, timetable, session count. `q` searches name, email, student ID. |
| DELETE | `/api/admin/users/:id` | Delete the account and its data; sessions stay, anonymised. Also deletes the Auth0 login when `AUTH0_MGMT_CLIENT_ID/SECRET` are set. |
| DELETE | `/api/admin/users/:id/:kind` | `kind` = `face`, `barcode`, `timetable` or `dashboard`. The student is told next time they sign in. |
| GET | `/api/admin/analytics` | Visit summary, A/B comparison, recent sessions |
| GET | `/api/admin/face-audit` | Blocked duplicate-face attempts |
| POST | `/api/analytics/config` | `{mode: auto\|force_a\|force_b\|hourly\|daily}` |
| POST | `/api/notices/config` | Notice filters for the mirrors |
| POST | `/api/notices/fetch` | Re-fetch today's notices now |
| POST | `/api/admin/screensaver` | `{mode, slide_seconds}` |
| POST | `/api/admin/screensaver/images?kind=slide\|logo` | multipart `files` (JPEG/PNG/WebP, ≤10 MB, ≤40 slides) |
| DELETE | `/api/admin/screensaver/images/:id` | |
| POST | `/api/admin/banner` | `{message}`. Also accepted with `X-Admin-Token: <ADMIN_TOKEN>` (the Windows updater). |
| GET | `/api/admin/logs?name=mirror` | Returns last 500 lines of daemon log file (`mirror`, `face`, `gesture`, `rpicam`, `ffmpeg`). |
| POST | `/api/admin/logs` | Same as `/api/logs`, accepts log payload with admin token. |

Every admin change is recorded in the `admin_audit` table.
