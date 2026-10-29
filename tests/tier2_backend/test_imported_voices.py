"""Imported prepared voices (plan §4.1: untrusted input): validation, storage, provenance, removal.

The safetensors files here are built byte by byte, so the validator is tested against exactly the
shapes an attacker (or a corrupt download) could hand it.
"""

from __future__ import annotations

import hashlib
import json
import struct

import numpy as np
import pytest

from persona_forge import imported_voices, speech_engines
from persona_forge.kitten2_engine import InvalidVoice

SHAPE = (1, 512, 125)


def build(
    *,
    name="speaker_wavs",
    dtype="F32",
    shape=SHAPE,
    data=None,
    metadata=None,
    extra_tensors=None,
    entry_extra=None,
    offsets=None,
    trailing=b"",
    header_override=None,
) -> bytes:
    count = int(np.prod(shape))
    payload = data if data is not None else (np.arange(count, dtype="<f4") / count).tobytes()
    entry = {"dtype": dtype, "shape": list(shape), "data_offsets": offsets or [0, len(payload)]}
    entry.update(entry_extra or {})
    header = {name: entry}
    header.update(extra_tensors or {})
    if metadata is not None:
        header["__metadata__"] = metadata
    raw = header_override if header_override is not None else json.dumps(header).encode()
    return struct.pack("<Q", len(raw)) + raw + payload + trailing


GOOD = build(metadata={"epoch": "300", "sig": "ba7a5a45"})


# -- file validation -------------------------------------------------------------------------------


def test_a_voice_shaped_like_the_shipped_ones_is_accepted_and_hashed():
    result = imported_voices.validate_bytes("phonon-31m", GOOD)

    assert result.sha256 == hashlib.sha256(GOOD).hexdigest()
    assert result.size == len(GOOD) and result.shape == SHAPE
    assert result.metadata == {"epoch": "300", "sig": "ba7a5a45"}


@pytest.mark.parametrize(
    ("label", "blob"),
    [
        ("pickle", b"\x80\x04\x95" + b"\x00" * 64 + b"cposix\nsystem\n"),
        ("zip/npz", b"PK\x03\x04" + b"\x00" * 200),
        ("empty", b""),
        ("too short", b"\x01\x02"),
        ("header longer than the file", struct.pack("<Q", 10_000) + b"{}"),
        ("header beyond the cap", struct.pack("<Q", 1 << 40) + b"{}"),
        ("header not json", build(header_override=b"not json at all")),
        ("header not an object", build(header_override=b"[1, 2, 3]")),
        ("header not utf-8", build(header_override=b"\xff\xfe{}")),
        ("wrong tensor name", build(name="embedding")),
        ("second tensor", build(extra_tensors={"extra": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}})),
        ("object-array dtype", build(dtype="O")),
        ("float16", build(dtype="F16")),
        ("int64", build(dtype="I64")),
        ("two dimensions", build(shape=(512, 125))),
        ("wrong channel count", build(shape=(1, 256, 125))),
        ("wrong frame count", build(shape=(1, 512, 64))),
        ("batch of two", build(shape=(2, 512, 125))),
        ("negative offset", build(offsets=[-4, 256000])),
        ("offsets that overrun", build(offsets=[0, 999_999_999])),
        ("offsets that do not cover the data", build(offsets=[0, 4])),
        ("trailing bytes", build(trailing=b"\x00" * 8)),
        ("truncated data", build(data=b"\x00" * 100)),
        ("tensor entry with extra keys", build(entry_extra={"path": "/etc/passwd"})),
        ("nan values", build(data=np.full(int(np.prod(SHAPE)), np.nan, dtype="<f4").tobytes())),
        ("infinite values", build(data=np.full(int(np.prod(SHAPE)), np.inf, dtype="<f4").tobytes())),
        ("absurd magnitude", build(data=np.full(int(np.prod(SHAPE)), 1e30, dtype="<f4").tobytes())),
        ("metadata with a non-string", build(metadata={"epoch": 300})),
        ("metadata that is not a map", build(metadata=["a"])),
        ("too many metadata keys", build(metadata={f"k{i}": "v" for i in range(40)})),
        ("oversized metadata value", build(metadata={"note": "x" * 5000})),
        ("metadata carrying a path", build(metadata={"source": "file:///etc/passwd"})),
        ("metadata carrying a url", build(metadata={"source": "https://example.com/x"})),
    ],
)
def test_untrusted_files_that_do_not_match_the_schema_are_rejected(label, blob):
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.validate_bytes("phonon-31m", blob)

    assert info.value.code == "invalid_voice_file", label
    assert info.value.status == 422


