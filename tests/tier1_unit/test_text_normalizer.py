import pytest

from persona_forge import text_normalizer
from persona_forge.text_normalizer import normalize, number_to_words


def test_structured_corpus_case_is_spelled_out():
    spoken = normalize("Invoice AB-104 totals $1,234.56 due on the 23rd at 3:30 PM.")

    assert "A B one oh four" in spoken
    assert "one thousand two hundred thirty-four dollars and fifty-six cents" in spoken
    assert "twenty-third" in spoken
    assert "three thirty P M" in spoken
    assert not any(ch.isdigit() for ch in spoken)


@pytest.mark.parametrize(
    ("value", "words"),
    [(0, "zero"), (13, "thirteen"), (21, "twenty-one"), (100, "one hundred"),
     (1001, "one thousand one"), (2_500_000, "two million five hundred thousand")],
)
def test_number_to_words(value, words):
    assert number_to_words(value) == words


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3.5 kg", "three point five kilograms"),
        ("1 km", "one kilometer"),
        ("15%", "fifteen percent"),
        ("in 2024", "in twenty twenty-four"),
        ("in 2005", "in two thousand five"),
        ("the 1st and 12th", "the first and twelfth"),
        ("Gate 7 at 14:00", "Gate seven at fourteen hundred"),
        ("call 555-0142", "call five five five oh one four two"),
        ("£20", "twenty pounds"),
        ("$1", "one dollar"),
    ],
)
def test_common_forms(text, expected):
    assert normalize(text) == expected


def test_urls_and_emails_are_left_alone():
    text = "see www.example.com or a@b.com or https://x.io/v2 now"

    assert normalize(text) == text


def test_text_without_digits_is_unchanged():
    assert normalize("Nothing to do here.") == "Nothing to do here."
    assert normalize("") == ""


def test_failure_returns_the_original_text(monkeypatch):
    monkeypatch.setattr(text_normalizer, "_RULES", (("not a pattern", None),))

    assert normalize("room 101") == "room 101"


def test_env_switch_disables_normalisation(monkeypatch):
    monkeypatch.setenv("TTS_NORMALIZE_TEXT", "0")
    assert text_normalizer.enabled() is False
    monkeypatch.delenv("TTS_NORMALIZE_TEXT")
    assert text_normalizer.enabled() is True
