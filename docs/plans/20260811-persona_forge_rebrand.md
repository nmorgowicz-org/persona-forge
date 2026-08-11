# Persona Forge Rebrand — Execution Plan

- Status: execution authority once §2's decisions are treated as frozen (they were reached with
  Nick directly, 2026-08-11 — this doc is the record, not a proposal)
- Plan owner: Claude (Sonnet), brainstormed with Nick
- Execution owner: any implementing agent, one gated phase at a time — most phases are
  Haiku-executable given this doc's file:line specificity; phases 8-9 are Sonnet+Nick only
- Target branch: `feature/voice-style-foundation` (after Initiative A/B; before Initiative C —
  see `docs/plans/20260720-post_merge_initiatives.md`)
- Source snapshot: 2026-08-11

## Execution status

| Phase | Status | Evidence / gate |
|---|---|---|
| 0 — source-backed inventory | Not started | |
| 1 — Python module + package rename | Not started | |
| 2 — backend-default verification + doc correction (D12) | Not started | |
| 3 — environment variable identity | Not started | |
| 4 — this repo's Docker/Compose identity | Not started | |
| 5 — docs/README overhaul | Not started | |
| 6 — dev-deploy helper script | Not started | |
| 7 — final repo-side acceptance sweep | Not started | |
| 8 — GitHub repository rename | Not started | requires Nick, interactive |
| 9 — dockermisc1 host migration | Not started | requires Nick, interactive, sudo |

## 1. Purpose and execution contract

This plan coordinates the complete rename of this project from **Qwen3-TTS OpenVINO** /
`qwen3-tts-openvino` to **Persona Forge** / `persona-forge`. It covers Python package/module
identity, this repo's own Docker/Compose surface, environment variables, documentation, the
GitHub repository, and the dockermisc1 dev-deployment host (including its host-local data
directory, which is not tracked in this repo).

It deliberately does **not** borrow the migration-protocol machinery from the sibling
`llama-monitor` rebrand plan (`../llama-monitor/docs/plans/20260811-local_llm_foundry-rebrand.md`)
— that plan exists because Local LLM Foundry is a native desktop app with encrypted
application-root paths, an auto-updater, and existing external users whose data must survive a
migration. Persona Forge is a single-maintainer, currently-private, Dockerized web app with one
deployment host. There is no compatibility window to protect and no live user data migration
problem beyond one host-side directory (Phase 9). Scope is sized to match.

Rules for whoever executes a phase:

- Audit current source before editing. This doc's file:line citations are a 2026-08-11 baseline,
  not permission to assume the checkout is unchanged once earlier phases have landed — re-grep at
  the start of each phase.
- Do not combine phases whose owners differ (0-7 vs. 8-9) in one sitting.
- A phase is not complete because the edits exist; it is complete when its gate passes.
- Commit one phase at a time, matching this repo's existing convention of phase-scoped commits
  (see `f9031be`, `f967d0d`, `8588b78`).
- Stop and ask on a genuine decision fork or anything the phase's own risk notes flag — do not
  improvise around it.
- Do not rewrite historical prose in `docs/plans/*.md` that narrates past work using the old name
  (e.g. "the qwen3-tts capture harness" in a July dated entry). Only forward-looking / reference
  material gets renamed. History stays history.

## 2. Frozen decisions

Reached with Nick during brainstorming on 2026-08-11; authoritative unless he explicitly changes
them.