def test_a_file_over_the_size_limit_is_rejected_before_it_is_parsed():
    blob = GOOD + b"\x00" * imported_voices.MAX_FILE_BYTES

    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.validate_bytes("phonon-31m", blob)

    assert info.value.code == "file_too_large" and info.value.status == 413


def test_an_engine_without_a_pinned_schema_cannot_validate():
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.validate_bytes("kitten2", GOOD)

    assert info.value.code == "import_unsupported"


# -- names and filenames ------------------------------------------------------------------------------


@pytest.mark.parametrize("filename", ["voice.safetensors", "My Voice.SAFETENSORS", "a-b_c.1.safetensors"])
def test_the_extension_allowlist_accepts_safetensors_only(filename):
    assert imported_voices.check_filename(filename) == filename  # the provenance name, unchanged


@pytest.mark.parametrize(
    "filename",
    [
        "voice.pkl", "voice.pt", "voice.npz", "voice.bin", "voice.npy", "voice.safetensors.exe",
        "voice", "", ".safetensors", "../voice.safetensors", "dir/voice.safetensors",
        "C:\\voice.safetensors", "https://x.test/v.safetensors", "file:voice.safetensors",
        "vo\x00ice.safetensors",
    ],
)
def test_filenames_outside_the_allowlist_or_carrying_paths_are_rejected(filename):
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.check_filename(filename)

    assert info.value.code in {"bad_extension", "invalid_filename"}
    assert info.value.status == 400


@pytest.mark.parametrize(
    ("display", "slug"),
    [("Zoey copy", "imported-zoey-copy"), ("  Narrator 2  ", "imported-narrator-2"), ("a.b_c", "imported-a-b-c")],
)
def test_names_become_a_namespaced_slug(display, slug):
    assert imported_voices.slug_for(display) == slug


@pytest.mark.parametrize("display", ["", "   ", "x" * 41, "../etc", "a/b", "---", "é", "\x00"])
def test_unusable_names_are_rejected(display):
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.slug_for(display)

    assert info.value.code == "invalid_name" and info.value.status == 400


# -- store ------------------------------------------------------------------------------------------


class StubAdapter:
    def __init__(self, error=None):
        self.error = error
        self.imports: list[tuple[str, str]] = []
        self.forgotten: list[str] = []

    def import_voice(self, slug, path, sha256=None):
        if self.error is not None:
            raise self.error
        self.imports.append((slug, str(path)))

    def forget_imported(self, slug):
        self.forgotten.append(slug)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORTED_VOICES_DIR", str(tmp_path / "imported"))
    adapter = StubAdapter()
    monkeypatch.setitem(speech_engines.ADAPTERS, "phonon-31m", adapter)
    monkeypatch.setattr(imported_voices, "_is_installed", lambda engine_id: True)
    monkeypatch.setattr(imported_voices, "_engine_revision", lambda engine_id: "rev-1")
    monkeypatch.setattr(imported_voices, "_catalog_names", lambda engine_id: {"Zoey", "Juniper"})
    return tmp_path / "imported", adapter


def _import(name="Zoey copy", filename="zoey.safetensors", blob=GOOD):
    return imported_voices.import_voice("phonon-31m", filename=filename, data=blob, display_name=name)


