"""HTTP layer of the Compare auto-check: /compare/auto-check, /status and /install.

The checker and the download job are replaced by stubs built on the real classes, so the route code,
status codes and response shapes are the real ones while no model is loaded or downloaded.
"""

from __future__ import annotations

import io
import threading
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from persona_forge import compare_autocheck as ac


def wav(freq: float = 220.0, seconds: float = 1.0, sr: int = 16000) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    buf = io.BytesIO()
    sf.write(buf, (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32), sr, format="WAV")
    return buf.getvalue()


def spectrum(samples: np.ndarray) -> np.ndarray:
    mag = np.abs(np.fft.rfft(samples))
    vec = np.log1p(np.array([b.sum() for b in np.array_split(mag, 32)]))
    return vec / (np.linalg.norm(vec) or 1.0)


def form(**over):
    body = {"audio": (io.BytesIO(wav()), "clip.wav"), "text": "Hello there, ten minutes."}
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


@pytest.fixture
def stub(app_module, tmp_path, monkeypatch):
    """Install a checker with stand-in models and a download job with a recording fetch."""
    fetched: list[str] = []
    checker = ac.AutoChecker(
        stt=lambda x: "hello there 10 minutes", embedder=spectrum, cache_dirs=[tmp_path / "cache"]
    )
    job = ac.DownloadJob(cache_dir=tmp_path / "cache", fetch=lambda spec, cache: fetched.append(spec.id))
    monkeypatch.setattr(app_module.compare_autocheck, "get_checker", lambda: checker)
    monkeypatch.setattr(app_module.compare_autocheck, "get_download_job", lambda: job)
    checker.fetched, checker.job = fetched, job  # type: ignore[attr-defined]
    return checker


def post(client, **over):
    return client.post("/compare/auto-check", data=form(**over), content_type="multipart/form-data")


def test_check_returns_wer_transcript_and_the_disclaimer(client, stub):
    resp = post(client)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["wer"] == 0.0
    assert body["transcript"] == "hello there 10 minutes"
    assert body["similarity"] is None
    assert "never replaces your rating" in body["disclaimer"]
    assert any("cloned voice" in note for note in body["notes"])
    assert stub.fetched == []  # a check never downloads


def test_check_never_enters_the_inference_executor(client, stub, app_module):
    with patch.object(app_module.model.executor, "submit", side_effect=AssertionError("executor used")):
        assert post(client).status_code == 200