| Surface | Decision |
|---|---|
| Product name | **Persona Forge** (already live in the frontend `<title>`) |
| Canonical slug | `persona-forge` — GitHub repo, Docker image/container, compose project name, `pyproject.toml` `[project].name` |
| Python package/module | `src/persona_forge` (full internal rename from `src/qwen3_tts` — the product no longer centers on the Qwen3-TTS engine, which is now an opt-in extra alongside OmniVoice and pocket-tts, so locking the internal namespace to it "doesn't make technical sense," per Nick) |
| GitHub repository | `nmorgowicz-org/persona-forge` (currently private, single consumer — Nick, via dockermisc1) |
| Environment variable prefix | `PERSONA_FORGE_*` replacing `QWEN3_TTS_*` |
| Backward compatibility | **None.** Clean cutover, no aliases, no compat window. Private repo, single maintainer, single deployment host — there is no external consumer to protect. |
| Default TTS backend (D12) | pocket_tts as product default, OpenVINO opt-in. **Already implemented in code as of 2026-07-11 — see the correction in Phase 2.** This plan closes out the documentation gap, not a code change. |
| dockermisc1 data directory | Rename `/var/data/autopirate/qwen3-tts-new/` → `/var/data/autopirate/persona-forge/` (full clean rename, not left as legacy cruft — confirmed with Nick despite the higher effort of moving live model/voice data) |
| dockermisc1 host access | Nick confirmed passwordless sudo is available for Phase 9; use it carefully, one confirmed step at a time |
| Sequencing vs. Initiative C | This rebrand executes **before** resuming `docs/plans/20260720-post_merge_initiatives.md` Initiative C (guided-experience/teaching layer) — no sense building tooltips/docs that reference the old name right before erasing it |
| Dev-deploy convenience | Add `scripts/dev-deploy.sh` (Phase 6) to oneline the frontend-build + compose-merge steps Nick currently runs by hand on dockermisc1 |

Nothing else in this plan requires a decision from Nick before execution — everything below has a
worked-out default.

## 3. Source-backed inventory (2026-08-11 baseline)

A case-insensitive scan for `qwen3-tts` / `qwen3_tts` (excluding `.git`, `node_modules`, `.venv`,
`dist`, `build`) reaches **138 files**:

```
grep -rIli "qwen3-tts\|qwen3_tts" --exclude-dir=.git --exclude-dir=node_modules \
  --exclude-dir=.venv --exclude-dir=dist --exclude-dir=build .
```

Breakdown by category (re-derive the exact list at Phase 0 time — do not trust this count once
earlier phases have landed):

- **Python source** (`src/qwen3_tts/*.py`, 14 files) and **export tooling** (`src/export/*.py`,
  10 files) — import references, Phase 1.
- **Tests** (`tests/tier1_unit/*.py` ~24 files, `tests/tier2_backend/*.py` ~4 files,
  `tests/conftest.py`, `tests/fixtures/fake_runtime.py`, `tests/ui/fixtures/fake_model_server.py`)
  — import references, Phase 1.
- **Scripts** (`scripts/benchmark_aligner.py`, `scripts/diagnostics/codec_memory_report.py`,
  `scripts/download_model.py`, `scripts/export.py`, `scripts/patch_local_compat.py`,
  `scripts/validate_repo.py`, `scripts/entrypoint.sh`, `scripts/run-m4-on-dockermisc1.sh`) — mixed
  Phase 1 (import references) and Phase 3 (env vars).
- **Docs** (~50 files under `docs/`, plus `README.md`, `AGENTS.md`, `CHANGELOG.md`,
  `SECURITY.md`) — Phase 5.
- **Infra/CI** (`compose.yml`, `Dockerfile`, `.github/workflows/image.yml`,
  `.github/workflows/ci-ui.yml`, `.github/release-please/config.json5`,
  `.release-please-manifest.json`, `pyproject.toml`, `requirements/requirements-runtime.txt`,
  `.env.example`) — Phase 1/3/4.
- **Frontend residuals** (`frontend/src/lib/api.ts`, `frontend/src/lib/theme.ts`,
  `frontend/src/lib/voiceDesignExamples.ts`, `frontend/src/pages/IntegrationsPage.tsx`,
  `frontend/vite.config.ts`) — Phase 3/4.
- **Generated/lockfile** (`uv.lock`, `tests/ui/package-lock.json`) — regenerate, do not hand-edit.

### 3.1 Explicit exclusions — do NOT rename

These match the census but are not our identity to change:

