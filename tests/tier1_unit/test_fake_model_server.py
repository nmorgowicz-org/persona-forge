from __future__ import annotations

import types

from tests.fixtures.fake_runtime import FakeModelRuntime
from tests.ui.fixtures.fake_model_server import _patch_save_voice


def test_patch_save_voice_routes_app_module_to_fake_library():
    rt = FakeModelRuntime()
    app_module = types.SimpleNamespace(voice_library=types.SimpleNamespace())

    _patch_save_voice(app_module, rt)

    meta = app_module.voice_library.save_voice(
        b"fake wav",
        description="test voice",
        sample_text="hello",
        language="english",
        selections={"engine": "omnivoice"},
        source="OmniVoice",
    )

    assert meta["voice_id"] == "fake_voice_0"
    assert meta["source"] == "OmniVoice"
    assert app_module.voice_library.get_voice(meta["voice_id"]) == meta
    assert app_module.voice_library.get_voice_wav_bytes(meta["voice_id"]) == b"fake wav"