def test_an_import_is_stored_under_the_app_data_dir_with_full_provenance(store):
    root, adapter = store

    record = _import()

    assert record["voice_id"] == "phonon:imported-zoey-copy"
    assert record["display_name"] == "Zoey copy" and record["slug"] == "imported-zoey-copy"
    assert record["source_filename"] == "zoey.safetensors"
    assert record["sha256"] == hashlib.sha256(GOOD).hexdigest() and record["size"] == len(GOOD)
    assert record["engine_revision"] == "rev-1" and record["engine"] == "phonon-31m"
    assert record["imported_at"].endswith("Z") or "+" in record["imported_at"]
    stored = root / "phonon-31m" / "imported-zoey-copy.safetensors"
    assert stored.read_bytes() == GOOD
    on_disk = json.loads((root / "phonon-31m" / "imported-zoey-copy.json").read_text())
    assert on_disk["sha256"] == record["sha256"] and on_disk["source_filename"] == "zoey.safetensors"
    assert adapter.imports == [("imported-zoey-copy", str(stored))]  # a path we built, not the user's


def test_the_users_filename_never_becomes_part_of_a_path(store):
    root, adapter = store

    _import(filename="weird name (1).SafeTensors")

    stored = sorted(p.name for p in (root / "phonon-31m").iterdir())
    assert stored == ["imported-zoey-copy.json", "imported-zoey-copy.safetensors"]
    assert all("weird" not in path for _, path in adapter.imports)


def test_listing_returns_imported_voices_in_name_order(store):
    _import("Beta")
    _import("Alpha")

    listed = imported_voices.list_imported("phonon-31m")

    assert [r["slug"] for r in listed] == ["imported-alpha", "imported-beta"]
    assert imported_voices.names("phonon-31m") == ["imported-alpha", "imported-beta"]


def test_an_engine_that_rejects_the_file_leaves_nothing_behind(store):
    root, adapter = store
    adapter.error = InvalidVoice("the engine could not read this voice")

    with pytest.raises(imported_voices.ImportRefused) as info:
        _import()

    assert info.value.code == "engine_rejected" and info.value.status == 422
    assert "could not read" in str(info.value)
    assert not (root / "phonon-31m").exists() or list((root / "phonon-31m").rglob("*")) == []
    assert imported_voices.list_imported("phonon-31m") == []


def test_an_engine_that_cannot_import_is_refused_with_a_reason(store):
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.import_voice("kitten2", filename="v.safetensors", data=GOOD, display_name="x")

    assert info.value.code == "import_unsupported" and info.value.status == 400
    assert "Kitten" in str(info.value) or "cannot import" in str(info.value)


def test_an_engine_that_is_not_installed_cannot_verify_a_file_so_refuses(store, monkeypatch):
    monkeypatch.setattr(imported_voices, "_is_installed", lambda engine_id: False)

    with pytest.raises(imported_voices.ImportRefused) as info:
        _import()

    assert info.value.code == "engine_not_installed" and info.value.status == 409


def test_a_second_import_under_the_same_name_is_refused(store):
    _import()

    with pytest.raises(imported_voices.ImportRefused) as info:
        _import(filename="other.safetensors")

    assert info.value.code == "name_taken" and info.value.status == 409


def test_a_name_that_slugs_onto_a_catalog_voice_is_still_namespaced(store):
    record = _import("Zoey")

    assert record["slug"] == "imported-zoey" and record["slug"] != "Zoey"


def test_validation_failure_stores_nothing_and_never_reaches_the_engine(store):
    root, adapter = store

    with pytest.raises(imported_voices.ImportRefused):
        _import(blob=b"\x80\x04 pickle")

    assert adapter.imports == []
    assert not (root / "phonon-31m").exists() or not any((root / "phonon-31m").iterdir())


def test_remove_deletes_both_files_and_tells_the_engine(store):
    root, adapter = store
    _import()

    removed = imported_voices.remove("phonon-31m", "imported-zoey-copy")

    assert removed is True
    assert list((root / "phonon-31m").iterdir()) == []
    assert adapter.forgotten == ["imported-zoey-copy"]
    assert imported_voices.remove("phonon-31m", "imported-zoey-copy") is False


@pytest.mark.parametrize("slug", ["../x", "imported-../x", "a/b", "Zoey", "imported-", "", "imported-A", "x" * 80])
def test_remove_only_accepts_a_slug_it_would_have_generated(store, slug):
    with pytest.raises(imported_voices.ImportRefused) as info:
        imported_voices.remove("phonon-31m", slug)

    assert info.value.code == "invalid_name"


