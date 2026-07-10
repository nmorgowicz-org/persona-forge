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

For Pocket TTS built-in voice route changes, add:

```bash
PYTHONPATH=.:src pytest tests/tier2_backend/test_app_voices.py -q
```
