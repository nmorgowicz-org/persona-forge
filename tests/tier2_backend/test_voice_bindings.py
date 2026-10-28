"""Binding status: (saved voice x engine) prepared state, keyed so an edit invalidates it."""

from __future__ import annotations

import io

import numpy as np
import pytest
import soundfile as sf

from persona_forge import speech_engines, voice_bindings, voice_library


def _wav(seed: int = 0, seconds: float = 1.0) -> bytes:
    rng = np.random.default_rng(seed)
    samples = (rng.standard_normal(int(24000 * seconds)) * 0.05).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, samples, 24000, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_library, "VOICE_LIBRARY_DIR", tmp_path / "voices")
    return tmp_path / "voices"


@pytest.fixture
def installed(monkeypatch):
    """Which pack engines count as installed; tests flip entries in this set."""
    present = {"kitten2", "pocket-lite", "phonon-31m", "kokoro"}
    monkeypatch.setattr(voice_bindings, "_is_installed", lambda engine_id: engine_id in present)
    monkeypatch.setattr(voice_bindings, "engine_revision", lambda engine_id: "rev-1")
    monkeypatch.setattr(
        voice_bindings, "_needs_transcript", lambda engine_id: engine_id == "kitten2"
    )
    voice_bindings.reset_jobs()
    return present


def _voice(text="hello there", seed=0):
    return voice_library.save_voice(
        _wav(seed), description="d", sample_text=text, language="English"
    )


def _binding(voice_id, engine_id):
    return next(b for b in voice_bindings.bindings_for_voice(voice_id) if b["engine"] == engine_id)


def _meta(voice_id):
    meta = voice_library.get_voice(voice_id)
    assert meta is not None
    return meta


def _prepare(voice_id, engine_id):
    voice_bindings.write_marker(voice_id, engine_id, voice_bindings.current_key(_meta(voice_id), engine_id))


def test_every_registered_engine_gets_a_binding_in_registry_order(library, installed):
    voice = _voice()

    ids = [b["engine"] for b in voice_bindings.bindings_for_voice(voice["voice_id"])]

    assert ids == [engine.id for engine in speech_engines.list_engines()]


def test_baseline_pocket_is_always_ready_for_a_saved_voice(library, installed):
    voice = _voice()

    pocket = _binding(voice["voice_id"], "pocket-tts")

    assert pocket["status"] == "ready" and pocket["installed"] is True
    assert pocket["can_prepare"] is False  # nothing to prepare; it clones per request as today


@pytest.mark.parametrize("engine_id", ["phonon-31m", "kokoro"])
def test_engines_that_cannot_clone_are_unsupported_with_the_reason(library, installed, engine_id):
    voice = _voice()

    binding = _binding(voice["voice_id"], engine_id)

    assert binding["status"] == "unsupported"
    assert binding["reason"] == "no local cloning"
    assert binding["can_prepare"] is False


def test_a_cloning_pack_needs_preparation_until_a_marker_is_written(library, installed):
    voice = _voice()

    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "needs_preparation"
    _prepare(voice["voice_id"], "pocket-lite")
    ready = _binding(voice["voice_id"], "pocket-lite")

    assert ready["status"] == "ready" and ready["prepared_at"] is not None
    assert ready["can_prepare"] is False


def test_an_engine_that_is_not_installed_says_so_and_cannot_prepare(library, installed):
    installed.discard("kitten2")
    voice = _voice()

    binding = _binding(voice["voice_id"], "kitten2")

    assert binding["status"] == "needs_preparation"
    assert binding["installed"] is False and binding["blocker"] == "engine_not_installed"
    assert binding["can_prepare"] is False


def test_changing_the_reference_audio_invalidates_every_binding(library, installed):
    voice = _voice()
    for engine_id in ("kitten2", "pocket-lite"):
        _prepare(voice["voice_id"], engine_id)
        assert _binding(voice["voice_id"], engine_id)["status"] == "ready"

    path = _meta(voice["voice_id"])["wav_path"]
    with open(path, "wb") as handle:
        handle.write(_wav(seed=9))

    assert _binding(voice["voice_id"], "kitten2")["status"] == "needs_preparation"
    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "needs_preparation"


