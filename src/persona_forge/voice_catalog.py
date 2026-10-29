"""Voice names and descriptions of the pack engines, bundled so they can be browsed before install.

An installed engine reports its own voice names (authoritative). This file adds what each engine's
data says about a voice (gender, accent, age, a description) and answers "what would I get?" for an
engine that is not installed, so the Built-in voices tab can list it with a "needs install" badge.
``engine_voice_catalog.json`` is generated from installed packs (``python -m
persona_forge.voice_catalog``) and a test compares it to any pack that is installed, so it cannot
quietly go stale.

``gender_source`` says how much to trust ``gender``:

- ``upstream``: the engine's own catalog states it (Phonon) or its voice-naming scheme does (Kokoro).
- ``name``: the voice name says so explicitly (Kitten ``NewsAnchorFemale``, ``GrandmaBedtimeStory``).
- ``estimated``: guessed from the median pitch of the voice's reference clip (Kitten, which ships no
  gender). It mislabels low female and high male voices, so the UI shows it as an estimate. Replace
  it with ``upstream`` data if Kitten ever publishes any.
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_FILE = Path(__file__).with_name("engine_voice_catalog.json")

GENERATED_ENGINES = ("kitten2", "phonon-31m", "kokoro", "pocket-lite")

# Median fundamental frequency that separates the two for adult speech. Female voices sit around
# 165-255 Hz and male around 85-155 Hz; the overlap is where an estimate goes wrong.
PITCH_SPLIT_HZ = 165.0

_ACCENTS = {"en-us": "American", "en-gb": "British", "en-au": "Australian", "en-ca": "Canadian", "en-in": "Indian"}
# Kokoro names read <language><gender>_<name>: a/b are American/British English, and the second
# letter is f or m for every language.
_KOKORO_ENGLISH = {"a": "en-us", "b": "en-gb"}
_KOKORO_GENDER = {"f": "female", "m": "male"}
_FEMALE_WORDS = {"female", "woman", "grandma", "grandmother", "mother", "girl", "lady"}
_MALE_WORDS = {"male", "man", "grandpa", "grandfather", "father", "boy", "gentleman"}


def accent_label(locale: str | None) -> str:
    """Readable accent for a locale code, or the code itself when it has no common name."""
    return _ACCENTS.get((locale or "").lower(), locale or "")


def split_camel(name: str) -> str:
    """``NewsAnchorFemale`` -> ``News Anchor Female``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)


def gender_from_name(name: str) -> str | None:
    """Gender only when a word of the voice name states it; ``None`` otherwise."""
    words = {word.lower() for word in split_camel(name).split()}
    female, male = bool(words & _FEMALE_WORDS), bool(words & _MALE_WORDS)
    if female == male:
        return None
    return "female" if female else "male"


def estimate_gender(wav_path: Path) -> str | None:
    """Median-pitch guess for a reference clip, or ``None`` when no steady voiced speech is found."""
    import librosa
    import numpy as np
    import soundfile

    audio, rate = soundfile.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != 16000:
        audio = librosa.resample(audio, orig_sr=rate, target_sr=16000)
    pitch = librosa.yin(audio, fmin=65, fmax=400, sr=16000, frame_length=1024)
    loudness = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    count = min(len(pitch), len(loudness))
    if count == 0:
        return None
    voiced = pitch[:count][loudness[:count] > 0.25 * np.median(loudness[:count])]
    voiced = voiced[(voiced > 70) & (voiced < 390)]
    if len(voiced) < 20:
        return None
    return "female" if np.median(voiced) >= PITCH_SPLIT_HZ else "male"


def _entry(name: str, language: str = "en", **fields: str) -> dict[str, str]:
    entry = {"name": name, "language": language}
    entry.update({key: value for key, value in fields.items() if value})
    return entry




def _build_phonon() -> list[dict[str, str]]:
    from persona_forge import phonon_engine

    directory = phonon_engine.pack_directory()
    if directory is None:
        return []
    for catalog in sorted((directory / "hf").glob("**/models--*phonon-voices/snapshots/*/voices.jsonl")):
        entries = []
        for line in catalog.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("language") != "en" or not row.get("name"):
                continue
            locale = str(row.get("locale") or "")
            entries.append(
                _entry(
                    str(row["name"]),
                    gender=str(row.get("gender") or ""),
                    gender_source="upstream" if row.get("gender") else "",
                    accent=accent_label(locale) if locale.startswith("en-") else "",
                    age=str(row.get("age") or ""),
                    description=str(row.get("description") or ""),
                )
            )
        if entries:
            return sorted(entries, key=lambda item: item["name"])
    return []


