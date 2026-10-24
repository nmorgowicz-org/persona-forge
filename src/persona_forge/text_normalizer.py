"""Spell out numbers, money, times and codes before synthesis.

Pocket-TTS misreads structured text ("AB-104 totals $1,234.56" came out as "AB 10 of 4 totals
$1020.34.56"). This is a small, dependency-free normaliser for English text. It never raises: any
failure returns the original text, and tokens that look like URLs or e-mail addresses are left alone.
Engines that already normalise internally (Kitten TTS 2) simply do not call it.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SCALES = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (10**3, "thousand"))
_ORDINAL_IRREGULAR = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}
_UNITS = {
    "kg": "kilograms",
    "g": "grams",
    "mg": "milligrams",
    "km": "kilometers",
    "m": "meters",
    "cm": "centimeters",
    "mm": "millimeters",
    "l": "liters",
    "ml": "milliliters",
    "gb": "gigabytes",
    "mb": "megabytes",
    "kb": "kilobytes",
    "tb": "terabytes",
    "ms": "milliseconds",
    "s": "seconds",
    "hz": "hertz",
    "khz": "kilohertz",
    "mph": "miles per hour",
}
_CURRENCY = {"$": ("dollar", "cents"), "£": ("pound", "pence"), "€": ("euro", "cents")}


def enabled() -> bool:
    """Normalisation is on unless ``TTS_NORMALIZE_TEXT`` is set to a false value."""
    return os.environ.get("TTS_NORMALIZE_TEXT", "1").strip().lower() not in {"0", "false", "no", "off"}


def number_to_words(value: int) -> str:
    """Spell an integer (up to the trillions) in English."""
    if value < 0:
        return "minus " + number_to_words(-value)
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return f"{_ONES[hundreds]} hundred" + (f" {number_to_words(rest)}" if rest else "")
    for scale, name in _SCALES:
        if value >= scale:
            head, rest = divmod(value, scale)
            return f"{number_to_words(head)} {name}" + (f" {number_to_words(rest)}" if rest else "")
    return str(value)


def _digits(text: str) -> str:
    return " ".join("oh" if ch == "0" else _ONES[int(ch)] for ch in text if ch.isdigit())


def _ordinal(value: int) -> str:
    words = number_to_words(value)
    head, sep, last = words.rpartition("-")
    if not sep:
        head, sep, last = words.rpartition(" ")
    if last in _ORDINAL_IRREGULAR:
        last = _ORDINAL_IRREGULAR[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}{sep}{last}"


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else noun + "s"


def _money(match: re.Match[str]) -> str:
    symbol, whole_text, cents_text = match.group(1), match.group(2), match.group(3)
    major, minor = _CURRENCY[symbol]
    whole = int(whole_text.replace(",", ""))
    spoken = f"{number_to_words(whole)} {_plural(whole, major)}"
    if cents_text:
        cents = int(cents_text)
        if cents:
            unit = minor if minor != "cents" else _plural(cents, "cent")
            spoken += f" and {number_to_words(cents)} {unit}"
    return spoken


def _time(match: re.Match[str]) -> str:
    hour, minute = int(match.group(1)), int(match.group(2))
    suffix = (match.group(3) or "").replace(".", "").upper()
    if hour > 23 or minute > 59:
        return match.group(0)
    spoken = number_to_words(hour if hour else 12 if suffix else 0)
    if minute:
        spoken += f" {'oh ' if minute < 10 else ''}{number_to_words(minute)}"
    elif not suffix and hour:
        spoken += " o'clock" if hour < 13 else " hundred"
    return spoken + (f" {' '.join(suffix)}" if suffix else "")


def _decimal(match: re.Match[str]) -> str:
    whole = int(match.group(1).replace(",", ""))
    return f"{number_to_words(whole)} point {_digits(match.group(2))}"


def _integer(match: re.Match[str]) -> str:
    raw = match.group(0)
    value = int(raw.replace(",", ""))
    if len(raw) == 4 and "," not in raw and 1900 <= value <= 2099:
        head, tail = divmod(value, 100)
        if tail == 0 or head == 20 and tail < 10:
            return number_to_words(value)
        return f"{number_to_words(head)} {'oh ' if tail < 10 else ''}{number_to_words(tail)}"
    if len(raw) > 1 and raw.startswith("0") and "," not in raw:
        return _digits(raw)
    return number_to_words(value)


def _code(match: re.Match[str]) -> str:
    """Read a code piece by piece: letters one at a time, digits one at a time."""
    spoken = []
    for piece in match.group(0).split("-"):
        for run in re.findall(r"[A-Za-z]+|\d+", piece):
            spoken.append(_digits(run) if run.isdigit() else " ".join(run))
    return " ".join(spoken)


_MONTHS = (
    "January February March April May June July August September October November December"
).split()


def _iso_date(match: re.Match[str]) -> str:
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return match.group(0)
    return f"{_MONTHS[month - 1]} {_ordinal(day)}, {_integer_year(year)}"


def _integer_year(year: int) -> str:
    head, tail = divmod(year, 100)
    if 1000 <= year <= 2099 and tail and not (head == 20 and tail < 10):
        return f"{number_to_words(head)} {'oh ' if tail < 10 else ''}{number_to_words(tail)}"
    return number_to_words(year)


def _unit(match: re.Match[str]) -> str:
    number, unit = match.group(1), match.group(2)
    spoken_unit = _UNITS.get(unit.lower())
    if spoken_unit is None:
        return match.group(0)
    if "." in number:
        whole, frac = number.split(".")
        spoken = f"{number_to_words(int(whole.replace(',', '')))} point {_digits(frac)}"
    else:
        count = int(number.replace(",", ""))
        spoken = number_to_words(count)
        if count == 1:
            spoken_unit = spoken_unit.removesuffix("s") if not spoken_unit.endswith("hertz") else spoken_unit
    return f"{spoken} {spoken_unit}"


_RULES: tuple[tuple[re.Pattern[str], object], ...] = (
    (re.compile(r"([$£€])\s?(\d[\d,]*)(?:\.(\d{2}))?(?!\d)"), _money),
    (re.compile(r"\b(\d{1,2}):(\d{2})\s?([AaPp]\.?[Mm]\.?)?(?![\d:])"), _time),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), _iso_date),
    (re.compile(r"\b[A-Z]{1,5}-\d+(?:-[A-Z0-9]+)*\b|\b\d+-[A-Z]{1,5}\b"), _code),
    (re.compile(r"\b\d{3}-\d{4}\b"), lambda m: _digits(m.group(0))),
    (re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?%"), lambda m: _decimal_or_int(m.group(1)) + " percent"),
    (
        re.compile(r"\b(\d+)(st|nd|rd|th)\b"),
        lambda m: _ordinal(int(m.group(1))),
    ),
    (re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?([A-Za-z]{1,3})\b(?!-)"), _unit),
    (re.compile(r"\b(\d[\d,]*)\.(\d+)\b"), _decimal),
    (re.compile(r"\b\d[\d,]*\b"), _integer),
)


def _decimal_or_int(number: str) -> str:
    if "." in number:
        whole, frac = number.split(".")
        return f"{number_to_words(int(whole.replace(',', '')))} point {_digits(frac)}"
    return number_to_words(int(number.replace(",", "")))


def _protected(token: str) -> bool:
    lowered = token.lower()
    return "://" in lowered or lowered.startswith("www.") or "@" in token


def normalize(text: str) -> str:
    """Return ``text`` with numbers, money, times, ordinals, units and codes spelled out.

    Never raises: on any error the original text is returned unchanged.
    """
    if not text or not any(ch.isdigit() for ch in text):
        return text
    try:
        # Units and decimals span a space ("12 kg"), so rules run on the whole text with
        # protected tokens masked out first.
        masked: dict[str, str] = {}

        def _mask(match: re.Match[str]) -> str:
            key = "\x00" + "".join(chr(ord("a") + int(d)) for d in str(len(masked))) + "\x00"
            masked[key] = match.group(0)
            return key

        working = re.sub(r"\S*(?:://|www\.|@)\S*", _mask, text)
        for pattern, handler in _RULES:
            working = pattern.sub(handler, working)  # type: ignore[arg-type]
        for key, value in masked.items():
            working = working.replace(key, value)
        return working
    except Exception:  # noqa: BLE001 - normalisation must never block synthesis
        logger.warning("Text normalisation failed; using the original text", exc_info=True)
        return text
