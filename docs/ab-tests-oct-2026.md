# A/B tests for a 3–4 day window (October 2026)

## First: the old results can't be trusted

Until this update the mirror counted **every hand movement as a tap**, so almost every
visit with a hand in view looked like "used gestures". Gesture adoption, tap counts and
the A vs B lift recorded before the fresh start are inflated and should not be quoted.
The database starts empty, so everything from now on is clean.

What one visit now records (one row in `sessions`):

| Field | Meaning |
|---|---|
| `session_type`, `auth_method`, `time_to_auth_sec` | guest or signed in; face or student ID; seconds from walking up to being recognised |
| `user_id` | which student (signed-in visits only), for per-user session counts |
| `has_gesture`, `time_to_first_gesture` | a deliberate control was used: scroll, tap or a held dwell |
| `hand_seen` | a hand was tracked at all (so `hand_seen − has_gesture` = tried but didn't get it) |
| `scroll_count`, `tap_count` | one per scroll / tap |
| `dwell_completed`, `dwell_abandoned`, `timetable_toggles` | top-right hold to bring the timetable back |
| `notice_opens`, `article_opens`, `modal_read_sec`, `kings_expands` | content engagement |
| `tutorial_shown`, `tutorial_dismissed` | the in-session gesture tutorial, and pinch-and-hold to close it |
| `from_screensaver`, `screensaver_mode` | the visit interrupted the screensaver, and which one |
| `variant`, `mirror_id`, `mirror_version` | experiment arm and which mirror/build |

A visit is everything from someone being seen to the mirror going idle again; flickers
under a second are dropped. A guest who then signs in stays one visit.

## How much data 3–4 days gives you

At a two-sided 5 % significance level with 80 % power, comparing two rates needs roughly:

| Rates being compared | Visits per arm |
|---|---|
| 30 % vs 50 % | ~95 |
| 40 % vs 55 % | ~170 |
| 40 % vs 50 % | ~390 |

So with one mirror you can only detect **large** differences in 3–4 days. Pick tests where
you expect a big effect, and use **daily** switching (admin dashboard → "Switch daily")
rather than per-session, so both arms see the same mix of lunchtimes, free periods and
after-school traffic. Run an even number of days (A, B, A, B) to balance weekdays.

## Test 1 — Re-run the dwell hint (no code changes)

The current experiment, with honest numbers this time.

- **A:** no hint. **B:** "Hold hand in top-right for Timetable" pill under the arrow.
- **Hypothesis:** the hint makes more signed-in students bring the timetable back.
- **Primary metric:** `timetable_toggle_rate` (user visits with ≥1 toggle).
- **Secondary:** `dwell_success_rate`, `avg_time_to_first_gesture`.
- **Run:** admin dashboard → A/B controller → *Switch daily*, 4 days.
- **Decide:** keep B if toggle rate is higher with p < 0.05; if not significant, keep
  whichever has the higher dwell success rate and note the result as inconclusive.

## Test 2 — Which screensaver brings people over (no code changes)

The new screensaver choice makes a clean test of the "attract" screen.

- **A:** gesture demo video. **B:** slideshow (school photos / events).
  Optional third day: logo only, as a "nothing to see" baseline.
- **Hypothesis:** the demo video teaches gestures before people arrive, so visits that
  start from it use gestures more (and sooner) than visits that start from a slideshow.
- **Primary metric:** `has_gesture` rate among visits with `from_screensaver = true`.
- **Secondary:** `time_to_first_gesture`, `hand_seen` rate, total visits per day
  (does the slideshow attract *more* people even if they gesture less?).
- **Run:** change *Screensaver* in the admin dashboard each morning: demo, slideshow,
  demo, slideshow. The variant column isn't needed — group by `screensaver_mode`.
- **Watch for:** day-of-week effects; compare same weekdays if you can.

## Test 3 — Show the tutorial on arrival, or only when someone is stuck (small code change)

- **A (current):** the tutorial plays as soon as a guest arrives, and again after 10 s
  without a gesture. **B:** only after 10 s without a gesture.
- **Hypothesis:** playing it immediately interrupts people who already know the gestures;
  waiting gets the same adoption with fewer dismissals.
- **Primary metric:** `has_gesture` rate. **Secondary:** `tutorial_dismissed / tutorial_shown`,
  `time_to_first_gesture`.
- **Needs:** the mirror to skip the on-arrival tutorial when the variant is B
  (`_trigger_transition` in smart_mirror_pro.py) — about ten lines.

## Test 4 — Visible cursor dot vs trail only (small code change)

- **A:** dot + trail (current). **B:** trail only (the trail fades when the hand is still).
- **Hypothesis:** a cursor that is always visible makes it obvious the mirror is tracking
  you, so more people who raise a hand go on to tap or scroll.
- **Primary metric:** `has_gesture / hand_seen` (conversion from "hand up" to "used it").
- **Secondary:** taps per visit, `notice_opens + article_opens`.
- **Needs:** `GestureTrailOverlay` to skip drawing the dot for variant B.

## Reading the results

The admin dashboard's battle card shows adoption, the z-score and p-value for the current
A/B variant. For tests grouped by something else (Test 2), *Export JSON* on the dashboard
and compare in a spreadsheet, or query `data/smartmirror.db` directly, e.g.:

```sql
SELECT screensaver_mode,
       COUNT(*)                                  AS visits,
       ROUND(100.0 * AVG(has_gesture), 1)        AS gesture_pct,
       ROUND(AVG(NULLIF(time_to_first_gesture, 0)), 1) AS secs_to_first_gesture
FROM sessions
WHERE from_screensaver = 1
GROUP BY screensaver_mode;
```

Report novelty effects honestly: if B wins on day 1–2 and not on day 3–4 (the dashboard's
"phase 1 / phase 2 lift"), say the effect may be novelty rather than design.
