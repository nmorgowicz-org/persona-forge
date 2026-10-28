"""Hugging Face access for gated engine packs: the token store and install-failure triage.

The token is a secret the user types into the engine card. It is kept in one 0600 file under the
app data directory (``.engine_hf_token``; deliberately not the ``HF_TOKEN_FILE`` that may be a
read-only Docker secret) and handed ONLY to the pack download child process by the pack that needs
it. It is never copied into ``os.environ``, so the standard Pocket runtime and every other child
process stay as they were. No API returns it: callers get ``status()`` (``set`` and where it came
from), nothing else.

Resolution order when a pack download needs a token:

1. the stored token (set on the engine card),
2. ``HF_TOKEN`` / ``HUGGING_FACE_HUB_TOKEN`` from the environment (which already includes a token
   loaded from ``HF_TOKEN_FILE`` at startup),
3. the user's own ``huggingface-cli login``.

This module never accepts a gate's terms for anyone and never talks to Hugging Face; a failed
download is classified from its error text so the card can say what to do.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from persona_forge import paths

TOKEN_FILENAME = ".engine_hf_token"
HF_TOKENS_URL = "https://huggingface.co/settings/tokens"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{6,512}$")
_ENV_NAMES = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")

_lock = threading.Lock()
_cache: tuple[tuple[int, int], str | None] | None = None  # ((mtime_ns, size), token)


class InvalidToken(ValueError):
    """The submitted token is not usable. The message never contains the token."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


def token_path() -> Path:
    return Path(paths.runtime_data_dir()) / TOKEN_FILENAME


def validate(token: object) -> str:
    """Return the trimmed token, or raise ``InvalidToken`` with a message that omits it."""
    if not isinstance(token, str):
        raise InvalidToken("The token must be a string.")
    cleaned = token.strip()
    if not cleaned:
        raise InvalidToken("Paste a Hugging Face access token.")
    if not _TOKEN_RE.match(cleaned):
        raise InvalidToken(
            "That does not look like a Hugging Face token (letters, digits, '_', '-' and '.' only, "
            "6 to 512 characters, no spaces)."
        )
    return cleaned


def save(token: object) -> None:
    """Store the token atomically with owner-only permissions. Raises ``InvalidToken``."""
    cleaned = validate(token)
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{TOKEN_FILENAME}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(cleaned)
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _forget_cache()


def clear() -> bool:
    """Delete the stored token. Returns True if there was one."""
    with _lock:
        _forget_cache()
        try:
            token_path().unlink()
        except FileNotFoundError:
            return False
        return True


def _forget_cache() -> None:
    global _cache
    _cache = None


def stored_token() -> str | None:
    """The token saved on the engine card, or None."""
    global _cache
    path = token_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _cache
    if cached is not None and cached[0] == key:
        return cached[1]
    try:
        value = path.read_text(encoding="utf-8").strip() or None
    except OSError:
        value = None
    _cache = (key, value)
    return value


def env_token() -> str | None:
    for name in _ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def login_token() -> str | None:
    """The token from the user's own ``huggingface-cli login``, if the library is importable."""
    try:
        from huggingface_hub import get_token

        return get_token() or None
    except Exception:  # absent library or unreadable login file: no token, not an error
        return None


def resolve() -> tuple[str | None, str | None]:
    """``(token, source)`` for a pack download; source is stored | environment | login | None."""
    token = stored_token()
    if token:
        return token, "stored"
    token = env_token()
    if token:
        return token, "environment"
    token = login_token()
    if token:
        return token, "login"
    return None, None


def status() -> dict[str, object]:
    """What the API may say about the token: whether one is set and where it comes from."""
    _token, source = resolve()
    return {"set": source is not None, "source": source, "can_clear": stored_token() is not None}


def secrets() -> list[str]:
    """Every token value this process knows, for redaction."""
    found = [stored_token(), env_token()]
    return [value for value in found if value and len(value) >= 4]


# -- install failure triage -----------------------------------------------------------------


@dataclass(frozen=True)
class Failure:
    code: str  # needs_token | terms_not_accepted | token_rejected | network
    message: str
    link: str | None


_NETWORK = (
    "name or service",
    "nodename nor servname",
    "temporary failure in name resolution",
    "connection",
    "could not resolve",
    "failed to resolve",
    "timed out",
    "timeout",
    "network is unreachable",
    "max retries exceeded",
    "certificate verify failed",
)
_REJECTED = ("invalid credentials", "invalid username or password", "invalid token", "token is invalid")
# Printed by a pack's preflight (see pocket_lite_pack) with the HTTP status Hugging Face answered:
# 401 means no token or one it does not recognise, 403 means a valid token whose account has not
# accepted the gate's terms. Exact, unlike the text heuristics below.
_GATE_STATUS = re.compile(r"pf_hf_gate (\d{3})")
_HTTP_AUTH = re.compile(r"\b40[13]\b")
_GATE = (
    "no cloning weights",
    "gated",
    "restricted",
    "not in the authorized list",
    "ask for access",
    "authenticated",
    "access to model",
)


def _token_rejected(label: str) -> Failure:
    return Failure(
        "token_rejected",
        f"{label} failed: Hugging Face did not accept the token. Check that it was copied "
        f"completely and has not been revoked, paste a new one (create it at {HF_TOKENS_URL}), then "
        "choose Repair.",
        HF_TOKENS_URL,
    )


def _needs_token(label: str, repo: str, repo_url: str) -> Failure:
    return Failure(
        "needs_token",
        f"{label} failed: {repo} is a gated repository, so downloading it needs a Hugging "
        f"Face token. Add one on this card (create it at {HF_TOKENS_URL}), accept the terms "
        f"on {repo_url} with the same account, then choose Repair. The app does not accept "
        "terms for you.",
        repo_url,
    )


def _terms_not_accepted(label: str, repo: str, repo_url: str) -> Failure:
    return Failure(
        "terms_not_accepted",
        f"{label} failed: Hugging Face has not given this token's account access to {repo}. "
        f"Open {repo_url}, accept the terms while signed in to that account, then choose "
        "Repair. The app does not accept terms for you.",
        repo_url,
    )


def classify(raw: str, *, token_present: bool, label: str, repo: str, repo_url: str) -> Failure | None:
    """Tell missing token, rejected token, unaccepted terms and network failure apart.

    ``raw`` is the failed step's output. Returns None when the failure is none of these, so the
    caller keeps its generic message. Hugging Face answers a gated repo with 401 when no token is
    sent and 403 when the token's owner has not accepted the terms; a token it does not recognise
    gets 401 "invalid credentials".
    """
    lowered = raw.lower()
    status = _GATE_STATUS.search(lowered)
    if status is not None:
        code = status.group(1)
        if code == "403":
            return _terms_not_accepted(label, repo, repo_url)
        if not token_present:
            return _needs_token(label, repo, repo_url)
        return _token_rejected(label)
    gate_hit = any(marker in lowered for marker in _GATE) or bool(_HTTP_AUTH.search(lowered))
    if any(marker in lowered for marker in _REJECTED) and token_present:
        return _token_rejected(label)
    if gate_hit:
        if not token_present:
            return _needs_token(label, repo, repo_url)
        return _terms_not_accepted(label, repo, repo_url)
    if any(marker in lowered for marker in _NETWORK):
        return Failure(
            "network",
            f"{label} failed: could not reach huggingface.co. Check the internet connection (and "
            "any proxy or firewall) and choose Repair to try again.",
            None,
        )
    return None
