"""``/v1/audio/speech`` loudness normalisation across engines (plan §4.6 item 4)."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from persona_forge import kokoro_engine, speech_engines

SR = 24000


def _tone(rms: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (rms * np.sqrt(2.0) * np.sin(2 * np.pi * 220.0 * t)).astype("float32")


def _rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x.astype("float64"))))))


class _FixedAudio:
    """A stand-in adapter that returns a given clip, like an engine with its own output level."""

    def __init__(self, clip: np.ndarray):
        self.clip = clip

    def synthesize(self, text, language, **kwargs):
        return self.clip.copy(), SR, None


@pytest.fixture
def serving(rt, app_module, monkeypatch):
    monkeypatch.setattr(rt, "TTS_BACKEND", "pocket_tts")
    monkeypatch.setattr(app_module, "_generation_ready", lambda: True)
    monkeypatch.setattr(rt, "_service_started", True)
    monkeypatch.delenv("TTS_NORMALIZE_LOUDNESS", raising=False)
    monkeypatch.setattr(kokoro_engine, "is_installed", lambda root=None: True)


def _serve(monkeypatch, client, clip, **body):
    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: _FixedAudio(clip))
    payload = {"input": "hello", "response_format": "wav", **body}
    return client.post("/v1/audio/speech", json=payload)


def _decode(response) -> np.ndarray:
    audio, sr = sf.read(io.BytesIO(response.data), dtype="float32")
    assert sr == SR
    return audio


def test_two_engines_with_different_native_levels_land_within_a_decibel(client, serving, monkeypatch):
    pocket_like = _serve(monkeypatch, client, _tone(0.09))
    kitten_like = _serve(
        monkeypatch, client, _tone(0.2), model="kokoro", voice="kokoro:af_heart"
    )

    assert pocket_like.status_code == kitten_like.status_code == 200
    assert abs(_rms_db(_decode(pocket_like)) - _rms_db(_decode(kitten_like))) < 1.0
    assert pocket_like.headers["X-Loudness-Normalized"] == "true"
    assert kitten_like.headers["X-Loudness-Normalized"] == "true"
    assert "X-Loudness-Gain-Db" in kitten_like.headers


def test_pcm_from_a_batch_engine_is_normalised_too(client, serving, monkeypatch):
    response = _serve(
        monkeypatch, client, _tone(0.2), model="kokoro", voice="kokoro:af_heart", response_format="pcm"
    )

    pcm = np.frombuffer(response.data, dtype="<i2").astype("float32") / 32768.0
    assert response.status_code == 200
    assert _rms_db(pcm) == pytest.approx(-23.0, abs=0.3)


def test_request_field_opts_out_and_leaves_the_clip_untouched(client, serving, monkeypatch):
    clip = _tone(0.2)

    response = _serve(monkeypatch, client, clip, normalize_loudness=False)

    assert response.status_code == 200
    assert response.headers["X-Loudness-Normalized"] == "false"
    assert "X-Loudness-Gain-Db" not in response.headers
    assert _rms_db(_decode(response)) == pytest.approx(_rms_db(clip), abs=0.01)


def test_env_opt_out_applies_and_the_request_can_override_it(client, serving, monkeypatch):
    monkeypatch.setenv("TTS_NORMALIZE_LOUDNESS", "0")
    clip = _tone(0.2)

    off = _serve(monkeypatch, client, clip)
    on = _serve(monkeypatch, client, clip, normalize_loudness=True)

    assert off.headers["X-Loudness-Normalized"] == "false"
    assert _rms_db(_decode(off)) == pytest.approx(_rms_db(clip), abs=0.01)
    assert on.headers["X-Loudness-Normalized"] == "true"
    assert _rms_db(_decode(on)) == pytest.approx(-23.0, abs=0.3)


def test_non_boolean_normalize_loudness_is_rejected(client, serving, monkeypatch):
    response = _serve(monkeypatch, client, _tone(0.1), normalize_loudness="no")

    assert response.status_code == 400
    assert "normalize_loudness" in response.get_json()["error"]["message"]


def test_silent_audio_is_served_as_is(client, serving, monkeypatch):
    response = _serve(monkeypatch, client, np.zeros(2400, dtype="float32"))

    assert response.status_code == 200
    assert response.headers["X-Loudness-Normalized"] == "false"
    assert not np.any(_decode(response))


def test_a_hot_clip_does_not_clip_after_encoding(client, serving, monkeypatch):
    clip = np.clip(_tone(0.7), -1.0, 1.0)

    response = _serve(
        monkeypatch, client, clip, model="kokoro", voice="kokoro:af_heart", response_format="pcm"
    )

    pcm = np.frombuffer(response.data, dtype="<i2")
    assert np.abs(pcm.astype("int32")).max() < 32767 * 0.9


def test_streamed_pcm_is_not_normalised_and_says_so(client, serving, monkeypatch):
    class Streaming:
        def stream_pcm(self, text, language, **kwargs):
            yield b"\x01\x00" * 50

    monkeypatch.setattr(speech_engines, "adapter_for", lambda engine: Streaming())

    response = client.post(
        "/v1/audio/speech",
        json={"model": "pocket-lite", "input": "hi", "voice": "pocket-lite:jane", "response_format": "pcm"},
    )

    assert response.status_code == 200
    assert response.data == b"\x01\x00" * 50
    assert response.headers["X-Loudness-Normalized"] == "false"
