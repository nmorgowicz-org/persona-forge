"""The built-in Pocket voices and what the app says about each."""

from __future__ import annotations

POCKET_BUILTIN_VOICES: dict[str, dict[str, str]] = {
    "vera": {"display_name": "Vera", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female, natural Aussie"},
    "jane": {"display_name": "Jane", "license": "CC0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female conversation"},
    "anna": {"display_name": "Anna", "license": "CC0", "language": "English", "language_code": "en", "category": "conversation", "note": "Female conversation"},
    "fantine": {"display_name": "Fantine", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Female reading"},
    "alba": {"display_name": "Alba", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Reading / character"},
    "marius": {"display_name": "Marius", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "reading", "note": "Male reading"},
    "jean": {"display_name": "Jean", "license": "CC0", "language": "English", "language_code": "en", "category": "reading", "note": "Male reading"},
    "azelma": {"display_name": "Azelma", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "bill_boerst": {"display_name": "Bill Boerst", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "caro_davy": {"display_name": "Caro Davy", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "charles": {"display_name": "Charles", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "cosette": {"display_name": "Cosette", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "eponine": {"display_name": "Eponine", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "eve": {"display_name": "Eve", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "george": {"display_name": "George", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "javert": {"display_name": "Javert", "license": "CC BY 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "mary": {"display_name": "Mary", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female"},
    "michael": {"display_name": "Michael", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "paul": {"display_name": "Paul", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "peter_yearsley": {"display_name": "Peter Yearsley", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "stuart_bell": {"display_name": "Stuart Bell", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male"},
    "estelle": {"display_name": "Estelle", "license": "CC BY 4.0", "language": "French", "language_code": "fr", "category": "multilingual", "note": "French"},
    "giovanni": {"display_name": "Giovanni", "license": "CC BY 4.0", "language": "Italian", "language_code": "it", "category": "multilingual", "note": "Italian"},
    "juergen": {"display_name": "Juergen", "license": "CC BY 4.0", "language": "German", "language_code": "de", "category": "multilingual", "note": "German"},
    "lola": {"display_name": "Lola", "license": "CC BY 4.0", "language": "Spanish", "language_code": "es", "category": "multilingual", "note": "Spanish"},
    "rafael": {"display_name": "Rafael", "license": "CC BY 4.0", "language": "Portuguese", "language_code": "pt", "category": "multilingual", "note": "Portuguese"},
    "hf_expresso_happy": {"display_name": "Expresso Happy", "license": "CC BY-NC 4.0", "language": "English", "language_code": "en", "category": "other", "note": "Happy delivery", "path": "hf://kyutai/tts-voices/expresso/ex03-ex01_happy_001_channel1_334s.wav"},
    "hf_voice_zero_bill": {"display_name": "Bill (Zero)", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Male", "path": "hf://kyutai/tts-voices/voice-zero/bill_boerst.wav"},
    "hf_voice_donations_0a67": {"display_name": "Donation 0a67", "license": "CC0", "language": "English", "language_code": "en", "category": "other", "note": "Female", "path": "hf://kyutai/tts-voices/voice-donations/0a67_enhanced.wav"},
    "hf_cml_fr_10087": {"display_name": "French 10087", "license": "CC BY 4.0", "language": "French", "language_code": "fr", "category": "multilingual", "note": "Female", "path": "hf://kyutai/tts-voices/cml-tts/fr/10087_11650_000028-0002_enhanced.wav"},
}


def gender_of(note: str) -> str:
    """``female``/``male`` when the app's note for a voice says so, else an empty string."""
    lowered = note.lower()
    return "female" if "female" in lowered else "male" if "male" in lowered else ""
