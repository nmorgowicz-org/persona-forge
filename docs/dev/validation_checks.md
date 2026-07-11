# Local Validation Checks

Use these before handing off feature work that touches backend or frontend code:

```bash
python scripts/validate_repo.py
git diff --check
npm run --prefix frontend check
```

For focused audio style and voice-library changes, add:

```bash
PYTHONPATH=.:src pytest tests/tier1_unit/test_audio_style.py tests/tier1_unit/test_voice_library.py -q
```

For output-polish (loudness/peak) changes, run the validation matrix — see
docs/dev/OUTPUT_POLISH_MATRIX.md for the invariants and metadata parity checks:

```bash
PYTHONPATH=.:src pytest tests/tier1_unit/test_output_polish_matrix.py -q
```

For Pocket TTS built-in voice route changes, add:

```bash
PYTHONPATH=.:src pytest tests/tier2_backend/test_app_voices.py -q
```

## Fake Runtime Parity

CI validation intentionally runs without real model weights and may skip
Torch-dependent tests. When production code adds or changes a model/runtime/app
surface, update the fake layer in the same change:

- `tests/fixtures/fake_runtime.py` for backend unit tests that replace
  `qwen3_tts.model`.
- `tests/ui/fixtures/fake_model_server.py` for API/UI flows that run the real
  Flask app.
- Targeted fake modules in tier-1 tests, such as
  `tests/tier1_unit/test_run_generate.py`, when importing production modules
  directly.

The fake should match the shape production code touches, including nested model
attributes, health/config fields, job progress fields, and backend-specific
metadata. Add or update a focused test that exercises the new fake surface before
relying on the broader CI suite.
