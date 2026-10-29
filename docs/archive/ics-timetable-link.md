# Archived: timetable from a calendar link (.ics)

Archived 30 October 2026. Timetables now come from KAMAR through the server
(see `kamar-directory-services-setup.md`), using the student ID a student links
in Settings. Nothing in normal setup asks for a calendar link any more.

The old method still works and is kept as a fallback for when the KAMAR
timetable isn't working for someone.

## How the old method worked

1. The student signed in to the school's KAMAR portal, opened "Timetable and
   Attendance", and copied the calendar link at the bottom of the page. It looks
   like `https://kingshigh.school.kiwi/ics/12345-XXXX.ics`.
2. They pasted it into the website. The server saved it against their account
   (`users.ics_url`) after checking it was a King's High link.
3. When the mirror or website asked for the timetable, the server downloaded
   that calendar (cached for 10 minutes, with a stale copy kept for a day if the
   school's site was down) and picked out this week's and next week's lessons.

## Where it lives now

| Part | Where |
|---|---|
| Website: the "how to find your link" slideshow and the link form | `web/src/legacy/IcsTimetableLink.jsx` (with the two screenshots in `web/src/assets/timetable-instructions/`) |
| Website: where students reach it | Settings, at the very bottom, a closed "Troubleshooting" section |
| Server: save, read and remove a link | `GET / POST / DELETE /api/timetable/ics` in `server/timetable.go` (unchanged) |
| Server: downloading and reading the calendar | `parseTimetable`, `fetchICS` and `parseICSWeek` in `server/timetable.go`. KAMAR's own timetables are read by the same code. |

## When it is used

`/api/timetable` picks the timetable in this order:

1. The timetable KAMAR sent for the student's linked student ID.
2. Otherwise the student's own calendar link, if they saved one.
3. Otherwise "no timetable" (404), and the website and mirror say to link a
   student ID.

So a saved calendar link only takes effect when KAMAR has no timetable for that
student. If a student has a stale or wrong KAMAR timetable, a calendar link will
not override it. Deleting their row from `kamar_timetables` (or waiting the 30
days after KAMAR stops sending) lets the link take over.

## Bringing it back to the front

To make it a normal setup step again: show the `LegacyCalendarLink` section (or
the `TimetableSetupModal` inside it) from the website's timetable widget and
onboarding, as it was before this change (see git history of
`web/src/components/TimetableWidget.jsx` and `web/src/pages/Dashboard.jsx`).