def _build_kokoro() -> list[dict[str, str]]:
    from persona_forge import kokoro_engine

    entries = []
    for name in kokoro_engine.list_presets():
        language = kokoro_engine.preset_language(name)
        gender = _KOKORO_GENDER.get(name[1:2]) if name[2:3] == "_" else None
        locale = _KOKORO_ENGLISH.get(name[:1])
        entries.append(
            _entry(
                name,
                language,
                gender=gender or "",
                gender_source="upstream" if gender else "",
                accent=accent_label(locale) if locale else "",
            )
        )
    return entries


def _build_kitten() -> list[dict[str, str]]:
    from persona_forge import kitten2_engine

    directory = kitten2_engine.pack_directory()
    if directory is None:
        return []
    for catalog in sorted((directory / "hf").glob("models--*kitten-tts-2/snapshots/*/voices/voices.json")):
        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = []
        for name in sorted(data):
            gender, source = gender_from_name(name), "name"
            if gender is None:
                clip = catalog.parent / str(data[name].get("reference", ""))
                try:
                    gender = estimate_gender(clip)
                except (OSError, RuntimeError, ValueError):
                    gender = None
                source = "estimated"
            entries.append(
                _entry(
                    name,
                    kitten2_engine.preset_language(name),
                    gender=gender or "",
                    gender_source=source if gender else "",
                    description=split_camel(name),
                )
            )
        return entries
    return []


def _build_pocket_lite() -> list[dict[str, str]]:
    from persona_forge import pocket_lite_worker, pocket_voices

    entries = []
    for name in pocket_lite_worker.ENGLISH_PRESETS:
        note = str(pocket_voices.POCKET_BUILTIN_VOICES.get(name, {}).get("note", ""))
        gender = pocket_voices.gender_of(note)
        entries.append(
            _entry(name, gender=gender, gender_source="upstream" if gender else "", description=note)
        )
    return entries


_BUILDERS = {
    "kitten2": _build_kitten,
    "phonon-31m": _build_phonon,
    "kokoro": _build_kokoro,
    "pocket-lite": _build_pocket_lite,
}


@lru_cache(maxsize=1)
def _load() -> dict[str, list[dict[str, str]]]:
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def bundled_voices(engine_id: str) -> list[dict[str, str]]:
    """Catalog entries for an engine, or ``[]`` when none is bundled."""
    return [dict(entry) for entry in _load().get(engine_id, [])]


def installed_voices(provisioned: Any) -> list[dict[str, str]]:
    """Voices an installed engine reports (authoritative names), described from the bundle."""
    engine = provisioned.engine
    bundled = {entry["name"]: entry for entry in bundled_voices(provisioned.engine_id)}
    voices = []
    for name in engine.list_presets():
        entry = dict(bundled.get(name) or {"name": name})
        entry["language"] = engine.preset_language(name) or entry.get("language", "en")
        voices.append(entry)
    return voices


def generate(engine_id: str) -> list[dict[str, str]]:
    """Build an engine's entries from its installed pack (empty when it is not installed)."""
    return _BUILDERS[engine_id]()


def refresh(path: Path = CATALOG_FILE) -> dict[str, list[dict[str, str]]]:
    """Rewrite the bundled file from the packs installed on this machine."""
    from persona_forge import provisioned_engines

    catalog = dict(_load())
    for engine_id in GENERATED_ENGINES:
        provisioned = provisioned_engines.get(engine_id)
        needs_pack = engine_id != "pocket-lite"  # its voices are fixed in its worker
        if needs_pack and (provisioned is None or not provisioned.engine.is_installed()):
            print(f"skipped {engine_id}: not installed here (kept the existing entry)", file=sys.stderr)
            continue
        catalog[engine_id] = generate(engine_id)
    path.write_text(json.dumps(catalog, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    _load.cache_clear()
    return catalog


if __name__ == "__main__":
    result = refresh()
    for key, value in sorted(result.items()):
        sources: dict[str, int] = {}
        for entry in value:
            label = f"{entry.get('gender', '?')}/{entry.get('gender_source', '-')}"
            sources[label] = sources.get(label, 0) + 1
        print(f"{key}: {len(value)} voices {dict(sorted(sources.items()))}")
