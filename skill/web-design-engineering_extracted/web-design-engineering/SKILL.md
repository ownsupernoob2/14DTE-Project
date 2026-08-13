---
name: web-design-engineering
description: >
  Guidelines for producing browser-rendered visual artifacts: landing pages, dashboards,
  prototypes, slide decks, data visualizations, UI mockups, animations. The bar is "stunning,"
  not "functional." Use this skill whenever you are building any frontend UI, web page, React
  component, or visual browser artifact. Covers: anti-cliché design mandates, design system
  declaration, v0 draft workflow, dial calibration, and technical CSS/JS specs. Apply this
  whenever the deliverable renders in a browser — do not default to generic safe design.
---

# Web Design & Frontend Engineering Guidelines for AI Models

Guidelines for producing browser-rendered visual artifacts: landing pages, dashboards, prototypes, slide decks, data visualizations, UI mockups, animations. The bar is "stunning," not "functional." Every pixel is intentional, every interaction deliberate.

These guidelines apply to HTML/CSS/JS and React work. They do not apply to back-end APIs, CLI tools, data-processing scripts, or long-form article conversion.

---

## The Core Problem

AI-generated frontends all look the same: rounded corners, blue-purple gradients, card grids with shadows, Inter everywhere, uniform spacing, safe palettes. This is the "AI look" — the average of training data — and it has zero brand recognition value.

Real design has opinions. It makes choices that exclude alternatives. It creates tension and resolves it. It has rhythm, not uniformity. The goal is output that is indistinguishable from an award-winning human designer's work.

---

## Workflow

### Step 0: Verify Facts First

When the request names a specific product, SDK, brand, model, or release — verify current facts before designing around them. Never assert specs from memory.

Forbidden without prior search: "I think X hasn't released yet," "X is currently version N," "X probably doesn't exist," "as I recall, X's specs are…"

If search comes back ambiguous, ask. Don't guess and design around wrong facts.

### Step 1: Understand the Request

Don't fire off a long list of questions every time. Calibrate by how much information was provided:

- "Make a deck" with no context → ask about audience, duration, tone.
- "Use this PRD to make a 10-min deck for Eng All Hands" → enough info, start building.
- "Make me something nice / I don't know what style I want" → switch to **Design Direction Advisor** mode (see below), don't interrogate.

### Step 2: Gather Design Context

Good design is rooted in existing context. Priority order:

1. Resources the user provides (screenshots, Figma, codebase, design system) → read thoroughly, extract tokens.
2. Existing pages of the product → ask if you can review them.
3. Industry references → ask which brands or products to use as a reference point.
4. Starting from scratch → explicitly tell the user this will affect quality, then propose directions.

**Code beats screenshots**: When both are available, extract design tokens from source code rather than guessing from images. Rebuilding from code yields far higher fidelity.

### Step 2b: Produce a Design Read and Calibrate Five Dials

Before choosing tokens, state a design read:

```yaml
Design Read:
  artifact: [landing / dashboard / prototype / slides / visualization / ...]
  audience: [primary audience]
  visual-language: [specific family, not "modern / clean"]
  mode: [greenfield / extension / preserve / overhaul]
  visual-variance: [1-10]      # how much do sections diverge from each other?
  motion-intensity: [1-10]     # how much moves and how elaborately?
  information-density: [1-10]  # content per viewport?
  asset-dependence: [1-10]     # reliance on real brand assets?
  brand-fidelity: [1-10]       # adherence to an existing system?
```

These dials must drive **real decisions** — not decorative labels. A `motion-intensity: 2` means almost nothing animates. A `visual-variance: 9` means sections look radically different. Use them.

### Step 3: Declare the Design System Before Writing Code

State your design brief before the first line of code:

```
DIRECTION: [one phrase, e.g. "brutalist editorial with acid accents"]
MOOD: [emotional register]
PALETTE: [actual hex/oklch values, 2–4 colors with roles]
TYPE: [display face + body face, by name]
LAYOUT: [the structural idea in one sentence]
SIGNATURE: [the one memorable move]
```

The **SIGNATURE** is non-negotiable. Every great design has one thing you remember. Identify it and make sure it actually appears in the final code — not just the brief.

**Two commitment rules**:
- Default to brave. When torn between safe and bold, pick bold.
- Don't converge. If you just did a dark portfolio, deliberately pick something different. Rotate: warm editorial, bold brand color, sophisticated minimal, brutalist, retro, organic.

**Stop and confirm** the design system before writing code. Actually wait for a response — don't say "let me know if this looks right" and immediately start building.

### Step 4: Show a v0 Draft Early