def test_check_with_a_reference_voice_returns_similarity(client, stub, app_module, tmp_path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(wav(220.0))
    with patch.object(
        app_module.voice_library, "get_voice", return_value={"voice_id": "vd_aabbccddeeff", "wav_path": str(reference)}
    ) as get_voice, patch.object(app_module.voice_library, "VOICE_LIBRARY_DIR", tmp_path):
        resp = post(client, reference_voice_id="vd_aabbccddeeff")
    get_voice.assert_called_once_with("vd_aabbccddeeff")
    assert resp.status_code == 200
    assert resp.get_json()["similarity"] == pytest.approx(1.0, abs=1e-3)


def test_unknown_reference_voice_is_404(client, stub, app_module):
    with patch.object(app_module.voice_library, "get_voice", return_value=None):
        resp = post(client, reference_voice_id="vd_000000000000")
    assert resp.status_code == 404
    assert resp.get_json()["error"]


def test_reference_audio_outside_the_voice_library_is_refused(client, stub, app_module, tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    outside = tmp_path / "elsewhere.wav"
    outside.write_bytes(wav(220.0))
    with patch.object(
        app_module.voice_library, "get_voice", return_value={"voice_id": "vd_aabbccddeeff", "wav_path": str(outside)}
    ), patch.object(app_module.voice_library, "VOICE_LIBRARY_DIR", library):
        resp = post(client, reference_voice_id="vd_aabbccddeeff")
    assert resp.status_code == 400


def test_reference_voice_without_audio_on_disk_is_400(client, stub, app_module, tmp_path):
    with patch.object(
        app_module.voice_library, "get_voice", return_value={"voice_id": "vd_aabbccddeeff", "wav_path": str(tmp_path / "gone.wav")}
    ), patch.object(app_module.voice_library, "VOICE_LIBRARY_DIR", tmp_path):
        resp = post(client, reference_voice_id="vd_aabbccddeeff")
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "over",
    [
        {"audio": None},
        {"text": None},
        {"text": "   "},
        {"text": "x" * 5001},
        {"audio": (io.BytesIO(b"definitely not audio"), "clip.wav")},
        {"audio": (io.BytesIO(b""), "clip.wav")},
    ],
)
def test_bad_input_is_400(client, stub, over):
    resp = post(client, **over)
    assert resp.status_code == 400
    assert resp.get_json()["error"]


def test_oversized_upload_is_413(client, stub, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_AUTOCHECK_MAX_UPLOAD", 1024)
    assert post(client, audio=(io.BytesIO(wav(seconds=2.0)), "clip.wav")).status_code == 413


def test_no_models_on_disk_is_409_with_the_download_offer(client, app_module, tmp_path, monkeypatch):
    empty = ac.AutoChecker(cache_dirs=[tmp_path / "nothing"])
    monkeypatch.setattr(app_module.compare_autocheck, "get_checker", lambda: empty)
    resp = post(client)
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "models_missing"
    assert {m["id"]: m["available"] for m in body["models"]} == {"whisper-tiny-en": False, "wavlm-base-plus-sv": False}
    assert all(m["size_bytes"] > 0 for m in body["models"])


def test_a_second_check_while_one_runs_is_429(client, app_module, tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(x):
        started.set()
        release.wait(5)
        return "a"

    checker = ac.AutoChecker(stt=slow, embedder=None, cache_dirs=[tmp_path])
    monkeypatch.setattr(app_module.compare_autocheck, "get_checker", lambda: checker)
    first = threading.Thread(target=lambda: app_module.app.test_client().post(
        "/compare/auto-check", data=form(), content_type="multipart/form-data"))
    first.start()
    assert started.wait(5)
    try:
        resp = post(client)
        assert resp.status_code == 429
        assert resp.get_json()["code"] == "busy"
    finally:
        release.set()
        first.join(5)


def test_status_lists_models_sizes_job_and_never_downloads(client, stub):
    body = client.get("/compare/auto-check/status").get_json()
    assert [m["id"] for m in body["models"]] == ["whisper-tiny-en", "wavlm-base-plus-sv"]
    assert body["models"][0]["available"] is True and body["models"][1]["available"] is True
    assert body["job"]["state"] == "idle"
    assert "never replaces your rating" in body["disclaimer"]
    assert stub.fetched == []


def test_install_downloads_only_what_is_missing_and_only_on_post(client, app_module, tmp_path, monkeypatch):
    fetched: list[str] = []
    checker = ac.AutoChecker(cache_dirs=[tmp_path / "cache"])
    job = ac.DownloadJob(cache_dir=tmp_path / "cache", fetch=lambda spec, cache: fetched.append(spec.id))
    monkeypatch.setattr(app_module.compare_autocheck, "get_checker", lambda: checker)
    monkeypatch.setattr(app_module.compare_autocheck, "get_download_job", lambda: job)
    client.get("/compare/auto-check/status")
    assert fetched == []
    resp = client.post("/compare/auto-check/install", json={"models": ["whisper-tiny-en"]})
    assert resp.status_code == 202 and resp.get_json()["started"] is True
    assert job.wait(5)
    assert fetched == ["whisper-tiny-en"]
    done = client.get("/compare/auto-check/status").get_json()["job"]
    assert done["state"] == "done"


def test_install_with_no_body_fetches_every_missing_model(client, app_module, tmp_path, monkeypatch):
    fetched: list[str] = []
    checker = ac.AutoChecker(cache_dirs=[tmp_path / "cache"])
    job = ac.DownloadJob(cache_dir=tmp_path / "cache", fetch=lambda spec, cache: fetched.append(spec.id))
    monkeypatch.setattr(app_module.compare_autocheck, "get_checker", lambda: checker)
    monkeypatch.setattr(app_module.compare_autocheck, "get_download_job", lambda: job)
    assert client.post("/compare/auto-check/install").status_code == 202
    assert job.wait(5)
    assert fetched == ["whisper-tiny-en", "wavlm-base-plus-sv"]


def test_install_refuses_unknown_ids_and_when_nothing_is_missing(client, stub):
    assert client.post("/compare/auto-check/install", json={"models": ["nope"]}).status_code == 400
    resp = client.post("/compare/auto-check/install", json={})
    assert resp.status_code == 409 and resp.get_json()["started"] is False
    assert stub.fetched == []
