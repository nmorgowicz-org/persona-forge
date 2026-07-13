# Local Validation Checks

Use these before handing off feature work that touches backend or frontend code:

```bash
python scripts/validate_repo.py
git diff --check
npm run --prefix frontend check
```

## Test Lanes

CI intentionally runs without Torch, model weights, or exported OpenVINO IR. Keep
that lane fake-only and make real-runtime coverage explicit in separate lanes.

```bash
# CI fake lane: no Torch, no weights, no IR.
PYTHONPATH=src:src/export python -m pytest -m "not slow and not requires_torch and not requires_model_weights and not requires_openvino_ir" -n auto --tb=short tests/tier1_unit tests/tier2_backend tests/tier3_api_integration
```

```bash
# Local or dockermisc1 Torch lane: real Torch-backed code, no model weights required unless separately marked.
PYTHONPATH=src:src/export python -m pytest -m "requires_torch and not requires_model_weights and not requires_openvino_ir" --tb=short tests/tier1_unit
```

```bash
# dockermisc1 model/runtime lane: real model artifacts and exported IR.
PYTHONPATH=src:src/export python -m pytest -m "requires_model_weights or requires_openvino_ir" --tb=short
```

## Focused Checks

For focused audio style and voice-library changes, add:

```bash
PYTHONPATH=.:src pytest tests/tier1_unit/test_audio_style.py tests/tier1_unit/test_voice_library.py -q
```

For output-polish changes, run the validation matrix from
`docs/dev/OUTPUT_POLISH_MATRIX.md`:

```bash
PYTHONPATH=.:src pytest tests/tier1_unit/test_output_polish_matrix.py -q
```

For Pocket TTS built-in voice route changes, add:

```bash
PYTHONPATH=.:src pytest tests/tier2_backend/test_app_voices.py -q
```

## Prosody alignment hardening

Phase 5 and later alignment changes must also run the real target-CPU p95 gate documented in
`docs/dev/PROSODY_HARDENING.md`. The command is intentionally separate from fake-only CI
because it requires the pinned ONNX weights and a representative, non-Git reference clip.

## Fake Runtime Parity

The CI fake lane validates product contracts without real inference. When
production code changes a model, runtime, or app surface, update the fake layer
in the same change:

- `tests/fixtures/fake_runtime.py` backs unit and backend tests that replace
  `qwen3_tts.model`.
- `tests/ui/fixtures/fake_model_server.py` runs the real Flask app for API and
  UI flows.
- Targeted tier-1 fake modules, such as
  `tests/tier1_unit/test_run_generate.py`, import production modules directly.

The fake should match the production shape touched by the change, including
nested model attributes, health/config fields, job progress fields, and
backend-specific metadata. Add or update a focused fake-surface test before
relying on the broader CI suite.