Before full components, produce a viewable v0: core structure + color/type tokens + key layout + module placeholders (explicitly marked `[image]`, `[icon]`, etc.) + a list of design assumptions.

A v0 with clear assumptions is more valuable than a "perfect v1" that took 3× the time and went in the wrong direction.

Stop and show the v0 before continuing. The whole point is course-correction.

### Step 5: Full Build

After v0 approval, write full components, add states, implement motion. At any non-trivial decision point during the build — interaction approach, content variant, layout shift — pause and confirm instead of pushing through silently.

### Step 6: Pre-Delivery Self-Check

Before delivering, verify:

- [ ] Facts were verified if any specific product/brand was named.
- [ ] Design Read and five dials exist and influenced real decisions.
- [ ] If branded: logo is real (not a colored rectangle); product imagery is real (not a CSS silhouette).
- [ ] No obvious broken imports, missing state handlers, or invalid markup.
- [ ] Responsive rules exist for target viewports.
- [ ] All interactive elements have hover/focus/active states — not browser defaults.
- [ ] No text overflow or truncation; `text-wrap: pretty` applied.
- [ ] All colors come from the declared system — no rogue hues introduced.
- [ ] No AI clichés (see below) unless the brand spec explicitly calls for them.
- [ ] No filler content, no fabricated data, no dummy testimonials.

---

## The Anti-Cliché Mandate

Anti-cliché is not aesthetic snobbery — it protects brand recognition. AI defaults = average of training data = all brands averaged together = no brand is recognized. Every cliché applied dilutes the user's identity.

| Pattern | Why it's slop | When it's actually fine |
|---|---|---|
| Blue → purple gradient backgrounds | The "tech vibe" formula; on every SaaS/AI/web3 page | Brand explicitly uses it, or task is satirizing the aesthetic |
| `border-radius: 12px` on everything | Material/Tailwind era leftover; visual noise in dashboards | User explicitly asks, or brand spec preserves it |
| `box-shadow: 0 4px 6px rgba(0,0,0,0.1)` everywhere | Default drop shadow from every tutorial | Use sparingly; prefer `backdrop-filter` or solid borders |
| Uniform card grids with identical spacing | AI layout fallback | Break the grid; vary sizes; use asymmetric layouts |
| Inter / Roboto / Arial as display face | Too common; reads as "demo page" | Brand spec specifies these |
| Centered hero with `max-width: 1200px` on every page | The HTML starter template | Try left-aligned, full-bleed, pushed-to-one-side |
| Generic hover states (`opacity: 0.8`) | No design intent whatsoever | Never — hover states should tell a small story |
| CSS silhouettes substituting for product imagery | Zero recognition value for hardware/physical products | **Never** for branded work — go fetch the real image |
| Emoji as icon substitutes | "No icon library" workaround, reads as amateur | Brand actually uses emoji (Notion, early Linear); otherwise use honest placeholder |
| Fabricated stats, fake logo walls, dummy testimonials | Damages credibility; users notice mismatches | **Never** — use clearly marked placeholders |
| Gradient-clipped hero text (blue→purple) | Scale and weight create impact, not gradients | Solid dramatic type does more |
| Glassmorphic cards everywhere | Glass on at most one element class (usually fixed nav) | Solid surfaces and borders for everything else |

**The ownership test**: Strip the brand name — could this design belong to any company? If yes, it has no point of view yet.

---

## Design Direction Advisor Mode

Trigger when the request is genuinely vague ("make something nice," "give me some directions," "I don't know what style I want") and no design context exists.

Don't ask 10 generic taste questions. Instead, propose **3 design directions from clearly different schools** so the contrast is visible and the choice is meaningful.

Each direction must include:
- A **named designer or studio reference** (not "minimalist" — "Kenya Hara / MUJI minimalist")
- 2–3 lines on why it fits the context
- 3–4 concrete signature cues (specific colors, type, motion, layout details)

Never pick 3 directions from the same school — the contrast is the point.

School examples to draw from (pick across rows, never within):

| School | Vibe | Anchors |
|---|---|---|
| Information architecture | Rational, data-driven, restrained | Pentagram, Edward Tufte, Massimo Vignelli |
| Editorial / minimalist | Whitespace, refined typography, quiet luxury | Kenya Hara, Apple HIG, Dieter Rams |
| Modern tool / Builder SaaS | Hairline detail, warm dark, monospace chips | Linear, Vercel, Raycast |
| Motion / experimental | Bold, generative, sensory | Field.io, Active Theory, Resn |
| Brutalist / raw | Anti-design, honest, unpolished | Balenciaga, Are.na, Bloomberg Businessweek |
| Warm humanist | Approachable, organic, hand-touched | Early Mailchimp, Stripe Press, Headspace |

---

