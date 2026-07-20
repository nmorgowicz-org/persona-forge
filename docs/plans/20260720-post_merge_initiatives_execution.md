# Post-Merge Initiatives — Execution Companion

| Field | Value |
|---|---|
| Created | 2026-07-20 |
| Purpose | Low-context phase router + checkpoint ledger |
| Authoritative specification | [`20260720-post_merge_initiatives.md`](./20260720-post_merge_initiatives.md) |
| Intended reader | A context-free implementing agent (Sonnet sub-agent **or** local Qwen3.6-27B) |
| Execution model | One phase per agent context; verify the phase gate before advancing |
| Product implementation status | Not started |

## Bootstrap prompt for a fresh agent

Give a fresh agent this document and the following instruction:

> Begin with the "First 15 minutes" procedure in
> `docs/plans/20260720-post_merge_initiatives_execution.md`. Read the referenced sections of the
> comprehensive plan (`20260720-post_merge_initiatives.md`) for the active phase only. Implement
> exactly one phase, satisfy its gate, and record the evidence in the ledger. Do not implement
> from this companion alone, do not skip a phase's preconditions, do not reopen a frozen decision
> (comprehensive §3), do not modify unrelated user work, and do not proceed past an
> `[escalate→frontier]` or user-authority gate without asking. When a gate is tagged
> `[escalate→device]`, run it on the real Mac (real model / real browser) or hand it back to Nick.

No conversation history from the planning session is required.

## 1. How to use these two documents

This companion is the **execution interface** (routing + checkpoints). The comprehensive plan is
the **source of truth** (requirements, source-code detail, decisions, invariants, exact gates).

**Do not implement from this companion alone.** It summarizes; it does not duplicate. Priority
when documents appear to conflict:

1. Current user (Nick) instruction.
2. Repository rules / security / platform constraints.
3. The comprehensive plan's exact phase section + its referenced decisions (§3) and facts (§2).
4. This companion's routing and ledger.
5. Older archived plans — including the two superseded `20260715-*` docs (delete them; they are
   fully folded into the comprehensive plan).

Stable Markdown headings are the authoritative references. The line hints in §3 are conveniences
captured 2026-07-20 and drift as the plan is edited — **never let a stale line number override a
heading's actual content**; re-grep if a hint looks wrong.

## 2. First 15 minutes for a context-free agent

1. Read this companion completely.
2. Inspect branch, `HEAD`, and worktree without changing files. Read the comprehensive plan's
   **§9 completion ledger** and this companion's **§4 ledger** to find the lowest phase not yet
   "Verified."