- The upstream **`qwen-tts==0.1.1`** pip package name and its `qwen_tts` import path
  (`pyproject.toml:33-37`, `requirements/requirements-runtime.txt:4`, `Dockerfile:58,66-91`,
  `.github/workflows/image.yml:118`'s smoke-test import list). That is a third-party dependency we
  consume, not our product.
- HuggingFace model repo ids: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, `Qwen/Qwen3-TTS-12Hz-1.7B-Base`,
  `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` (`presets.py:50,64,98`,
  `frontend/src/lib/voiceDesignExamples.ts:8`) — Qwen's actual model names on the Hub.
- `.claude/settings.local.json` — local Claude Code tool-permission config, not a shippable
  surface. Any stale path patterns in it after Phase 1 are a session-hygiene matter, not a rebrand
  item.
- Historical prose in `docs/plans/*.md` narrating past work with the old name (per §1's rule).
- `uv.lock` / `package-lock.json` — regenerate via the normal tool (`uv lock`), never hand-edit.

### 3.2 Key non-mechanical findings

- `pyproject.toml:2` names the package `qwen3-tts-openvino`.
- `Dockerfile:124` hardcodes the gunicorn target `qwen3_tts.app:app`; `Dockerfile:120`'s
  `LABEL org.opencontainers.image.source` points at the current (pre-rename) GitHub URL.
- `compose.yml:1,31,34,41,54,112` name the compose project, service, container, image, and port
  env var after the old name.
- `.github/workflows/image.yml:15,25,74-75,123,133` and
  `.github/release-please/config.json5:25` drive the release tag pattern, image name, and
  release-please package-name — these three must change in lockstep with `pyproject.toml`'s name
  or release-please will desync from the actual package identity.
- `frontend/src/pages/IntegrationsPage.tsx:23` contains `model="qwen3-tts"` in an example curl
  snippet — **verify before renaming** whether `src/persona_forge/app.py`'s
  `/v1/audio/speech` handler validates or echoes a model-id string; if it's a live API contract
  value, the backend needs a symmetric change, not just the docs example (see R2 in §7).
- `.env.example:23-24` documents example data paths
  (`/var/data/autopirate/qwen3-tts/model`, `/var/data/autopirate/qwen3-tts/openvino`) that don't
  exactly match the real host path recorded in project memory
  (`/var/data/autopirate/qwen3-tts-new/...`) — treat the `.env.example` paths as illustrative, and
  the real host path as something to reconfirm live in Phase 9, not assume from either source.

## 4. Gate taxonomy

Reused from `docs/plans/20260720-post_merge_initiatives_execution.md` rather than inventing new
ceremony:

- `[local-verifiable]` — the executing agent can prove the gate itself (tests, grep, config
  validation) without leaving this checkout.
- `[decide-once]` — a judgment call already made in §2; the phase just needs to execute it
  consistently.
- `[escalate→device]` — requires action on real infrastructure outside this checkout (dockermisc1)
  and/or credentials the executing agent shouldn't hold unattended.

Phases 0-7 are `[local-verifiable]`. Phase 8 is `[escalate→device]` (GitHub account-level change).
Phase 9 is `[escalate→device]` (SSH + sudo on dockermisc1).

## 5. Phases

### Phase 0 — Source-backed inventory & baseline receipt `[local-verifiable]`

**Mission:** establish the authoritative file list before any edits.

**Tasks:**
1. Run the census command from §3 from repo root.
2. Save the resulting file list as this phase's evidence (paste it into the phase's commit
   message or a scratch note — it's the baseline every later phase's gate diffs against).
3. Confirm §3.1's exclusions still match reality (spot-check a few).

**Gate:** census command exits 0; file list captured.

### Phase 1 — Python module + package identity rename `[local-verifiable]`

**Mission:** rename the internal Python namespace so nothing shipped still says
`qwen3_tts`/`qwen3-tts`.

**Tasks:**
1. `git mv src/qwen3_tts src/persona_forge`.
2. Update every `import qwen3_tts` / `from qwen3_tts import ...` / `qwen3_tts.` reference across
   `src/`, `src/export/`, `tests/`, `scripts/*.py`, `scripts/entrypoint.sh` (its functional
   `python -c ...qwen3_tts.gpu_family...` invocation around line 32, plus the comment above it),
   `Dockerfile:6,124`, `.github/workflows/ci-ui.yml:9,71-72`, and
   `.github/workflows/image.yml:118`.
3. `pyproject.toml:2`: `name = "qwen3-tts-openvino"` → `name = "persona-forge"`. **Do not** touch
   the `qwen-tts` optional-dependency group (line 33) or its `qwen-tts==0.1.1` pin (line 37) — see
   §3.1.
4. Regenerate the lockfile: `uv lock`. Do not hand-edit `uv.lock`.

**Verification / gate:**
- `PYTHONPATH=src:. pytest tests/tier1_unit/ -q` fully green (baseline: 343/343 — confirm current
  count before asserting parity).
- `grep -rn "qwen3_tts" --include="*.py" .` returns zero hits.
- `python -c "import persona_forge"` succeeds from repo root with `PYTHONPATH=src`.

**Stop conditions:** any import error not already explained by a known transformers/torch pin
issue; any test failure absent from the pre-rename baseline; `uv lock`'s resolution drifting from
the previously-proven 120-package set (R6, §7) — stop and escalate rather than accept silently.

### Phase 2 — Backend-default verification + doc correction (D12) `[local-verifiable]`

**Mission:** confirm the OpenVINO→opt-in / pocket_tts→default swap and correct every doc/prose
reference that still describes OpenVINO as primary.

**Correction to the record:** contrary to the assumption both Nick and I were working from when
this phase was scoped, **the runtime default is already `pocket_tts`, not `openvino`** —
confirmed at `.env.example:20`, `compose.yml:61`, and `config.py`'s fallback logic (`model.py:53`'s
bare code-level fallback, used only when `TTS_BACKEND` isn't set at all, is `pytorch`, never
`openvino`). `presets.py`'s `PRESETS` dict `"backend": "pytorch"` values are unrelated — they pick
pytorch-vs-openvino *within* the Qwen engine, only relevant once `TTS_BACKEND=openvino` is
explicitly chosen. The one intentional exception is
`VOICE_DESIGN_PRESETS["1.7B"]["backend"] = "openvino"` (`presets.py:101`) — VoiceDesign never runs
on pocket_tts by design (guarded in `app.py`), so this is correct and must **not** change.

