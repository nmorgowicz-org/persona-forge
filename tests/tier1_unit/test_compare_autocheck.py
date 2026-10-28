"""Compare auto-check: WER, speaker similarity, offline model lookup and the opt-in download job.

Nothing here loads a real model. The checker takes a stub transcriber/embedder, and the model
lookup runs against a fake Hugging Face cache laid out in ``tmp_path``.
"""

from __future__ import annotations

import io
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from persona_forge import compare_autocheck as ac

SR = 16000


def wav_bytes(samples: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, samples.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def tone(freq: float, seconds: float = 1.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def spectrum_embedder(samples: np.ndarray) -> np.ndarray:
    """A stub embedder: coarse log-magnitude spectrum. Same signal in, same vector out."""
    mag = np.abs(np.fft.rfft(samples))
    bins = np.array([b.sum() for b in np.array_split(mag, 32)])
    vec = np.log1p(bins)
    return vec / (np.linalg.norm(vec) or 1.0)


# --- normalisation and WER ---------------------------------------------------------------------


def test_normalisation_ignores_case_punctuation_and_digits_vs_words():
    ref = "Hello there. Your timer is set for ten minutes, and the kitchen lights are now on."
    heard = "Hello there, your timer is set for 10 minutes, and the kitchen lights are now on."
    assert ac.normalize_words(ref) == ac.normalize_words(heard)


def test_structured_text_matches_spoken_form():
    text = "Invoice AB-104 totals $1,234.56, due on the 23rd at 3:30 PM."
    spoken = (
        "invoice a b one oh four totals one thousand two hundred thirty four dollars and "
        "fifty six cents due on the twenty third at three thirty p m"
    )
    assert ac.normalize_words(text) == ac.normalize_words(spoken)


def test_apostrophes_and_curly_quotes_do_not_count_as_errors():
    assert ac.normalize_words("Don’t stop, it's fine!") == ac.normalize_words("dont stop its fine")


def test_a_time_written_with_a_period_and_am_pm_matches_the_colon_form():
    # Whisper writes "3.30 pm" for what the sample text writes as "3:30 PM".
    assert ac.normalize_words("at 3:30 PM.") == ac.normalize_words("at 3.30 pm.")
    assert ac.normalize_words("at 3:30 PM.") == ac.normalize_words("at 3:30 p.m.")


def test_a_decimal_without_am_pm_is_still_a_decimal():
    assert ac.normalize_words("it costs 3.30 total") == ["it", "costs", "three", "point", "three", "oh", "total"]


def test_spelled_out_letters_match_the_acronym_form():
    # The spoken form of "AB-104" starts with its letters one at a time; Whisper writes them together.
    assert ac.normalize_words("code AB-104")[:2] == ac.normalize_words("code AB 104")[:2] == ["code", "ab"]
    assert ac.normalize_words("U.S.A. rules") == ac.normalize_words("USA rules")
    # Known limit: the digits stay "one oh four" for "AB-104" but "one hundred four" for a bare
    # "AB 104", and a transcript cannot say which was meant, so that one word may count as an error.


def test_a_single_letter_word_alone_is_left_alone():
    assert ac.normalize_words("a cat and I") == ["a", "cat", "and", "i"]


def test_wer_identical_is_zero():
    result = ac.word_error_rate("the cat sat down", "The cat sat down.")
    assert result["wer"] == 0.0
    assert (result["substitutions"], result["deletions"], result["insertions"]) == (0, 0, 0)
    assert result["reference_words"] == 4


def test_wer_counts_each_error_kind():
    deletion = ac.word_error_rate("the cat sat down", "the cat down")
    assert deletion["wer"] == 0.25 and deletion["deletions"] == 1
    substitution = ac.word_error_rate("the cat sat down", "the dog sat down")
    assert substitution["wer"] == 0.25 and substitution["substitutions"] == 1
    insertion = ac.word_error_rate("the cat sat down", "the big cat sat down")
    assert insertion["wer"] == 0.25 and insertion["insertions"] == 1


def test_wer_can_exceed_one_and_empty_hypothesis_is_all_deletions():
    assert ac.word_error_rate("hi", "oh well hello there")["wer"] == 4.0
    silent = ac.word_error_rate("one two three", "")
    assert silent["wer"] == 1.0 and silent["deletions"] == 3


def test_wer_is_undefined_without_reference_words():
    assert ac.word_error_rate("", "anything")["wer"] is None
    assert ac.word_error_rate("...", "anything")["wer"] is None


# --- similarity --------------------------------------------------------------------------------


def test_cosine_basics():
    assert ac.cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(1.0)
    assert ac.cosine(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)
    assert ac.cosine(np.zeros(3), np.ones(3)) is None


def test_identical_signals_score_higher_than_different_ones(tmp_path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(wav_bytes(tone(220)))
    checker = ac.AutoChecker(stt=lambda x: "hello", embedder=spectrum_embedder, cache_dirs=[tmp_path])
    same = checker.check(wav_bytes(tone(220)), "hello", str(reference))
    different = checker.check(wav_bytes(tone(3000)), "hello", str(reference))
    assert same["similarity"] == pytest.approx(1.0, abs=1e-4)
    assert different["similarity"] is not None
    assert different["similarity"] < same["similarity"] - 0.05


# --- checker -----------------------------------------------------------------------------------


def test_check_reports_wer_and_transcript_and_notes_missing_similarity(tmp_path):
    checker = ac.AutoChecker(
        stt=lambda x: "Hello there, ten minutes.", embedder=spectrum_embedder, cache_dirs=[tmp_path]
    )
    result = checker.check(wav_bytes(tone(220)), "Hello there. Ten minutes.", None)
    assert result["wer"] == 0.0
    assert result["transcript"] == "Hello there, ten minutes."
    assert result["similarity"] is None
    assert any("cloned voice" in note for note in result["notes"])


def test_check_resamples_to_16k_before_the_models(tmp_path):
    seen = []
    checker = ac.AutoChecker(
        stt=lambda x: seen.append(len(x)) or "a", embedder=None, cache_dirs=[tmp_path]
    )
    checker.check(wav_bytes(tone(220, 1.0, 24000), 24000), "a", None)
    assert seen == [SR]


def test_unavailable_metric_is_null_with_a_note_never_a_made_up_score(tmp_path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(wav_bytes(tone(220)))
    # Whisper stub only; nothing for similarity and an empty cache, so it cannot load WavLM.
    checker = ac.AutoChecker(stt=lambda x: "hello", embedder=None, cache_dirs=[tmp_path / "empty"])
    result = checker.check(wav_bytes(tone(220)), "hello", str(reference))
    assert result["wer"] == 0.0
    assert result["similarity"] is None
    assert any("speaker" in note.lower() and "download" in note.lower() for note in result["notes"])


def test_nothing_available_raises_so_the_route_can_offer_the_download(tmp_path):
    checker = ac.AutoChecker(cache_dirs=[tmp_path / "empty"])
    with pytest.raises(ac.AutoCheckUnavailable):
        checker.check(wav_bytes(tone(220)), "hello", None)


def test_a_failing_transcriber_never_becomes_a_score(tmp_path):
    def broken(x):
        raise RuntimeError("decoder blew up")

    checker = ac.AutoChecker(stt=broken, embedder=None, cache_dirs=[tmp_path])
    result = checker.check(wav_bytes(tone(220)), "hello", None)
    assert result["wer"] is None and result["transcript"] is None
    assert any("could not" in note.lower() for note in result["notes"])


@pytest.mark.parametrize("data", [b"", b"not audio at all", b"RIFF0000WAVEfmt "])
def test_undecodable_audio_is_rejected(data, tmp_path):
    checker = ac.AutoChecker(stt=lambda x: "a", embedder=None, cache_dirs=[tmp_path])
    with pytest.raises(ValueError):
        checker.check(data, "a", None)


def test_overlong_clip_is_rejected(tmp_path):
    checker = ac.AutoChecker(stt=lambda x: "a", embedder=None, cache_dirs=[tmp_path])
    with pytest.raises(ValueError, match="too long"):
        checker.check(wav_bytes(np.zeros(int(ac.MAX_CLIP_SECONDS + 5) * SR, np.float32)), "a", None)


def test_second_check_while_one_runs_is_refused_not_queued(tmp_path):
    started, release = threading.Event(), threading.Event()

    def slow(x):
        started.set()
        release.wait(5)
        return "a"

    checker = ac.AutoChecker(stt=slow, embedder=None, cache_dirs=[tmp_path])
    first = threading.Thread(target=lambda: checker.check(wav_bytes(tone(220)), "a", None))
    first.start()
    assert started.wait(5)
    try:
        with pytest.raises(ac.AutoCheckBusy):
            checker.check(wav_bytes(tone(220)), "a", None)
    finally:
        release.set()
        first.join(5)


def test_reference_embedding_is_cached_per_file(tmp_path):
    reference = tmp_path / "ref.wav"
    reference.write_bytes(wav_bytes(tone(220)))
    calls = []

    def counting(x):
        calls.append(len(x))
        return spectrum_embedder(x)

    checker = ac.AutoChecker(stt=lambda x: "a", embedder=counting, cache_dirs=[tmp_path])
    checker.check(wav_bytes(tone(220)), "a", str(reference))
    checker.check(wav_bytes(tone(330)), "a", str(reference))
    assert len(calls) == 3  # two clips + the reference once


def test_unload_drops_loaded_models(tmp_path):
    checker = ac.AutoChecker(stt=lambda x: "a", embedder=None, cache_dirs=[tmp_path])
    checker.check(wav_bytes(tone(220)), "a", None)
    assert checker.unload() is False  # injected callables are not "loaded models"


# --- offline model lookup ----------------------------------------------------------------------


def fake_cache(root: Path, spec: ac.ModelSpec, revision: str, files: tuple[str, ...] | None = None) -> Path:
    snapshot = root / ("models--" + spec.repo.replace("/", "--")) / "snapshots" / revision
    snapshot.mkdir(parents=True)
    for name in files if files is not None else spec.files:
        (snapshot / name).write_bytes(b"x")
    return snapshot


def test_find_snapshot_needs_every_file(tmp_path):
    fake_cache(tmp_path, ac.WAVLM_SV, "abc", files=("model.safetensors",))
    assert ac.find_snapshot(ac.WAVLM_SV, [tmp_path]) is None
    full = fake_cache(tmp_path, ac.WHISPER_TINY_EN, "def")
    assert ac.find_snapshot(ac.WHISPER_TINY_EN, [tmp_path]) == full


def test_find_snapshot_prefers_the_pinned_revision_and_the_first_cache(tmp_path):
    app_cache, hf_default = tmp_path / "app", tmp_path / "hf"
    other = fake_cache(hf_default, ac.WAVLM_SV, "someother")
    pinned = fake_cache(hf_default, ac.WAVLM_SV, ac.WAVLM_SV.revision)
    assert ac.find_snapshot(ac.WAVLM_SV, [app_cache, hf_default]) == pinned
    in_app = fake_cache(app_cache, ac.WAVLM_SV, "appcopy")
    assert ac.find_snapshot(ac.WAVLM_SV, [app_cache, hf_default]) == in_app
    assert other.exists()


def test_status_never_touches_the_network_and_reports_sizes(tmp_path, monkeypatch):
    import huggingface_hub

    def no_network(*a, **k):  # pragma: no cover - only runs when the contract is broken
        raise AssertionError("status() must not download")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", no_network)
    checker = ac.AutoChecker(cache_dirs=[tmp_path])
    fake_cache(tmp_path, ac.WHISPER_TINY_EN, "x")
    status = {m["id"]: m for m in checker.models_status()}
    assert status["whisper-tiny-en"]["available"] is True
    assert status["wavlm-base-plus-sv"]["available"] is False
    assert status["wavlm-base-plus-sv"]["size_bytes"] == ac.WAVLM_SV.size_bytes > 300_000_000
    assert status["whisper-tiny-en"]["purpose"] == "word_error_rate"
    assert status["wavlm-base-plus-sv"]["purpose"] == "speaker_similarity"


# --- opt-in download job -----------------------------------------------------------------------


def wait_done(job: ac.DownloadJob, timeout: float = 5.0) -> dict:
    assert job.wait(timeout)
    return job.status()


def test_download_runs_only_when_started_and_fetches_pinned_revisions(tmp_path):
    calls = []

    def fetch(spec, cache_dir):
        calls.append((spec.repo, spec.revision, tuple(spec.files), cache_dir))

    job = ac.DownloadJob(cache_dir=tmp_path, fetch=fetch)
    assert job.status()["state"] == "idle" and calls == []
    assert job.start([ac.WHISPER_TINY_EN, ac.WAVLM_SV]) is True
    status = wait_done(job)
    assert status["state"] == "done"
    assert [c[:2] for c in calls] == [
        ("Systran/faster-whisper-tiny.en", ac.WHISPER_TINY_EN.revision),
        ("microsoft/wavlm-base-plus-sv", ac.WAVLM_SV.revision),
    ]
    assert all(c[3] == tmp_path for c in calls)
    assert status["step_count"] == 2


def test_download_failure_is_reported_in_plain_words(tmp_path):
    def fetch(spec, cache_dir):
        raise OSError("Temporary failure in name resolution")

    job = ac.DownloadJob(cache_dir=tmp_path, fetch=fetch)
    job.start([ac.WHISPER_TINY_EN])
    status = wait_done(job)
    assert status["state"] == "error"
    assert "internet" in status["error"].lower() or "network" in status["error"].lower()


def test_second_start_while_running_is_refused(tmp_path):
    release = threading.Event()

    def slow_fetch(spec, cache_dir):
        release.wait(5)

    job = ac.DownloadJob(cache_dir=tmp_path, fetch=slow_fetch)
    assert job.start([ac.WHISPER_TINY_EN]) is True
    try:
        assert job.start([ac.WAVLM_SV]) is False
    finally:
        release.set()
        wait_done(job)


def test_download_specs_pin_a_revision_and_state_a_size():
    for spec in (ac.WHISPER_TINY_EN, ac.WAVLM_SV):
        assert len(spec.revision) == 40 and spec.size_bytes > 1_000_000
    assert 70_000_000 < ac.WHISPER_TINY_EN.size_bytes < 90_000_000
    assert 380_000_000 < ac.WAVLM_SV.size_bytes < 430_000_000