def test_editing_the_transcript_invalidates_kitten_but_not_pocket_lite(library, installed):
    voice = _voice(text="the old words")
    for engine_id in ("kitten2", "pocket-lite"):
        _prepare(voice["voice_id"], engine_id)

    voice_library.update_voice(voice["voice_id"], sample_text="the new words")

    assert _binding(voice["voice_id"], "kitten2")["status"] == "needs_preparation"
    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "ready"


def test_a_new_engine_revision_invalidates_the_binding(library, installed, monkeypatch):
    voice = _voice()
    _prepare(voice["voice_id"], "pocket-lite")

    monkeypatch.setattr(voice_bindings, "engine_revision", lambda engine_id: "rev-2")

    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "needs_preparation"


def test_restoring_the_old_transcript_makes_the_old_marker_valid_again(library, installed):
    voice = _voice(text="same words")
    _prepare(voice["voice_id"], "kitten2")
    voice_library.update_voice(voice["voice_id"], sample_text="other words")
    assert _binding(voice["voice_id"], "kitten2")["status"] == "needs_preparation"

    voice_library.update_voice(voice["voice_id"], sample_text="same words")

    assert _binding(voice["voice_id"], "kitten2")["status"] == "ready"


def test_a_voice_without_a_transcript_is_blocked_for_kitten_only(library, installed):
    voice = _voice(text="")

    kitten = _binding(voice["voice_id"], "kitten2")
    lite = _binding(voice["voice_id"], "pocket-lite")

    assert kitten["status"] == "needs_preparation"
    assert kitten["blocker"] == "transcript_missing" and kitten["needs_transcript"] is True
    assert kitten["can_prepare"] is True  # preparing is how the transcript gets resolved
    assert lite["blocker"] is None and lite["needs_transcript"] is False


def _mark_asr(library, voice_id, severity):
    import json

    meta_path = library / voice_id / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["asr"] = {"severity": severity, "whisper_transcript": "something else"}
    meta_path.write_text(json.dumps(meta))


def test_a_transcript_the_speech_check_disagreed_with_is_flagged_for_confirmation(library, installed):
    voice = _voice(text="auto heard words")
    _mark_asr(library, voice["voice_id"], "warn")

    kitten = _binding(voice["voice_id"], "kitten2")

    assert kitten["blocker"] == "transcript_unreviewed"
    assert _binding(voice["voice_id"], "pocket-lite")["blocker"] is None  # no transcript needed


def test_confirming_or_typing_the_transcript_counts_as_the_review(library, installed):
    voice = _voice(text="auto heard words")
    _mark_asr(library, voice["voice_id"], "fail")
    assert _binding(voice["voice_id"], "kitten2")["blocker"] == "transcript_unreviewed"

    voice_library.update_voice(voice["voice_id"], sample_text="auto heard words")  # source: user

    assert _binding(voice["voice_id"], "kitten2")["blocker"] is None


def test_an_audio_quality_warning_alone_is_not_a_transcript_problem(library, installed):
    voice = _voice(text="fine words")
    import json

    meta_path = library / voice["voice_id"] / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["needs_review"] = True  # set by clipping / noise checks as well
    meta_path.write_text(json.dumps(meta))

    assert _binding(voice["voice_id"], "kitten2")["blocker"] is None


def test_job_states_show_as_preparing_then_failed_then_cleared_by_success(library, installed):
    voice = _voice()
    key = voice_bindings.current_key(_meta(voice["voice_id"]), "pocket-lite")

    voice_bindings.set_job(voice["voice_id"], "pocket-lite", "preparing", key=key)
    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "preparing"
    assert _binding(voice["voice_id"], "pocket-lite")["can_prepare"] is False

    voice_bindings.set_job(voice["voice_id"], "pocket-lite", "failed", key=key, error="worker died")
    failed = _binding(voice["voice_id"], "pocket-lite")
    assert failed["status"] == "failed" and failed["error"] == "worker died"
    assert failed["can_prepare"] is True  # retry

    _prepare(voice["voice_id"], "pocket-lite")
    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "ready"


def test_a_failure_belongs_to_the_inputs_it_failed_on(library, installed):
    voice = _voice(text="first")
    meta = _meta(voice["voice_id"])
    voice_bindings.set_job(
        voice["voice_id"], "kitten2", "failed",
        key=voice_bindings.current_key(meta, "kitten2"), error="boom",
    )
    assert _binding(voice["voice_id"], "kitten2")["status"] == "failed"

    voice_library.update_voice(voice["voice_id"], sample_text="second")

    assert _binding(voice["voice_id"], "kitten2")["status"] == "needs_preparation"


