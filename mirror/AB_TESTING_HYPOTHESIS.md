# Smart Mirror A/B Testing: Hypotheses & Telemetry Specification

**Project:** 14DTE Smart Mirror (King's High School)  
**Author:** ownsupernoob2 (marminamina3@gmail.com)  
**Date:** October 2026  
**Document Status:** Ready for Implementation  

---

## 1. Problem Statement & User Mental Model

In human-computer interaction (HCI), physical glass displays carry a powerful **false affordance**: users instinctively assume interactive displays are touchscreens. When encountering the Smart Mirror, users exhibit two primary friction points:

1. **The Touchscreen Assumption (Touch vs. Vision Gestures):**
   * Users physically tap, press, or smudge the mirror glass expecting capacitive touch.
   * The current tutorial animation illustrates a hand with "CLICK" and "SCROLL" captions, but does not explicitly state that interaction is **touchless in mid-air via camera tracking**. Users who tap the glass feel the mirror is unresponsive and walk away.
2. **Hidden Timetable Dwell Mechanics:**
   * After the timetable collapses into King's Week, users have **no visual indicator** explaining how to bring their schedule back.
   * The top-right quadrant dwell requires holding a raised hand in the air for 1.6s. Because this affordance is completely invisible until the hand is already in position, discovery is near zero unless verbally explained.

---

## 2. A/B Testing Framework & Variant Definitions

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
     │ - Implicit Tutorial   │                       │ - Anti-Touch Graphic  │
     │ - Hidden Dwell Cue    │                       │   (❌ Touch, ✔️ Air)   │
     │ - Pinch-Only Drag     │                       │ - Live Cursor Dot     │
     │ - No Cursor Dot       │                       │ - Open-Palm Swipe     │
     │                       │                       │ - Proactive Dwell Bar │
     └───────────────────────┘                       └───────────────────────┘
```

### Variant A: Control (Current Implicit Design)
* **Onboarding:** Standard gesture demo video plays on idle/guest arrival with generic "CLICK" / "SCROLL" graphics without anti-touchscreen warnings.
* **Hand Feedback:** No visible on-screen cursor dot; user receives zero continuous feedback on whether their hand is detected or where it is mapped.
* **Scrolling:** Requires strict pinch-and-drag (thumb + index finger pressed together).
* **Timetable Discovery:** No visual guide indicating how to reopen the timetable. Top-right dwell bar only appears *after* the hand has already entered the top-right zone and stayed for $> 0.2\text{s}$.

### Variant B: Treatment (Explicit Multimodal Touchless Affordances)
* **Onboarding & Anti-Touchscreen Tutorial Graphic:**
  * Animated visual overlay at video start showing:
    * Hand physically touching the glass with a glowing red **❌ ("DO NOT TOUCH GLASS — INERT SCREEN")**.
    * Hand moving 30 cm away in the air with a glowing green **✔️ ("TOUCHLESS AIR GESTURES — MOVE IN AIR")**.
  * Immediate gesture bypass: any gesture during the tutorial immediately fades it out and executes the action.
* **Closed-Loop Feedback (Live On-Screen Cursor Dot):**
  * Displays a glowing 24px circular indicator tracking the user's hand position $(x, y)$ in real-time.
  * Transitions to green when active/pinching, providing immediate visual confirmation that the mirror's computer vision sees their hand.
* **Intuitive Open-Palm Wave / Swipe Scrolling:**
  * In addition to pinch-and-drag, accepts broad natural open-palm vertical swipes (flicking hand up/down) to scroll without requiring a fine-motor pinch.
* **Timetable Discovery (Proactive Corner Affordance):**
  * Subtle, clean pill in top-right header: `"✋ Hold hand in top-right for Timetable"` with live percentage progress `(15%... 60%... 100%)`.

---

## 3. Formal Scientific Hypotheses

### Hypothesis 1: Touchless Gesture Discovery Rate
* **Null Hypothesis ($H_{0,1}$):** Providing explicit "in-air / touchless" guidance produces no significant change in the proportion of sessions where users attempt touchless gestures ($P_A = P_B$).
* **Alternative Hypothesis ($H_{1,1}$):** Explicit touchless framing will significantly increase gesture discovery ($P_B > P_A$).
  * *Target Expectation:* Increase gesture adoption from $\le 15\%$ (Variant A) to $\ge 40\%$ (Variant B).
* **Statistical Test:** Two-proportion $Z$-test (significance threshold $\alpha = 0.05$, power $1 - \beta = 0.80$).

### Hypothesis 2: Timetable Dwell Toggle Discovery
* **Null Hypothesis ($H_{0,2}$):** A proactive top-right dwell cue produces no significant difference in timetable toggle rates ($P_A = P_B$).
* **Alternative Hypothesis ($H_{1,2}$):** Proactive visual dwell cues will increase timetable recall from $< 5\%$ to $> 25\%$ among authenticated users.
* **Statistical Test:** Pearson's Chi-square ($\chi^2$) test of independence.

### Hypothesis 3: Time-to-First-Gesture (Latency of Confusion)
* **Null Hypothesis ($H_{0,3}$):** Mean elapsed time from session start to the user's first valid gesture is identical across variants ($\mu_A = \mu_B$).
* **Alternative Hypothesis ($H_{1,3}$):** Clear touchless framing reduces hesitation and confusion, lowering time-to-first-gesture from $> 12\text{s}$ to $< 5\text{s}$.
* **Statistical Test:** Two-sample independent $t$-test / Mann-Whitney $U$ test.

### Hypothesis 4: False-Touchscreen Bounce Mitigation (Zero-Interaction Rate)
* **Null Hypothesis ($H_{0,4}$):** Explicit touchless guidance produces no change in the proportion of sessions that terminate with zero recognized gestures ($P_{\text{bounce},A} = P_{\text{bounce},B}$).
* **Alternative Hypothesis ($H_{1,4}$):** Users encountering Variant A frequently tap the physical glass, encounter no response, and walk away in frustration. Variant B dismantles this mental model failure, reducing zero-interaction abandonment from $> 45\%$ to $< 18\%$.
* **Statistical Test:** Two-proportion $Z$-test.

### Hypothesis 5: Dwell Intent vs. Accidental Edge Triggering (Dwell Success Ratio)
* **Null Hypothesis ($H_{0,5}$):** Proactive visual progress pills produce no difference in the ratio of completed dwell toggles versus abandoned entries ($R_{\text{dwell},A} = R_{\text{dwell},B}$).
* **Alternative Hypothesis ($H_{1,5}$):** In Variant A, top-right dwell entries are predominantly accidental (users moving hands near the edge), resulting in high abandon rates ($< 35\%$ completion). In Variant B, the proactive percentage countdown converts accidental passes into intentional actions ($> 80\%$ completion ratio).
* **Formula:**  
  $$\text{Dwell Success Ratio} = \frac{\text{Dwell Completed}}{\text{Dwell Completed} + \text{Dwell Abandoned}} \times 100\%$$

### Hypothesis 6: Novelty Stabilization (Week 1 Exploration vs. Week 2 Habituated Utility)
* **Null Hypothesis ($H_{0,6}$):** The observed lift in gesture adoption in Variant B decays to zero ($L_2 \le 0\%$) during Week 2 after the initial curiosity phase passes.
* **Alternative Hypothesis ($H_{1,6}$):** Variant B maintains a statistically significant positive lift ($L_2 \ge 20\%$) across Week 2, confirming sustained usability improvement over superficial novelty.

---

## 4. Addressing Confounding Factors & The Novelty Effect

To ensure rigorous data for academic and evaluation standards (NCEA Level 3 / Year 14 DTE):

1. **Novelty Effect Control:**
   * **Week 1 vs. Week 2 Trend Partitioning:** Analytics split chronologically into Phase 1 (exploration, peer demonstration) vs. Phase 2 (stabilized, habit-driven utility).
   * Key metric: **Phase 2 Lift Retention** ($\Delta \text{Lift} = \text{Phase 2 Lift} - \text{Phase 1 Lift}$).
2. **Day-of-Week Bias Elimination:**
   * Instead of running Variant A for one week and Variant B for the next, variants are **randomized per session (50/50)**. Both variants experience identical distribution across Monday assemblies, Wednesday sports afternoons, and Friday bell changes.
3. **Lighting & Environmental Normalization:**
   * Camera tracking depends on ambient corridor lighting. Session-level randomization ensures both variants run under identical sunlight, morning, and afternoon lighting conditions.

---

## 5. Mathematical Formulations & Statistical Engine

The backend API (`GET /api/admin/analytics`) automatically computes live two-proportion hypothesis tests:

$$\hat{p}_A = \frac{x_A}{n_A}, \quad \hat{p}_B = \frac{x_B}{n_B}$$

Pooled sample proportion:
$$\hat{p} = \frac{x_A + x_B}{n_A + n_B}$$

Standard Error ($SE$):
$$SE = \sqrt{\hat{p}(1 - \hat{p})\left(\frac{1}{n_A} + \frac{1}{n_B}\right)}$$

Test Statistic ($Z$-score):
$$Z = \frac{\hat{p}_B - \hat{p}_A}{SE}$$

Two-tailed $p$-value (using Gauss error function $\text{erf}$):
$$p = 1 - \text{erf}\left(\frac{|Z|}{\sqrt{2}}\right)$$

Decision Rule:
$$\text{Reject } H_0 \text{ in favor of } H_1 \iff p < 0.05 \quad (\alpha = 0.05, \text{ 95\% Confidence})$$

---

## 6. Telemetry Data Specification

Each completed session sends a structured summary to `POST /api/analytics/events`:

```json
{
  "session_id": "c7f91a2e-4b6d-8910-bcde-0123456789ab",
  "client_timestamp": 1729000000.450,
  "variant": "B",
  "session_type": "user",
  "auth_method": "face",
  "duration_sec": 28.4,
  "has_gesture": true,
  "time_to_first_gesture_sec": 3.8,
  "gesture_scroll_count": 6,
  "gesture_tap_count": 1,
  "timetable_toggle_count": 2,
  "dwell_completed_count": 2,
  "dwell_abandoned_count": 0,
  "article_modal_opens": 1,
  "modal_read_time_sec": 7.2
}
```

---

## 7. Admin Analytics Dashboard Metrics

The private web dashboard (`/admin` authenticated via `marminamina3@gmail.com`) displays:

1. **A/B Experiment Head-to-Head Battle Card:**
   * Sample Size ($N_A$ vs. $N_B$)
   * Gesture Adoption Rate ($A$ vs. $B$ with percentage lift)
   * Zero-Interaction Bounce Rate (Screen-Tap Confusion Indicator)
   * Dwell Completion Ratio ($\% \text{ Completed vs. Abandoned}$)
   * Average Time-to-First-Gesture ($A$ vs. $B$)
   * Article Modal Reading Duration & Engagement
   * Live Two-Proportion $Z$-Score and Two-Tailed $p$-Value Badge
   * Novelty Effect Phase 1 vs. Phase 2 Stability Tracking
2. **Core System KPIs:**
   * Total Sessions (Today, This Week, All-Time)
   * User Sessions vs. Guest Sessions
   * Authentication Method Ratio (Face Recognition vs. Physical Barcode)
   * Average Session Duration
3. **Peak Traffic Heatmap:**
   * Interaction volume grouped by hour of the school day.