**Net effect: no code change in this phase.** This is documentation-only, plus fixing the two
stale project memories that recorded this as still-pending.

**Tasks:**
1. Rewrite `README.md`'s opening framing (currently "CPU-only Linux AMD64 container for Qwen3-TTS
   voice-cloning checkpoints, accelerated on Intel CPUs with OpenVINO") to lead with
   OmniVoice/pocket-tts as the primary engines, OpenVINO as an opt-in accelerator.
2. Sweep `docs/HOW_TO_RUN.md`, `docs/DEV_TEST_LOOP.md`, `docs/TEST_STRATEGY.md`,
   `docs/architecture/FRONTEND_OVERVIEW.md`, `docs/dev/architecture/OPENVINO_IMPLEMENTATION.md`,
   and the rest of §3's docs census for "OpenVINO is the default/primary backend" framing;
   correct to "opt-in accelerator."
3. Update the `persona-forge-rebrand` and `post-merge-initiatives-plan` project memories to
   record that D12's default-backend swap was already functionally complete as of 2026-07-11 —
   this phase only closed the documentation gap.

**Gate:** no doc describes OpenVINO as the default/primary backend; manual review of every
`grep -rn "backend.*default\|default.*backend" docs/ README.md` hit.

### Phase 3 — Environment variable identity `[local-verifiable]`

**Mission:** `QWEN3_TTS_*` → `PERSONA_FORGE_*`.

**Owned occurrences:** `compose.yml:34,54,112` (`QWEN3_TTS_IMAGE`, `QWEN3_TTS_PORT`),
`.github/workflows/ci-ui.yml:154` (`QWEN3_TTS_UI_URL`),
`frontend/src/pages/IntegrationsPage.tsx:9,20` (`$QWEN3_TTS_BASE_URL`),
`scripts/run-m4-on-dockermisc1.sh`, `tests/ui/fixtures/fake_model_server.py` (check for env refs).