def test_a_file_changed_after_import_is_not_served(store):
    root, _adapter = store
    _import()
    (root / "phonon-31m" / "imported-zoey-copy.safetensors").write_bytes(GOOD[:-4] + b"\x00\x00\x00\x00")

    assert imported_voices.names("phonon-31m") == []
    broken = imported_voices.list_imported("phonon-31m", include_broken=True)
    assert broken[0]["broken"] is True


def test_corrupt_provenance_is_skipped_not_fatal(store):
    root, _adapter = store
    _import()
    (root / "phonon-31m" / "imported-zoey-copy.json").write_text("{nope")

    assert imported_voices.list_imported("phonon-31m") == []


def test_serving_entries_are_the_paths_the_engine_loads_at_start(store):
    root, _adapter = store
    _import()

    # The worker re-verifies these on every load: the verified digest and the revision the
    # voice was prepared under travel with the path.
    assert imported_voices.serving_entries("phonon-31m") == [
        {
            "name": "imported-zoey-copy",
            "path": str(root / "phonon-31m" / "imported-zoey-copy.safetensors"),
            "sha256": hashlib.sha256(GOOD).hexdigest(),
            "engine_revision": "rev-1",
        }
    ]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"speaker_wavs":{"dtype":"F16","dtype":"F32","shape":[1,512,125],"data_offsets":[0,256000]}}',
        b'{"speaker_wavs":{"dtype":"F32","shape":[1,512,125],"data_offsets":[0,256000]},'
        b'"speaker_wavs":{"dtype":"F32","shape":[1,512,125],"data_offsets":[0,256000]}}',
        b'{"speaker_wavs":{"dtype":"F32","shape":[1,512,125],"data_offsets":[0,256000]},'
        b'"__metadata__":{"source":"file:/secret","source":"safe"}}',
        b' {"speaker_wavs":{"dtype":"F32","shape":[1,512,125],"data_offsets":[0,256000]}}',
    ],
)
def test_ambiguous_or_non_safetensors_json_headers_are_refused(raw):
    with pytest.raises(imported_voices.ImportRefused):
        imported_voices.validate_bytes("phonon-31m", build(header_override=raw))


@pytest.mark.parametrize("offsets", [[False, 256000], [0.0, 256000.0]])
def test_tensor_offsets_must_be_json_integers(offsets):
    with pytest.raises(imported_voices.ImportRefused):
        imported_voices.validate_bytes("phonon-31m", build(offsets=offsets))


@pytest.mark.parametrize("text", ["voices/a", r"C:\voices\a", "file:relative", r"voices\a", "https:example.test", "a\x00b"])
def test_metadata_cannot_carry_relative_windows_or_scheme_paths(text):
    with pytest.raises(imported_voices.ImportRefused):
        imported_voices.validate_bytes("phonon-31m", build(metadata={"source": text}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("engine", "kitten2"), ("slug", "../elsewhere"),
        ("voice_id", "phonon:Zoey"), ("display_name", []),
        ("source_filename", "/etc/voice.safetensors"), ("sha256", "not-a-digest"),
        ("size", True), ("size", 1), ("imported_at", "yesterday"),
        ("engine_revision", None), ("metadata", {"source": "file:/secret"}),
        ("schema", {"tensor": "speaker_wavs", "dtype": "F16", "shape": [1, 512, 125]}),
    ],
)
def test_invalid_record_fields_are_never_offered_or_passed_to_the_worker(store, field, value):
    root, _ = store
    _import()
    path = root / "phonon-31m" / "imported-zoey-copy.json"
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))

    assert imported_voices.names("phonon-31m") == []
    assert imported_voices.serving_entries("phonon-31m") == []


def test_revision_changes_make_imports_broken_without_rewriting_provenance(store, monkeypatch):
    root, _ = store
    _import()
    before = (root / "phonon-31m" / "imported-zoey-copy.json").read_bytes()
    monkeypatch.setattr(imported_voices, "_engine_revision", lambda engine_id: "rev-2")

    assert imported_voices.names("phonon-31m") == []
    assert imported_voices.serving_entries("phonon-31m") == []
    assert imported_voices.list_imported("phonon-31m", include_broken=True)[0]["broken"]
    assert (root / "phonon-31m" / "imported-zoey-copy.json").read_bytes() == before


