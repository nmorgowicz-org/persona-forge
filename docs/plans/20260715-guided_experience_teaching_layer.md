# Guided Experience & Teaching Layer

Date: 2026-07-15
Status: Scoped, not started. Deferred out of `feature/voice-style-foundation` to keep that
branch mergeable; pick up as its own initiative.

Related: `docs/plans/20260709-app_roadmap_backlog.md` (§1 Dual-Audience UX invariant, §4.2
Accent DNA Panel / Hero-Take Coverage Map, §7.1 UX Cohesion) — this doc is the deeper,
teaching-focused elaboration of those items and should be read alongside them, not instead
of them.

---

## Why this is a separate doc, not part of the current branch

`feature/voice-style-foundation` already landed a large set of *guardrail*-style UX
improvements: pacing warnings, regen cost estimates, cancellation feedback, batch retention,
persisted speed. That's the "prevent mistakes / show state" layer, and it's in decent shape.

What's described below is the "teach the user *why*" layer — plain-language explanation,
progressive disclosure, guided flows, and troubleshooting content. It's a different kind of
work (content design + information architecture, not just wiring existing metrics into a new
UI element) and doing it "the right way" means:
- Establishing consistent terminology across the whole app first (prosody/pacing/tempo/
  accent-feature vocabulary is currently introduced ad hoc, panel by panel).
- Deciding where novice/expert disclosure boundaries live *before* scattering `{beginner,
  expert}` conditionals through components — this should be one shared mechanism, not a
  per-panel decision made five separate times under deadline pressure.
- Writing actual instructional content (tooltips, wizard copy, troubleshooting entries),
  which is a slower, iterative, review-heavy process unlike most of the mechanical work in
  the current branch.

Rushing this into an already-massive branch risks either shipping inconsistent half-measures
per-panel, or blocking the merge of otherwise-done prosody work on unrelated content design.
Recommendation: merge the current branch, then take this up as its own tracked initiative.

---

## 1. Progressive Disclosure Mode (Basic / Expert)

**Vision**: One shared mechanism for hiding/showing advanced controls, used consistently
across Voice Design, OmniVoice, Stitch Studio, and the Accent Workbench — instead of
per-component ad hoc simplification (which risks accidentally removing power-user
capability, the thing we explicitly want to avoid).

- **Technical Implementation Path**:
  - A single global `uiExperienceLevel: 'guided' | 'expert'` in `store.ts`, persisted
    (localStorage), toggle exposed in `AppShell.tsx`.
  - A shared `<Disclose level="expert">` wrapper component (or a `useExperienceLevel()` hook
    returning a boolean) used everywhere a control should be collapsed by default in guided
    mode — never conditionally *unmount* functionality, only collapse/hide behind a
    "Show advanced" affordance, so power users always have one click back to everything.
  - Default new users to `guided`; anyone who has previously touched an advanced control
    should probably default to `expert` on return (small heuristic, not required for v1).
- **Why**: This is the actual resolution to the stated tension (teach novices without
  stripping power users) — one seam, applied consistently, rather than a redesign per panel.

## 2. Contextual Tooltip & Plain-Language Metric Surfacing (near-term, cheap)

**Vision**: Reuse metrics the backend already computes and surface them in plain language at
the point of decision, rather than requiring the user to know what `speech_rate_proxy` or a
pause-ratio number means.

- **Current State**: `audio_style.analyze_reference()` already computes pause ratio, speech
  rate proxy, median/longest pause; `SegmentRackRow.tsx` already has a pacing-warning
  computation and regen cost estimate (this branch). None of it is explained in-app beyond a
  single warning string.
- **Technical Implementation Path**:
  - A small shared `MetricExplainer`/tooltip content map (metric key -> plain-language
    template), so "why is this shown" text lives in one place instead of being duplicated
    per component.
  - Extend existing warning/estimate UI (pacing warning, regen cost, cancellation status) with
    a `(?)` affordance that opens the explainer rather than writing new UI chrome.
- **Why**: Lowest engineering cost of everything in this doc — the data already exists, this
  is purely a presentation/content layer. Good first slice to pick up.