**Before renaming `model="qwen3-tts"` (`IntegrationsPage.tsx:23`):** grep
`src/persona_forge/app.py`'s `/v1/audio/speech` handler for a hardcoded `"qwen3-tts"` model-id
check. If the backend validates or echoes that string, change it there too, symmetrically. If it's
purely an illustrative example value, rename freely.

**Tasks:** rename every `QWEN3_TTS_*` occurrence to `PERSONA_FORGE_*`. No back-compat aliases.

**Gate:** `grep -rn "QWEN3_TTS_"` zero hits repo-wide; `.github/workflows/ci-ui.yml` still valid
YAML; `docker compose -f compose.yml config` validates.

### Phase 4 — This repo's Docker/Compose identity `[local-verifiable]`

**Mission:** rename this repo's own Docker/Compose surface (not dockermisc1's host-side files —
that's Phase 9).

**Tasks:**
1. `compose.yml:1` `name: qwen3-tts-openvino` → `name: persona-forge`; `compose.yml:31` service
   key `qwen3-tts:` → `persona-forge:`; `compose.yml:41` `container_name: qwen3-tts` →
   `persona-forge`; `compose.yml:34,112` image default `qwen3-tts-openvino:local` →
   `persona-forge:local`; update surrounding comments referencing the old service name for
   consistency.
2. `Dockerfile:120` `LABEL org.opencontainers.image.source` → the target GitHub URL
   (`https://github.com/nmorgowicz-org/persona-forge`) — use the target URL now; GitHub's
   post-rename redirect (Phase 8) covers the transition window, so sequencing this before Phase 8
   is safe.
3. `Dockerfile:6` comment (`src/qwen3_tts/app.py` → `src/persona_forge/app.py`) and
   `frontend/vite.config.ts:6` (same reference).
4. `frontend/src/lib/theme.ts:4` localStorage key `'qwen3-tts-theme'` →
   `'persona-forge-theme'`. Note: this silently resets any existing browser's persisted theme
   preference on first load post-rebrand — acceptable, no migration needed given the no-back-compat
   decision.
5. `.env.example:23-24` example data paths → `/var/data/autopirate/persona-forge/...` to match
   Phase 9's real host rename.
6. `.github/workflows/image.yml:15,25,74-75,123` — `IMAGE_NAME` →
   `nmorgowicz-org/persona-forge`; release tag pattern `qwen3-tts-openvino-v*` →
   `persona-forge-v*`.
7. `.github/release-please/config.json5:25` `package-name` → `persona-forge`; update
   `.release-please-manifest.json`'s key to match (R5, §7 — these two files must move together or
   release-please desyncs).

**Gate:** `docker compose -f compose.yml config` validates cleanly; release-please config is valid
JSON5; a local `docker build` succeeds through both stages if this machine can run it — otherwise
defer the real build verification to Phase 9.

### Phase 5 — Docs/README overhaul `[local-verifiable]`

**Mission:** rewrite the remaining prose surface (~50 `docs/*.md` files, `README.md`, `AGENTS.md`,
`CHANGELOG.md`, `SECURITY.md`) so "qwen3-tts"/"Qwen3-TTS OpenVINO" no longer reads as the product
identity, while leaving §3.1's exclusions intact.