def test_markers_live_with_the_voice_and_go_when_it_is_deleted(library, installed):
    voice = _voice()
    _prepare(voice["voice_id"], "pocket-lite")
    assert (library / voice["voice_id"] / voice_bindings.MARKER_FILE).is_file()

    voice_library.delete_voice(voice["voice_id"])

    assert not (library / voice["voice_id"]).exists()


def test_a_variant_is_keyed_by_its_own_audio_not_its_parents(library, installed):
    voice = _voice()
    parent = voice["voice_id"]
    variant_wav = library / parent / "prosody_x.wav"
    variant_wav.write_bytes(_wav(seed=3))
    voice_library._save_variants_meta(
        parent, {"x": {"filename": "prosody_x.wav", "label": "x", "created_at": 0}}
    )
    variant_id = f"{parent}.x"
    _prepare(parent, "pocket-lite")

    assert _binding(parent, "pocket-lite")["status"] == "ready"
    assert _binding(variant_id, "pocket-lite")["status"] == "needs_preparation"


def test_a_corrupt_marker_file_means_not_prepared_instead_of_an_error(library, installed):
    voice = _voice()
    (library / voice["voice_id"] / voice_bindings.MARKER_FILE).write_text("{not json")

    assert _binding(voice["voice_id"], "pocket-lite")["status"] == "needs_preparation"


def test_all_bindings_covers_every_voice_without_hashing_twice(library, installed):
    first, second = _voice(seed=1), _voice(seed=2)
    _prepare(first["voice_id"], "pocket-lite")

    everything = voice_bindings.all_bindings()

    assert set(everything) == {first["voice_id"], second["voice_id"]}
    by_engine = {b["engine"]: b for b in everything[first["voice_id"]]}
    assert by_engine["pocket-lite"]["status"] == "ready"
    assert {b["engine"]: b["status"] for b in everything[second["voice_id"]]}["pocket-lite"] == (
        "needs_preparation"
    )


def _write_pack(root, requirements, version="1", revision=None):
    import json

    pack = root / "kitten2"
    pack.mkdir(exist_ok=True)
    manifest = {
        "id": "kitten2", "engine_id": "kitten2", "version": version, "label": "K",
        "description": "d", "runtime": "r", "provisioner": "kitten2",
        "requirements": requirements, "artifacts": [],
    }
    if revision:
        manifest["revision"] = revision
    (pack / "manifest.json").write_text(json.dumps(manifest))


def test_engine_revision_follows_the_packs_pins_and_is_empty_without_a_pack(tmp_path, monkeypatch):
    from persona_forge import engine_packs

    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    assert engine_packs.binding_revision("kitten2") == ""

    _write_pack(tmp_path, ["kittenml==1.0"])
    first = engine_packs.binding_revision("kitten2")
    assert first and first == engine_packs.binding_revision("kitten2")

    _write_pack(tmp_path, ["kittenml==1.1"])
    assert engine_packs.binding_revision("kitten2") != first
    _write_pack(tmp_path, ["kittenml==1.1"], revision="abc")
    assert engine_packs.binding_revision("kitten2") not in ("", first)


def test_runtime_variant_and_preparation_settings_invalidate_revision(tmp_path, monkeypatch):
    import json
    from persona_forge import engine_packs

    monkeypatch.setenv("ENGINE_PACKS_DIR", str(tmp_path))
    _write_pack(tmp_path, ["kittenml==1.0"])
    first = engine_packs.binding_revision("kitten2")
    path = tmp_path / "kitten2" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["runtime"] = "python-mlx"
    path.write_text(json.dumps(manifest))
    second = engine_packs.binding_revision("kitten2")
    assert second != first
    manifest["preparation_settings"] = {"reference_seconds": 10}
    path.write_text(json.dumps(manifest))
    assert engine_packs.binding_revision("kitten2") != second


def test_malformed_marker_entry_is_not_ready_or_an_error(library, installed):
    import json

    voice_id = _voice()["voice_id"]
    path = library / voice_id / voice_bindings.MARKER_FILE
    path.write_text(json.dumps({voice_id: ["broken"]}))
    assert _binding(voice_id, "pocket-lite")["status"] == "needs_preparation"