## 3. Automated Artifact / Problem Diagnostics

**Vision**: Instead of a static "troubleshooting" document the user has to go read, detect
known failure signatures from metrics already computed and surface an inline, actionable
suggestion at the point of failure.

- **Technical Implementation Path**:
  - A `diagnose_take(metrics, audio_stats) -> list[Diagnosis]` pass (backend, likely in
    `audio_style.py` or a new `audio_diagnostics.py`) that flags known patterns: clipping
    (peak/RMS ratio), unnatural pacing (already have the proxy), long dead air outliers,
    excessive pause count from VAD, accent-feature coverage gaps (ties into the roadmap's
    §4.3 feature tagging).
  - Surface `Diagnosis[]` in generation/audition responses; render as inline chips near the
    affected take ("clipping detected — try lowering guidance" style), each linking to the
    matching troubleshooting KB entry (§5) for the "why."
- **Why**: This is the actual 2026-premium version of a troubleshooting doc — the app tells
  you what's wrong and what to try, instead of you diagnosing it yourself from a wiki page.
  Depends on §5 existing (as the deep-dive target) but can ship its own chip UI independently.

## 4. Guided Wizard for Persona Creation

**Vision**: A goal-oriented flow ("describe the agent/character you're building") that maps
answers to a starting parameter set (accent, delivery style, reference strategy), rather than
presenting a blank Voice Design panel with two dozen controls to a first-time user.

- **Technical Implementation Path**:
  - A new top-level flow (`PersonaWizardPage.tsx` or a modal sequence), asking a handful of
    plain questions (use case, target accent/region, energy/formality) and translating them
    into a starting `VoiceDesignPanel`/OmniVoice config — landing the user in the *existing*
    expert surfaces with sane defaults already applied, not a separate simplified engine.
  - Should route through the Accent Workbench's existing Route A/B/C decision (roadmap §4.1)
    for accent selection, since that logic already exists and shouldn't be duplicated.
  - Explicitly an on-ramp, not a replacement: "Skip wizard, go to full editor" must be one
    click away at every step.
- **Why**: Biggest lift in this doc (new flow, new copy, new design pass) and the most
  directly aimed at "no/limited knowledge" users from the stated vision. Should follow §1
  (progressive disclosure) since the wizard's whole point is handing off into the expert
  surface cleanly.

## 5. In-App Documentation / Troubleshooting KB / Glossary

**Vision**: A searchable, in-app reference — glossary of terms (prosody, tempo, accent
features, etc., reusing `accentBank.ts`'s existing `FEATURE_INFO` as a model), plus
troubleshooting entries for common audio problems (clipping, robotic cadence, accent drift,
stitching artifacts at cut boundaries).

- **Technical Implementation Path**:
  - Markdown-driven content (co-located in the repo, e.g. `frontend/src/content/help/*.md`),
    rendered in a slide-over panel accessible from anywhere (ties into roadmap §7.1's
    command palette — `⌘K` -> "Help: <topic>" is a natural entry point).
  - Glossary terms should be linkable from tooltips (§2) via a consistent term-ID scheme, so
    "prosody" in a tooltip can deep-link to its glossary entry instead of re-explaining inline.
  - Troubleshooting entries should be the link target for §3's diagnostic chips.
- **Why**: Lowest urgency of the five — highest value only once §2/§3 exist to link *into* it;
  building it standalone first risks writing content nobody discovers.

---

## Suggested Sequencing

1. **§2 Contextual tooltips** — cheap, reuses existing metrics, no new information
   architecture decisions required. Good first pickup.
2. **§1 Progressive disclosure mode** — one shared mechanism, unblocks doing §4 without
   re-litigating "hide vs. show" per component.
3. **§5 Glossary + troubleshooting KB** — content-heavy; can start in parallel with §1/§2
   once terminology is settled.
4. **§3 Automated diagnostics** — depends on §5 existing as the link target.
5. **§4 Guided wizard** — largest lift, depends on §1 for a clean expert hand-off; last.