## Technical Specifications

### React + Babel (Inline JSX) — Three Hard Rules

These are actual bugs, not style preferences:

**1. Never `const styles = { ... }` as a shared variable name.** Multiple Babel script blocks silently overwrite each other. Always namespace: `const terminalStyles`, `const headerStyles`. Or use inline `style={{...}}` directly.

**2. Separate `<script type="text/babel">` blocks don't share scope.** Each compiles independently. To share components across files, explicitly attach to `window`: `Object.assign(window, { MyComponent })`.

**3. Never use `scrollIntoView` in iframe-embedded environments.** It hijacks outer-frame scrolling. Use `element.scrollTop = ...` or `window.scrollTo({...})` instead.

### CSS Best Practices

```css
/* Fluid type scale — always use this, never fixed px for headings */
:root {
  --step-0: clamp(1.00rem, 0.91rem + 0.43vw, 1.25rem);
  --step-1: clamp(1.20rem, 1.07rem + 0.63vw, 1.56rem);
  --step-2: clamp(1.44rem, 1.26rem + 0.89vw, 1.95rem);
  --step-3: clamp(1.73rem, 1.48rem + 1.24vw, 2.44rem);
  --step-4: clamp(2.07rem, 1.73rem + 1.70vw, 3.05rem);
  --step-5: clamp(2.49rem, 2.03rem + 2.31vw, 3.82rem);
}

/* Spacing system */
:root {
  --space-xs:  clamp(0.75rem, 0.68rem + 0.33vw, 0.94rem);
  --space-s:   clamp(1.00rem, 0.91rem + 0.43vw, 1.25rem);
  --space-m:   clamp(1.50rem, 1.37rem + 0.65vw, 1.88rem);
  --space-l:   clamp(2.00rem, 1.83rem + 0.87vw, 2.50rem);
  --space-xl:  clamp(3.00rem, 2.74rem + 1.30vw, 3.75rem);
  --space-2xl: clamp(4.00rem, 3.65rem + 1.74vw, 5.00rem);
}
```

- Prefer CSS Grid + Flexbox for layout.
- Use CSS custom properties for design tokens.
- Derive color variants with `oklch()` — never invent new hues from scratch.
- Use `text-wrap: pretty` for better line breaking.
- Respect `@media (prefers-reduced-motion)` on every animation.
- Use `@container` queries for component-level responsiveness.
- Apply `-webkit-font-smoothing: antialiased` on dark backgrounds.

### Animation Priority Order

Don't reach for a heavy library first:

1. CSS transitions/animations — sufficient for 80% of micro-interactions.
2. Simple React state + setTimeout/requestAnimationFrame — frame-by-frame or event-driven.
3. Custom timeline approach — for multi-segment choreography (play/pause/scrubber).
4. Popmotion as fallback — only if the above genuinely can't cover the use case.

Avoid Framer Motion / GSAP / Lottie unless explicitly requested. Bundle overhead + version conflicts are not worth it in most artifacts.

### Placeholder Philosophy

When assets are missing, a placeholder is more professional than a poorly drawn fake:

- Missing icon → square + label (`[icon]`, `▢`)
- Missing avatar → initial-letter circle with color fill
- Missing image → placeholder card with aspect-ratio info (`16:9 image`)
- Missing data → ask the user; never fabricate
- Missing logo → **stop and ask** — never substitute "brand name in a colored box"

---

## Output-Type-Specific Rules

### Slide Decks
- Fixed canvas at 1920×1080 (16:9), auto-fitted via JS `transform: scale()`.
- Keyboard navigation: ← → to change slides, Space for next.
- Persist position in `localStorage` so refreshes don't reset.
- Slide numbering is 1-indexed: `01 Title`, `02 Agenda`.
- Don't cram text — visuals lead, text supports.

### Data Visualization Dashboards
- Chart.js (simple) or D3.js (complex custom).
- Responsive chart containers via `ResizeObserver`.
- Provide dark/light mode toggle.
- Minimize chart junk: remove unnecessary gridlines, 3D effects, decorative shadows.
- Color encoding must carry semantic meaning, not serve as decoration.

### Interactive Prototypes
- No title screen — prototypes should center in the viewport immediately.
- Use device frames (iPhone, browser window) to enhance realism.
- At least 3 variants, toggled via a Tweaks panel.
- Complete state coverage: default / hover / active / focus / disabled / loading / empty / error.

### Tweaks Panel
- Floating panel in the bottom-right corner, labeled "Tweaks."
- Completely hidden when closed so the design looks final during presentations.
- In multi-variant scenarios, expose variants as dropdowns/toggles within Tweaks.
- Even when not asked for, add 1–2 creative tweaks by default.