def test_timestamp_preserving_tampering_is_not_hidden_by_the_audio_hash_cache(store):
    import os

    root, _ = store
    _import()
    assert imported_voices.names("phonon-31m") == ["imported-zoey-copy"]
    path = root / "phonon-31m" / "imported-zoey-copy.safetensors"
    stamp = path.stat()
    path.write_bytes(GOOD[:-4] + b"\0\0\0\0")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

    assert imported_voices.names("phonon-31m") == []


def test_replacing_both_the_file_and_its_hash_cannot_bypass_schema_validation(store):
    root, _ = store
    _import()
    base = root / "phonon-31m"
    malformed = b"not a prepared voice"
    (base / "imported-zoey-copy.safetensors").write_bytes(malformed)
    path = base / "imported-zoey-copy.json"
    record = json.loads(path.read_text())
    record.update(sha256=hashlib.sha256(malformed).hexdigest(), size=len(malformed))
    path.write_text(json.dumps(record))

    assert imported_voices.names("phonon-31m") == []


@pytest.mark.parametrize("suffix", [".json", ".safetensors"])
def test_symlinked_store_files_are_not_offered_even_when_the_contents_match(store, tmp_path, suffix):
    root, _ = store
    _import()
    path = root / "phonon-31m" / ("imported-zoey-copy" + suffix)
    outside = tmp_path / ("outside" + suffix)
    path.rename(outside)
    path.symlink_to(outside)

    assert imported_voices.names("phonon-31m") == []
    assert imported_voices.serving_entries("phonon-31m") == []


def test_symlinked_engine_directory_is_not_read_written_or_removed(store, tmp_path):
    root, _ = store
    _import()
    outside = tmp_path / "outside"
    (root / "phonon-31m").rename(outside)
    (root / "phonon-31m").symlink_to(outside, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in outside.iterdir()}

    assert imported_voices.names("phonon-31m") == []
    with pytest.raises(imported_voices.ImportRefused):
        _import("Other")
    with pytest.raises(imported_voices.ImportRefused):
        imported_voices.remove("phonon-31m", "imported-zoey-copy")
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == before


def test_duplicate_record_keys_do_not_choose_a_favorable_identity(store):
    root, _ = store
    _import()
    path = root / "phonon-31m" / "imported-zoey-copy.json"
    text = path.read_text()
    path.write_text('{"engine":"kitten2",' + text[1:])

    assert imported_voices.names("phonon-31m") == []


def test_catalog_name_collision_is_refused_before_registering_or_writing(store, monkeypatch):
    root, adapter = store
    monkeypatch.setattr(imported_voices, "_catalog_names", lambda engine_id: {"imported-zoey-copy"})

    with pytest.raises(imported_voices.ImportRefused) as exc:
        _import()

    assert exc.value.code == "name_taken"
    assert adapter.imports == []
    assert not (root / "phonon-31m").exists()


def test_record_commit_failure_forgets_an_already_registered_voice(store, monkeypatch):
    root, adapter = store
    write_atomic = imported_voices._write_atomic

    def fail_record(path, payload):
        if path.suffix == ".json":
            raise OSError("disk full")
        write_atomic(path, payload)

    monkeypatch.setattr(imported_voices, "_write_atomic", fail_record)
    with pytest.raises(OSError, match="disk full"):
        _import()

    assert imported_voices.names("phonon-31m") == []
    assert adapter.forgotten == ["imported-zoey-copy"]
    assert list((root / "phonon-31m").iterdir()) == []


def test_revision_changing_during_engine_acceptance_does_not_certify_the_new_revision(store, monkeypatch):
    _, adapter = store
    revision = ["rev-1"]
    monkeypatch.setattr(imported_voices, "_engine_revision", lambda engine_id: revision[0])
    original = adapter.import_voice

    def changed(slug, path, sha256=None):
        original(slug, path, sha256=sha256)
        revision[0] = "rev-2"

    monkeypatch.setattr(adapter, "import_voice", changed)
    with pytest.raises(imported_voices.ImportRefused):
        _import()

    assert imported_voices.names("phonon-31m") == []
    assert adapter.forgotten == ["imported-zoey-copy"]