3. Read these comprehensive-plan sections before touching code:
   - §1 Purpose & scope, §2 Research baseline (the facts you'll rely on), §3 Decision register
     (frozen — do not reopen), §4 Global rules (esp. §4.3 gate taxonomy), §5 sequencing index.
4. Read **only the active phase's section** (§3 router below gives the exact heading + line hint).
   Do not read other phases — it wastes context.
5. Run the phase's **Preconditions** block verbatim. If a precondition fails, an earlier phase is
   incomplete — stop and report; do not guess forward.
6. Re-verify any drift-prone fact the phase depends on (routes, testid counts, schema) against
   live source per comprehensive §4.4.
7. Resolve every `[decide-once]` item the phase needs **before** writing code — ask Nick if it is
   not already settled in the plan. Do not let it be decided implicitly.
8. Implement the phase's "Do this" steps. Honor the phase Invariants.
9. Run the **Gate**. Close only the tags you are authorized to: `[local-verifiable]` yourself;
   `[decide-once]` once Nick has settled the value; `[escalate→device]` on the real Mac / browser
   or hand to Nick; `[escalate→frontier]` only with Nick's go-ahead (it spends quota).
10. Record evidence in the §4 ledger (files changed, pasted gate output, anything that diverged).
11. If your context is filling, checkpoint the ledger and stop — do not push through auto-compaction.

Do not begin at A1 merely because it changes files first — begin at the lowest **unverified** phase
whose dependencies (comprehensive §5) are green.

## 3. Navigation map (comprehensive plan)

Line hints captured 2026-07-20 — use the heading, not the number.

| Section / Phase | Line | Why it exists |
|---|---:|---|
| §1 Purpose & scope | 21 | The three initiatives, why bundled, ordering |
| §2 Research baseline | 49 | Current-state facts (deps, backend, capture, guided) — the source of truth for every phase |
| §3 Decision register | 149 | D1–D10 frozen decisions — do not reopen |
| §4 Global rules & invariants | 212 | Privacy, additive/no-CI, **§4.3 gate taxonomy**, context mgmt |
| §5 Dependency & sequencing index | 256 | Phase order + what each depends on |
| §6 Initiative A (uv) | 280 | |
| — Phase A1 (pyproject/uv config) | 282 | |
| — Phase A2 (uv sync proves real venv) | 359 | |
| — Phase A3 (docs + rewire, keep CI) | 397 | |
| — Phase A4 (TTS_DEVICE + OPENVINO_DEVICE seams) | 433 | |
| — Phase A5 (accelerator guide + deferred paths) | 484 | |
| §7 Initiative B (capture harness) | 536 | |
| — Phase B1 (real-server spawn) | 542 | |
| — Phase B2 (fixtures + seeding) | 599 | |
| — Phase B3 (capture.mjs --real) | 639 | |
| — Phase B4 (GIF helpers) | 666 | |
| — Phase B5 (testids) | 695 | |
| — Phase B6 (scenario catalog) | 724 | |
| — Phase B7 (coverage doc + workflow) | 770 | |
| §8 Initiative C (guided experience) | 793 | |
| — Phase C1 (metric tooltips) | 800 | |
| — Phase C2 (progressive disclosure) | 837 | |
| — Phase C3 (glossary/KB) | 875 | |
| — Phase C4 (take diagnostics) | 909 | |
| — Phase C5 (persona wizard) | 945 | |
| §9 Completion ledger | 985 | |

Refresh hints with:
```bash
grep -nE '^## |^### Phase' docs/plans/20260720-post_merge_initiatives.md
```

## 4. Phase router + checkpoint ledger

Each card: the minimum comprehensive-plan reading, the deliverable, the gate tags, and the
completion proof. The **full phase section remains mandatory reading** — the card is a router, not
a substitute. Update **State** and **Evidence** only after the gate is satisfied.

Gate-tag legend (comprehensive §4.3): `[local-verifiable]` = self-run, no quota; `[decide-once]` =
Nick settles once then it's local; `[escalate→device]` = real Mac/model/browser; `[escalate→frontier]`
= reasoning judgment, **spends quota**.

### Initiative A — uv local-dev migration

**A1 — pyproject.toml + uv config**
- State: not started · Depends on: — · Read: comprehensive §2.1, §2.2, D2/D5, Phase A1.
- Deliverable: `pyproject.toml` + `uv.lock` with `[tool.uv] environments = ["sys_platform ==
  'darwin'"]` (NO pytorch-cpu index split — see D2), transformers override, OmniVoice git pin;
  `requirements-dev.txt` + Dockerfile untouched.
- Gates: `uv lock -p 3.13` + grep for `5.12.1` / `398b6113` + `! grep cu128` `[local-verifiable]`;
  arm64 torch actually resolving/installing `[escalate→device]`. The resolver conflict is already
  de-risked (frontier probe 2026-07-20: 120 pkgs green) — no open `[escalate→frontier]` here.
- Completion proof: lock committed with the override + git rev, zero `cu128`; `git diff` shows no
  CI/Dockerfile change.

**A2 — uv sync proves a real-model venv**
- State: not started · Depends on: A1 · Read: comprehensive §2.2, Phase A2.
- Deliverable: `uv sync` yields an env that imports gunicorn/torch/transformers + the app and
  passes the pytest subset.
- Gates: import + pytest subset `[local-verifiable]`; MPS + app-import + real spawn `[escalate→device]`.
- Completion proof: `uv run` imports succeed; pytest subset green; model loads (device).

**A3 — docs + rewire capture prereq; CI intact**
- State: not started · Depends on: A2 · Read: comprehensive Phase A3, D3/D4.
- Deliverable: local-setup doc references `uv sync`; B1 precondition notes `uv sync`; no CI /
  `requirements-dev.txt` edits.
- Gates: CI-untouched + doc grep `[local-verifiable]`; clean-checkout `uv sync` reproduces `[escalate→device]`.
- Completion proof: setup doc; `git diff` clean of CI/requirements-dev; from-scratch sync works (device).

**A4 — runtime device seams (`TTS_DEVICE` + `OPENVINO_DEVICE`)** (axis a of D9)
- State: not started · Depends on: A2 · Read: comprehensive Phase A4, D9/D10; `model.py:46` +
  ~790/797, `omnivoice_engine.py:296`.
- Deliverable: `resolve_device()` helper — **auto-detect** default (cuda>xpu>mps>cpu), `TTS_DEVICE`
  (fallback `DEVICE`) forces; torch backend + OmniVoice (iff API accepts) wired; **`OPENVINO_DEVICE`
  (CPU/GPU/AUTO)** replaces the hardcoded OV `"CPU"` (~790/797) = the Intel iGPU knob, Qwen3-TTS OV
  backend only (D10); `/health` per-backend device. No `pyproject.toml` change.
- Gates: `resolve_device()`→cpu on no-GPU box + both seams grep `[local-verifiable]`; `TTS_DEVICE=mps`
  generate + OmniVoice device-kwarg + `OPENVINO_DEVICE=GPU` on a real iGPU `[escalate→device]` (iGPU deferred).
- Completion proof: auto-default + env overrides work; per-backend device in `/health`; OV seam wired
  (iGPU run deferred to device gate); no pyproject diff.

**A5 — accelerator install guide + deferred paths (docs, not code)** (axis b of D9)
- State: not started · Depends on: A2 · Read: comprehensive Phase A5, D2/D9/D10.
- Deliverable: dev-setup doc gains the out-of-box matrix (mac cpu+mps / linux cpu+cuda-auto / **linux
  ~5.5 GB caveat** / Intel-iGPU-via-OpenVINO) + the deferred-path map (slim-CPU/ROCm/XPU blocked by
  OmniVoice's cu128 source — `UV_TORCH_BACKEND` overruled, validated — + the OmniVoice-source escape
  hatch). **No pyproject extras** (deferred, D9).
- Gates: accel-guide grep + `git diff` shows no pyproject churn `[local-verifiable]`; iGPU OpenVINO
  enumeration on real hardware `[escalate→device]` (deferred; plexxie has the runtime).
- Completion proof: dev doc has matrix + 5.5 GB caveat + iGPU note + deferred map; no pyproject
  extras; no CI/Dockerfile diff.

### Initiative B — real-model capture harness

**B1 — real-server spawn** (Flask dev server, D1)
- State: not started · Depends on: A2 preferred (works on current venv) · Read: comprehensive §2.2,
  §2.3, D1, D6, §4.1, Phase B1.
- Deliverable: `tests/ui/run-real-server.mjs` (+ `lib/python.mjs`) spawns real backend on temp dirs,
  waits for `model_loaded: true`, prints URL + temp paths; fake tier untouched.
- Gates: fake tier healthy `[local-verifiable]`; real spawn + MODEL LOADED + temp-path privacy check `[escalate→device]`.
- Completion proof: files + device-gate output (MODEL LOADED, temp paths) + first-load time.

**B2 — fixtures + seeding**
- State: not started · Depends on: B1 · Read: comprehensive §2.3, §4.1, Phase B2.
- Deliverable: `generate-capture-fixtures.mjs` (one-time) → committed synthetic
  `tests/ui/fixtures/capture-data/`; `seedCaptureFixtures()` wired into `startRealServer`.
- Gates: fixtures present + size `[local-verifiable]`; endpoint counts match `[escalate→device]`;
  privacy review `[decide-once]`.
- Completion proof: fixture counts; KB; matching counts; privacy confirmed.

**B3 — capture.mjs --real**
- State: not started · Depends on: B1, B2 · Read: comprehensive §2.3, Phase B3.
- Deliverable: `--real`/`--model-size`/`--device` flags; `scenarioHome` runs real in one command;
  fake path byte-for-byte unchanged.
- Gates: fake path + artifact `[local-verifiable]`; real end-to-end run `[escalate→device]`.
- Completion proof: parseArgs/main diff; both runs pass; real wall-clock.

**B4 — GIF helpers**
- State: not started · Depends on: B3 · Read: comprehensive §2.3, Phase B4.
- Deliverable: `tests/ui/lib/gif.mjs` (captureFrames/framesToGif/cleanupFrames, array-arg ffmpeg);
  trivial GIF proven, frames cleaned up.
- Gates: all `[local-verifiable]` (fake-server smoke GIF).
- Completion proof: module + valid GIF + cleanup + smoke removed.

**B5 — testids** (demand-driven)
- State: not started · Depends on: B3 · Read: comprehensive §2.3, Phase B5.
- Deliverable: only the testids a B6 scenario needs; build passes after each.
- Gates: `npm run build` + grep `[local-verifiable]`.
- Completion proof: testids + file/line; build; which scenario each served.

**B6 — scenario catalog** (one scenario per agent)
- State: not started · Depends on: B3, B4, B5 · Read: comprehensive Phase B6 (catalog).
- Deliverable: incremental scenarios across Voice Library / Prosody / Stitch Studio / Accent-OmniVoice
  / GIFs; each registered in `--list-scenarios`; real waits only.
- Gates: artifact present + registered `[local-verifiable]`; the real capture run `[escalate→device]`;
  "does this feature exist / is it worth it" `[escalate→frontier]` where judgment is needed.
- Completion proof (phase): `--list-scenarios` spans all categories (minus deferred AlignmentCompareGif).

**B7 — coverage doc + workflow**
- State: not started · Depends on: B6 · Read: comprehensive Phase B7.
- Deliverable: `tests/ui/README.md` scenario list + documented review loop.
- Gates: README present `[local-verifiable]`; dry-run tweak→rebuild→recapture `[escalate→device]`.
- Completion proof: README; dry-run screenshot reflected the tweak.

### Initiative C — guided experience (independent of A/B)

**C1 — metric tooltips**
- State: not started · Depends on: — · Read: comprehensive §2.4, D8, Phase C1.
- Deliverable: `metricExplainers.ts` content map + `MetricExplainer` component wired into
  `SegmentRackRow.tsx`.
- Gates: build + files + wiring `[local-verifiable]`; plain-copy `[decide-once]`; reads-clearly `[escalate→device]`.
- Completion proof: map keys; explainer name; wiring; build; screenshot/description.

**C2 — progressive disclosure** (D7: never unmount)
- State: not started · Depends on: — (parallel with C1) · Read: comprehensive §2.4, D7, Phase C2.
- Deliverable: persisted `uiExperienceLevel` + `AppShell` toggle + one `<Disclose>` seam used in
  Voice Design + OmniVoice.
- Gates: build + store/seam greps `[local-verifiable]`; disclosure boundary `[decide-once]`;
  toggle/persist/never-unmount in-browser `[escalate→device]`.
- Completion proof: store field + helper; seam name + panels; build; never-unmount + persist confirmation.

**C3 — glossary/KB**
- State: not started · Depends on: C1 (link target) · Read: comprehensive §2.4, D8, Phase C3.
- Deliverable: markdown help content (`frontend/src/content/help/*.md`), slide-over panel,
  deep-linkable term-IDs, minimum term + 4 troubleshooting entries.
- Gates: build + `ls *.md` `[local-verifiable]`; copy `[decide-once]`; panel/search/deep-link `[escalate→device]`.
- Completion proof: term-ID scheme; entries; panel open path; deep-link demo; build.

**C4 — take diagnostics**
- State: not started · Depends on: C3 · Read: comprehensive §2.2, §2.4, Phase C4.
- Deliverable: backend `diagnose_take` (thresholded on existing metrics) + `Diagnosis[]` on
  responses + inline chips linking to C3 entries.
- Gates: pytest + build `[local-verifiable]`; thresholds `[decide-once]`; known-bad take shows chip `[escalate→device]`.
- Completion proof: diagnose_take location + patterns + thresholds; attach point; chip UI; test; build.

**C5 — persona wizard**
- State: not started · Depends on: C2 · Read: comprehensive §2.4, D7, Phase C5.
- Deliverable: `PersonaWizardPage` (or modal) mapping plain answers → starting config, handing off
  into the existing expert panel; reuses Route A/B/C; skip-to-editor at every step.
- Gates: build + file present `[local-verifiable]`; questions/copy `[decide-once]`; end-to-end
  hand-off + skip in-browser `[escalate→device]`.
- Completion proof: entry point; question→config mapping; hand-off; skip confirmation; build.

## 5. Ledger maintenance

- One row per phase (mirror comprehensive §9). Update **only after** the gate is satisfied for the
  tags you're authorized to close.
- For `[escalate→device]` / `[escalate→frontier]` gates you cannot close yourself, mark the phase
  "blocked: <tag>" and hand back to Nick rather than marking it verified.
- Record pasted gate output and files changed as evidence — a phase is not "Verified" without it.