**Tasks:** work through Phase 0's census file list; for each docs hit, replace product-identity
mentions per §2's naming table; leave §3.1's exclusions and historical narrative (§1's rule)
untouched.

**Gate:** `grep -rIli "qwen3-tts\|qwen3_tts" docs/ README.md AGENTS.md CHANGELOG.md SECURITY.md`
returns only the explicitly-excluded historical/upstream references — build the expected-residual
list before running this phase so a fresh-context agent has a checklist, not a judgment call. This
is the most text-judgment-heavy phase in the plan; under-specifying it is the biggest risk to
Haiku-executability (R1, §7).

### Phase 6 — Dev-deploy helper script `[local-verifiable]`

**Mission:** `scripts/dev-deploy.sh` — oneline the frontend-build + compose-merge steps Nick
currently runs by hand on dockermisc1.

**Tasks:** create `scripts/dev-deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npm --prefix frontend run build
cd ~/docker
docker compose -f docker-compose.yml -f docker-compose.persona-forge-dev.yml \
  up -d persona-forge --force-recreate
```

The compose filenames/service name here assume Phase 9 has already renamed the host-side files —
this script's *syntax* is verifiable now, but its real end-to-end run only happens as part of
Phase 9's gate. Document usage in `docs/dev/LOCAL_SETUP.md`.

**Gate:** `bash -n scripts/dev-deploy.sh` (or `shellcheck` if available) clean; executable bit set.

### Phase 7 — Final repo-side acceptance sweep `[local-verifiable]`

**Mission:** confirm phases 1-6 are consistent and complete before touching GitHub or
dockermisc1.

**Tasks:**
1. Re-run the Phase 0 census; diff against Phase 5's documented expected-residual list — anything
   unexpected outside that list is a bug in an earlier phase, not something to silently exclude
   here.
2. Full test suite green (`tier1_unit` at minimum; `tier2_backend` if runnable without live model
   weights).
3. `docker compose -f compose.yml config` validates.
4. Spot-check README/docs read coherently as "Persona Forge."

**Gate:** clean diff against the expected-residual list; tests green.

### Phase 8 — GitHub repository rename `[escalate→device]` — Sonnet + Nick, interactively

**Mission:** `nmorgowicz-org/qwen3-tts-openvino` → `nmorgowicz-org/persona-forge`.

**Tasks:**
1. `gh repo rename persona-forge --repo nmorgowicz-org/qwen3-tts-openvino` (GitHub auto-creates a
   redirect from the old name).
2. `git remote set-url origin https://github.com/nmorgowicz-org/persona-forge.git` locally.
3. Confirm `Dockerfile:120` / `image.yml`'s `IMAGE_NAME` (Phase 4) already point at the final URL.
4. Spot-check CI still runs green against the renamed repo (branch protection / required-check
   names carry over automatically on a GitHub rename, but verify).

**Gate:** `gh repo view nmorgowicz-org/persona-forge` succeeds; a fresh `git fetch` on the renamed
remote works; CI green on the next push.

**Why not Haiku:** this is an account-level, externally-visible-if-ever-made-public change.
Confirm explicitly before executing, per standing operating rules, even though the repo is
currently private.

### Phase 9 — dockermisc1 host migration `[escalate→device]` — Sonnet + Nick, interactively, sudo

**Mission:** bring the dev deployment host in line with the new naming, including the data
directory that isn't tracked in this repo.

**Preconditions:** Phases 1-8 complete; the renamed repo is pullable.

**Tasks — interactive, one confirmed step at a time:**
1. `ssh dockermisc1`.
2. Stop the running container:
   `cd ~/docker && docker compose -f docker-compose.yml -f docker-compose.qwen3-tts-dev.yml down qwen3-tts`.
3. **Before moving anything:** confirm the real data path live on the host (do not trust the
   memory-recorded `/var/data/autopirate/qwen3-tts-new/` or `.env.example`'s illustrative path —
   verify which is real). Check nothing else references it (`grep -rl "qwen3-tts-new" ~/docker`,
   check crontabs).
4. `sudo mv /var/data/autopirate/qwen3-tts-new /var/data/autopirate/persona-forge` (source path
   confirmed live in step 3, not assumed from any doc).
5. Update `~/docker/docker-compose.yml` (image tag, mount paths, any `qwen3-tts` service key) and
   rename `docker-compose.qwen3-tts-dev.yml` → `docker-compose.persona-forge-dev.yml`, updating its
   own internal service/image references and bind-mount source paths.
6. Re-point the host checkout: `~/projects/qwen3-tts-openvino` → `~/projects/persona-forge`
   (`git remote set-url` already done in Phase 8, so a directory `mv` + `git pull` is simpler than
   a fresh clone).
7. `git pull` to bring in Phases 1-7's commits.
8. Run `scripts/dev-deploy.sh` (Phase 6) to build the frontend and bring the container up under
   the new names.
9. Verify: health endpoint returns healthy; spot-check the Voice Library still sees the moved
   data.

**Gate:** container healthy under the new name/image, data directory intact at the new path,
`dev-deploy.sh` completes end to end.

**Rollback:** steps 2-6 are reversible by name (`mv` back, `git remote set-url` back) until step
8's first successful `--force-recreate`. This is exactly why step 4 must not proceed until step
3's check comes back clean — the data move is the one step in this whole plan that isn't trivially
reversible.

## 6. Ownership / sequencing

Strictly sequential, 0 → 9, even though phases 2-6 don't strictly depend on each other file-wise —
single-agent-at-a-time execution keeps each phase's diff reviewable and avoids cross-phase
conflicts (Phase 4 and Phase 6 both touch compose naming, for instance). Phases 0-7 can all be one
agent's session-to-session work. Phases 8-9 are a hard stop for that agent — hand off to Nick
directly.

## 7. Risk register

| # | Risk | Mitigation |
|---|---|---|
| R1 | Phase 5's docs sweep is the largest text-judgment surface in the plan; under-specifying it risks a Haiku executor missing files or over-eagerly rewriting §3.1 exclusions | Build the expected-residual grep list explicitly before running Phase 5; treat any unexpected diff in Phase 7 as a bug, not noise |
| R2 | `IntegrationsPage.tsx:23`'s `model="qwen3-tts"` might be a live API contract value, not just an example string | Explicit grep-before-rename instruction baked into Phase 3 |
| R3 | dockermisc1's actual data path may not match either source (memory vs. `.env.example`) | Phase 9 step 3 verifies live before the `sudo mv`, never assumes |
| R4 | GitHub repo rename (Phase 8) before content-phases land could leave a dangling `LABEL`/`IMAGE_NAME` pointing at the wrong repo | Strict sequencing — Phase 8 only after Phase 7's gate passes |
| R5 | `release-please` `package-name` change (Phase 4) desyncs from `.release-please-manifest.json` if only one file is updated | Phase 4 explicitly updates both together |
| R6 | `uv.lock` regeneration (Phase 1) could pull different transitive versions than the pinned 120-package resolution proven during Initiative A | Diff the new lock's resolution against the known-good baseline; stop and escalate on drift rather than accept silently |
| R7 | A silent missed import reference in Phase 1 only surfaces when that code path executes, if test coverage is incomplete | Phase 1's grep zero-hit gate plus running `tier2_backend` where feasible |

## 8. Acceptance checklist (whole plan)

- [ ] `grep -rIli "qwen3-tts\|qwen3_tts"` repo-wide returns only §3.1's documented exclusions
- [ ] Full test suite green
- [ ] `docker compose -f compose.yml config` valid; local image build succeeds (or verified via
      Phase 9's real build)
- [ ] GitHub repo renamed, CI green post-rename
- [ ] dockermisc1 container healthy under the new name/image/data path
- [ ] `scripts/dev-deploy.sh` works end to end on dockermisc1
- [ ] README/docs read coherently as "Persona Forge," no stray old-name mentions in user-facing
      prose outside historical records
- [ ] `persona-forge-rebrand` and `post-merge-initiatives-plan` memories updated to reflect
      completion (including the D12 correction from Phase 2)

## 9. Execution handoff

- Execute phases strictly in order.
- Re-run Phase 0's census at the start of every phase — this doc's file:line citations drift as
  earlier phases land; don't trust them blindly once phase 1+ has executed.
- Never combine a `[local-verifiable]` phase (0-7) with an `[escalate→device]` phase (8-9) in the
  same unattended session.
- One commit per phase.
- Stop and ask on any ambiguity — particularly R2 (Phase 3) and R3 (Phase 9).
- The naming table, backend-default framing, and no-back-compat policy (§2) are frozen; they are
  not open to re-litigation mid-execution. Only in-phase execution details are a judgment call.
- Once this plan's acceptance checklist (§8) is fully checked, resume
  `docs/plans/20260720-post_merge_initiatives.md` Initiative C (C1-C5) — its ledger tables also
  need a correction pass first: B1-B7 are marked "not started" in both that doc and its
  `_execution.md` companion despite being complete (`f967d0d`/`8588b78`); fix that before Initiative
  C work begins, so the ledger reflects reality.
