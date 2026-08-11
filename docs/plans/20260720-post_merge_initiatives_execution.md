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

Line hints refreshed 2026-07-22 (D14/D15 + A4b insertion) — use the heading, not the number.

| Section / Phase | Line | Why it exists |
|---|---:|---|
| §1 Purpose & scope | 21 | The three initiatives, why bundled, ordering |
| §2 Research baseline | 49 | Current-state facts (deps, backend, capture, guided) — the source of truth for every phase |
| §3 Decision register | 149 | D1–D15 frozen decisions — do not reopen |
| §4 Global rules & invariants | 280 | Privacy, additive/no-CI, **§4.3 gate taxonomy**, **§4.4 task budget 60–80k**, context mgmt, **§4.5 docs-per-phase (D13)** |
| §5 Dependency & sequencing index | 340 | Phase order + what each depends on |
| §6 Initiative A (uv + accel) | 377 | |
| — Phase A1 (pyproject/uv config) | 379 | pocket-tts+omnivoice main, qwen-tts opt-in extra (D14) |
| — Phase A2 (uv sync proves real venv) | 456 | |
| — Phase A3 (docs + rewire, keep CI) | 494 | |
| — Phase A4 (TTS_DEVICE + OPENVINO_DEVICE seams) | 530 | |
| — Phase A4b (Qwen3-TTS engine-mode auto-select: pytorch vs openvino, IR-gated) | 581 | D9 addendum / D15 |
| — Phase A5 (accelerator guide + deferred paths) | 636 | |
| — Phase A6 (OmniVoice-iGPU **validated** findings + packaging design) | 688 | reference for A6a–A6g; not itself a task |
| — **A6.4a Detection model** (capability vs presence; torch-independent family selection) | 812 | **read before A6c/A6d/A7c** |
| — Phase A6a (OmniVoice device seam + auto fp64-emu) | 861 | |
| — Phase A6b (honest OMP=4 CPU baseline; measurement) | 888 | |
| — Phase A6c (gpu_family detection + describe_accelerator) | 897 | |
| — Phase A6d (accel-aware entrypoint: family + runtime env) | 927 | |
| — Phase A6e (first-boot per-family torch install) | 946 | |
| — Phase A6f (base-image libs + /dev/dri compose + A5 reconcile) | 968 | |
| — Phase A6g (int8 PTQ; deferred) | 989 | |
| — Phase A7 (persisted runtime config — header + D11 context) | 1003 | reference for A7a–A7d |
| — Phase A7a (persistence backend: runtime.json + startup layering) | 1024 | |
| — Phase A7b (API: source/lock/restart + reset/dry-run) | 1051 | |
| — Phase A7c (container coach: copy + card) | 1068 | |
| — Phase A7d (premium Runtime control surface; may split A7d/A7e) | 1091 | |
| §7 Initiative B (capture harness) | 1116 | |
| — Phase B1 (real-server spawn) | 1122 | |
| — Phase B2 (fixtures + seeding) | 1179 | |
| — Phase B3 (capture.mjs --real) | 1219 | |
| — Phase B4 (GIF helpers) | 1246 | |
| — Phase B5 (testids) | 1275 | |
| — Phase B6 (scenario catalog) | 1304 | |
| — Phase B7 (coverage doc + workflow) | 1350 | |
| §8 Initiative C (guided experience) | 1373 | |
| — Phase C1 (metric tooltips) | 1380 | |
| — Phase C2 (progressive disclosure) | 1417 | |
| — Phase C3 (glossary/KB) | 1455 | |
| — Phase C4 (take diagnostics) | 1489 | |
| — Phase C5 (persona wizard) | 1525 | |
| §9 Completion ledger | 1565 | |

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
- State: verified (2026-07-22) · Depends on: — · Read: comprehensive §2.1, §2.2, D2/D5/D14, Phase A1.
- Deliverable: `pyproject.toml` + `uv.lock` with `[tool.uv] environments = ["sys_platform ==
  'darwin'", "sys_platform == 'linux'"]`, transformers override, OmniVoice git pin;
  `requirements-dev.txt` + Dockerfile untouched. **D14 (2026-07-22):** `pocket-tts` + `omnivoice`
  are main deps (Persona Forge's two real levers); `qwen-tts` (+`einops`/`onnxruntime`/`sox`) moved
  to `[project.optional-dependencies] qwen-tts` — install with `uv sync --extra qwen-tts`. Shared
  transitive deps (torch/torchaudio/transformers/accelerate/librosa) stay main. `model.py`'s
  `from qwen_tts import Qwen3TTSModel` is now a **lazy import** inside the pytorch/openvino load
  branch, not module-level — required so a bare `uv sync` (pocket_tts-only) imports cleanly.
- Gates: `uv lock -p 3.13` + grep for `5.12.1` / `398b6113` + `! grep cu128` + `pocket-tts` resolves
  main + `qwen-tts` gated behind `extra == 'qwen-tts'` `[local-verifiable]` — all re-verified
  2026-07-22 after the D14 restructuring; 343/343 `tests/tier1_unit/` green; app import proven in a
  pocket_tts-only venv (no `qwen-tts` extra installed).
- Completion proof: lock committed with the override + git rev, zero `cu128`, D14 extra wiring
  confirmed; `git diff` shows no CI/Dockerfile change.

**A2 — uv sync proves a real-model venv**
- State: verified (2026-07-22) · Depends on: A1 · Read: comprehensive §2.2, Phase A2.
- Deliverable: `uv sync` yields an env that imports gunicorn/torch/transformers + the app and
  passes the pytest subset.
- Gates: import + pytest subset `[local-verifiable]`; MPS + app-import + real spawn `[escalate→device]`.
- Completion proof: `uv run` imports succeed; pytest subset green; model loads (device).

**A3 — docs + rewire capture prereq; CI intact**
- State: verified (2026-07-22) · Depends on: A2 · Read: comprehensive Phase A3, D3/D4.
- Deliverable: local-setup doc references `uv sync`; B1 precondition notes `uv sync`; no CI /
  `requirements-dev.txt` edits.
- Gates: CI-untouched + doc grep `[local-verifiable]`; clean-checkout `uv sync` reproduces `[escalate→device]`.
- Completion proof: setup doc; `git diff` clean of CI/requirements-dev; from-scratch sync works (device).

**A4 — runtime device seams (`TTS_DEVICE` + `OPENVINO_DEVICE`)** (axis a of D9)
- State: verified (2026-07-22) · Depends on: A2 · Read: comprehensive Phase A4, D9/D10; `model.py:46` +
  ~790/797, `omnivoice_engine.py:296`.
- Deliverable: `resolve_device()` helper — **auto-detect** default (cuda>xpu>mps>cpu), `TTS_DEVICE`
  (fallback `DEVICE`) forces; torch backend + OmniVoice (iff API accepts) wired; **`OPENVINO_DEVICE`
  (CPU/GPU/AUTO)** replaces the hardcoded OV `"CPU"` (~790/797) = the Intel iGPU knob, Qwen3-TTS OV
  backend only (D10); `/health` per-backend device. No `pyproject.toml` change.
- Gates: `resolve_device()`→cpu on no-GPU box + both seams grep `[local-verifiable]`; `TTS_DEVICE=mps`
  generate + OmniVoice device-kwarg + `OPENVINO_DEVICE=GPU` on a real iGPU `[escalate→device]` (iGPU deferred).
- Completion proof: auto-default + env overrides work; per-backend device in `/health`; OV seam wired
  (iGPU run deferred to device gate); no pyproject diff.

**A4b — Qwen3-TTS engine-mode auto-select (`pytorch` vs `openvino`)** (D9 addendum / D15)
- State: verified (2026-07-22) · Depends on: A4 · Read: comprehensive Phase A4b, D9 addendum, D14/D15;
  `presets.py::PRESETS[...]["backend"]`, `config.py::apply_preset_env`.
- Deliverable: `has_valid_export(preset)` filesystem check (does the preset's `main_stateful_model`
  IR actually exist on disk); `apply_preset_env`'s preset-backend fallback becomes
  `"openvino" if has_valid_export(preset) else "pytorch"` — **never** auto-triggers
  `scripts/export.py`. Does not touch the product default (`TTS_BACKEND=pocket_tts` in
  `.env.example`, which still wins as an explicit var). `/health` reports why the fallback picked
  what it picked.
- Gates: no-IR-on-disk → `pytorch` fallback + `tests/tier1_unit/test_config.py` green
  `[local-verifiable]`; fallback flips to `openvino` against a real exported IR `[escalate→device]`.
- Completion proof: no-export hosts unchanged (`pytorch`); real export flips fallback to
  `openvino`; explicit `TTS_BACKEND` always wins; docs updated (D13); no pyproject diff.

**A5 — accelerator install guide + deferred paths (docs, not code)** (axis b of D9)
- State: verified (2026-07-22) · Depends on: A2, A4b · Read: comprehensive Phase A5, D2/D9/D10.
- Deliverable: dev-setup doc gains the out-of-box matrix (mac cpu+mps / linux cpu+cuda-auto / **linux
  ~5.5 GB caveat** / Intel-iGPU-via-OpenVINO) + the deferred-path map (slim-CPU/ROCm/XPU blocked by
  OmniVoice's cu128 source — `UV_TORCH_BACKEND` overruled, validated — + the OmniVoice-source escape
  hatch). **No pyproject extras** (deferred, D9).
- Gates: accel-guide grep + `git diff` shows no pyproject churn `[local-verifiable]`; iGPU OpenVINO
  enumeration on real hardware `[escalate→device]` (deferred; plexxie has the runtime).
- Completion proof: dev doc has matrix + 5.5 GB caveat + iGPU note + deferred map; no pyproject
  extras; no CI/Dockerfile diff.

### Initiative A — accelerator packaging (A6a–A6g) + runtime config (A7a–A7d)

Phase A6 (comprehensive §6, "OmniVoice iGPU acceleration") is **validated findings + design**, not a
task — read A6.1–A6.4 as reference before A6a–A6f. Each card below is one task, sized to the §4.4
budget (60–80k). Sequencing: A6a←A4; A6c independent; A6d←A6a,A6c; A6e←A6d; A6f←A6d; A6b/A6g
independent; A7a first (no new deps), A7b←A7a, A7c←A6c,A7b, A7d←A7b,A6c(,C1/C2).

**A6a — OmniVoice device seam + auto fp64-emu env** `[code]`
- Depends on: A4 · Read: comprehensive Phase A6a, A6.2, D10/D11; `omnivoice_engine.py:296/298`, `device.py`.
- Deliverable: `xpu_needs_fp64_emulation()` + `apply_fp64_emulation_env()` in `device.py`; OmniVoice
  `.to(device)` at :296 with emu-env-before-load for fp64-less xpu; CPU fallback warns; device in health.
- Gates: import + no-xpu cpu default + emu-env unit `[local-verifiable]`; plexxie load+generate with auto-emu `[escalate→device]`.
- Completion proof: helpers import; cpu path unchanged; unit green; plexxie generates without manual export.

**A6b — honest CPU baseline (OMP=4) + dtype re-confirm** `[measure]`
- Depends on: A6a (device) · Read: comprehensive Phase A6b, A6.3.
- Deliverable: `OMP_NUM_THREADS=4` CPU RTF on plexxie; A6.3 ratio corrected.
- Gates: all `[escalate→device]`. · Completion proof: A6.3 shows OMP=4 RTF + honest ratio; seed/text recorded.

**A6c — gpu_family detection module** `[code]`
- Depends on: — · Read: comprehensive **A6.4a (detection model — read first)**, Phase A6c, A6.4, D9/D11.
- Deliverable: `gpu_family.py::resolve_gpu_family()` (**torch-independent** probes — device nodes +
  PCI vendor + CPU model; `GPU_FAMILY` override) + `describe_accelerator()` returning `present`/`capable`.
- Gates: unit table (5 branches) + forced `GPU_FAMILY=cpu` + **present∧¬capable** (torch-independent) `[local-verifiable]`; plexxie→intel-xpu/has_fp64=False `[escalate→device]`.
- Completion proof: module + unit table green; override works; family selection ignores torch.is_available; plexxie detection.

**A6d — accel-aware entrypoint: family + runtime env** `[infra]`
- Depends on: A6a, A6c · Read: comprehensive Phase A6d, A6.4(ii), D3/D9/D11; `Dockerfile`.
- Deliverable: `docker/entrypoint.sh` resolves family, exports per-family env (emu vars / `OPENVINO_DEVICE`), execs CMD; ENTRYPOINT wired; no torch install here.
- Gates: dry-run cpu (no emu) + xpu (emu+OV) `[local-verifiable]`; cpu container boots healthy `[escalate→device]`.
- Completion proof: entrypoint; cpu dry-run empty; xpu dry-run sets env; cpu boots healthy.

**A6e — first-boot per-family torch install (named volume)** `[infra]`
- Depends on: A6d · Read: comprehensive Phase A6e, A6.1, D3/D11; `Dockerfile` pip flow.
- Deliverable: entrypoint installs the family torch (+OmniVoice `--no-deps`) into a volume on first boot, marker-gated; cpu uses baked torch.
- Gates: cpu no-install + install idempotency `[local-verifiable]`; plexxie first-boot populates + generates `[escalate→device]`.
- Completion proof: cpu boots without install; second xpu boot skips; plexxie first-boot works.

**A6f — base-image libs + /dev/dri compose docs + A5 reconcile** `[infra+docs]`
- Depends on: A6d · Read: comprehensive Phase A6f, A6.1, A6.4, Phase A5 matrix; compose file.
- Deliverable: Intel compute-runtime + `libze1` layered in base; compose `/dev/dri`+`GPU_FAMILY` example; A5 matrix row corrected (OmniVoice-on-iGPU via torch-xpu, not "CPU only").
- Gates: `docker compose config` parses + A5 grep `[local-verifiable]`; base image builds `[escalate→device]`.
- Completion proof: compose parses; A5 corrected; base image builds.

**A6g — int8 PTQ exploration (deferred)** `[research]`
- Depends on: A6b · Read: comprehensive Phase A6g, A6.3.
- Gates: worth-it `[escalate→frontier]` + probe `[escalate→device]`. · Completion proof: written go/no-go with artifact + RTF deltas.

**A7a — persistence backend (runtime.json + startup layering)** `[code]`
- Depends on: — · Read: comprehensive Phase A7a, D11; `config.py::apply_preset_env`, `model.py:896/:968`, `app.py` `/runtime/config`.
- Deliverable: `runtime_store.py` (atomic, schema-versioned, corrupt-safe); `apply_persisted_config()` layering file>default after preset seed, skipping locked keys; env-lock registry; `apply_runtime_config(persist=True)` write-on-success.
- Gates: round-trip + corrupt-ignore + lock-respected + failed-reload-no-persist units `[local-verifiable]`; restart-survival `[escalate→device]`.
- Completion proof: store + unit suite; lock respected; non-persist on failure; restart survives.

**A7b — API: source/lock/restart + reset/dry-run** `[code]`
- Depends on: A7a · Read: comprehensive Phase A7b, D11; `model.py:896`, `app.py` `/runtime/config`, `api.ts:1162–1207`.
- Deliverable: per-key `{value,source,locked,restart_required}`; `/runtime/config/reset` + `dry_run`; `api.ts` types.
- Gates: state shape + reset revert + `npm run build` `[local-verifiable]`.
- Completion proof: state shape; reset behavior; build green.

**A7c — container coach: copy + card** `[decide-once]+frontend`
- Depends on: A6c, A7b · Read: comprehensive **A6.4a (present∧¬capable trigger)**, Phase A7c, A6.4, D8/D11; `RuntimeConfigPage.tsx`.
- Deliverable: markdown coach copy (D8, per-family passthrough snippets) + coach card shown on the
  **present∧¬capable** gap with compose snippet + re-detect (`describe_accelerator`); quiet on native.
- Gates: build + card-from-markdown + present∧¬capable-only render `[local-verifiable]`; copy `[decide-once]`; reads-clearly on iGPU-LXC `[escalate→device]`.
- Completion proof: markdown keys; card wiring; build; copy approved; screenshot.

**A7d — premium Runtime control surface (UX)** `[frontend]` (may split A7d/A7e)
- Depends on: A7b, A6c, (C1/C2) · Read: comprehensive Phase A7d, D7/D8/D11; `RuntimeConfigPage.tsx`.
- Deliverable: per-key source/lock badges + env-locked disable; live-vs-restart affordance; detected-accelerator panel; Basic/Expert disclosure (never unmount), tooltips via C1.
- Gates: build + wiring greps `[local-verifiable]`; Basic boundary `[decide-once]`; env-lock disable + never-unmount + panel in-browser `[escalate→device]`.
- Completion proof: badge/panel/disclosure wiring; build; boundary decided; in-browser confirmed.

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
