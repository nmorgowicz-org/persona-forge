"""Explicit "Prepare for <engine>" jobs for saved voices (plan §5.4).

Preparation runs through the engine adapter's own ``prepare_voice`` on the existing single-worker
model executor, serialized with inference, transcription and model swaps. The adapter lock also
protects direct callers. State is polled through ``voice_bindings``: ``preparing`` while queued or
running, ``failed`` with the reason, ``ready`` once the adapter has written the marker.

A transcript an engine needs is resolved *here*, before anything is queued: a missing or
unreviewed transcript is refused with ``transcript_review`` so the UI can show it for confirmation
or editing. Nothing is ever transcribed, and nothing downloaded, while a request is being served.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, wait
from typing import Any, Callable

from persona_forge import speech_engines, voice_bindings, voice_library
from persona_forge.engine_lifecycle import PrepareCancelled


class PrepareRefused(Exception):
    """A preparation cannot start. ``code`` is stable for clients; ``status`` is the HTTP status."""

    def __init__(
        self, code: str, message: str, status: int, extra: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.public_message = message
        self.code = code
        self.status = status
        self.extra = extra or {}


_lock = threading.RLock()
_cancels: dict[tuple[str, str], threading.Event] = {}
_futures: dict[tuple[str, str], Future[None]] = {}


def reset() -> None:
    """Cancel and drain this service's jobs without replacing or stopping the model executor."""
    with _lock:
        futures = list(_futures.values())
        for event in _cancels.values():
            event.set()
        for future in futures:
            future.cancel()
    wait(futures)
    with _lock:
        _cancels.clear()
        _futures.clear()
        voice_bindings.reset_jobs()


def _find(binding_list: list[dict[str, Any]], engine_id: str) -> dict[str, Any]:
    return next(item for item in binding_list if item["engine"] == engine_id)


def _failure_message(exc: BaseException) -> str:
    return str(exc).strip() or type(exc).__name__


def _run(
    voice_id: str, engine_id: str, cancel: threading.Event, input_key: dict[str, str]
) -> None:
    key = (voice_id, engine_id)
    failure: str | None = None
    try:
        if cancel.is_set():
            raise PrepareCancelled("Preparation was cancelled.")
        meta = voice_bindings.meta_with_path(voice_id)
        if meta is None or voice_bindings.current_key(meta, engine_id) != input_key:
            raise RuntimeError("The voice changed while preparation was queued. Prepare it again.")
        adapter = speech_engines.get_adapter(engine_id)
        prepare = getattr(adapter, "prepare_voice", None)
        if prepare is None:
            raise RuntimeError(f"{engine_id} has no way to prepare a saved voice.")
        prepare(voice_id, cancel=cancel)
    except PrepareCancelled:
        pass
    except Exception as exc:  # failures belong to the inputs that actually failed
        failure = _failure_message(exc)
    finally:
        with _lock:
            if failure is not None:
                voice_bindings.set_job(voice_id, engine_id, "failed", key=input_key, error=failure)
            else:
                voice_bindings.clear_job(voice_id, engine_id)
            _cancels.pop(key, None)
            _futures.pop(key, None)


def _apply_transcript(
    voice_id: str,
    meta: dict[str, Any],
    transcript: str | None,
    confirm: bool,
    on_saved: Callable[[str], None] | None,
) -> dict[str, Any] | None:
    """Save the reviewed transcript as the user's own; returns the refreshed voice, or None."""
    text = (transcript if transcript is not None else meta.get("sample_text") or "").strip()
    if not text:
        return None
    # A prosody variant shares its parent's record, so the words are saved there.
    parent_id = voice_library.parse_voice_id(voice_id)[0]
    voice_library.update_voice(parent_id, sample_text=text, sample_text_source="user")
    if on_saved is not None:
        on_saved(parent_id)
    return voice_bindings.meta_with_path(voice_id)


def _start(
    voice_id: str,
    engine_id: str,
    *,
    transcript: str | None = None,
    confirm_transcript: bool = False,
    on_transcript_saved: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Queue a preparation and return the voice's binding for that engine (``preparing``).

    Already ``ready`` or already ``preparing`` returns the current binding without queueing again.
    Raises ``PrepareRefused`` when the engine cannot prepare this voice.

    For an engine that clones with the transcript, ``transcript`` (typed words) or
    ``confirm_transcript`` (keep the stored words) is the review step: either saves the words as
    the user's own and lets the preparation go ahead. Without one of them a missing or unreviewed
    transcript is refused with ``transcript_review``.
    """
    engine = speech_engines.ENGINES.get(engine_id)
    if engine is None:
        raise PrepareRefused("unknown_engine", f"Unknown engine {engine_id!r}.", 404)
    if not engine.capabilities.clone:
        raise PrepareRefused(
            "unsupported",
            f"{engine.label} cannot clone a saved voice ({voice_bindings.NO_CLONING}).",
            400,
        )
    if engine_id == voice_bindings.BASELINE_ENGINE:
        raise PrepareRefused(
            "nothing_to_prepare",
            f"{engine.label} clones a saved voice on every request; there is nothing to prepare.",
            400,
        )
    meta = voice_bindings.meta_with_path(voice_id)
    if meta is None:
        raise PrepareRefused("voice_not_found", "voice_id not found", 404)

    binding = _find(voice_bindings.bindings_for_meta(meta), engine_id)
    if not binding["installed"]:
        raise PrepareRefused(
            "engine_not_installed",
            f"Install {engine.label} in Runtime → Speech engines first.",
            409,
        )
    if binding["status"] == "preparing":
        if transcript is not None or confirm_transcript:
            raise PrepareRefused("preparation_busy", "Wait for preparation to finish before editing its transcript.", 409)
        return binding
    if binding["needs_transcript"] and (transcript is not None or confirm_transcript):
        refreshed = _apply_transcript(
            voice_id, meta, transcript, confirm_transcript, on_transcript_saved
        )
        if refreshed is not None:
            meta = refreshed
            binding = _find(voice_bindings.bindings_for_meta(meta), engine_id)
            if binding["status"] == "ready":
                return binding
    if binding["status"] == "ready":
        return binding
    if binding["blocker"] in ("transcript_missing", "transcript_unreviewed"):
        missing = binding["blocker"] == "transcript_missing"
        raise PrepareRefused(
            "transcript_review",
            f"{engine.label} clones with the transcript, so it must be "
            + ("added" if missing else "confirmed")
            + " before preparing.",
            409,
            {
                "reason": "missing" if missing else "unreviewed",
                "transcript": (meta.get("sample_text") or "").strip(),
            },
        )

    key = (voice_id, engine_id)
    with _lock:
        if key in _futures:
            return _find(voice_bindings.bindings_for_meta(meta), engine_id)
        from persona_forge import model

        input_key = voice_bindings.current_key(meta, engine_id)
        voice_bindings.set_job(voice_id, engine_id, "preparing", key=input_key)
        cancel = _cancels[key] = threading.Event()
        _futures[key] = model.executor.submit(_run, voice_id, engine_id, cancel, input_key)
    return _find(voice_bindings.bindings_for_meta(meta), engine_id)


def start(
    voice_id: str,
    engine_id: str,
    *,
    transcript: str | None = None,
    confirm_transcript: bool = False,
    on_transcript_saved: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Validate/review and enqueue atomically, deduplicating concurrent Prepare clicks."""
    saved: list[str] = []
    with _lock:
        binding = _start(
            voice_id, engine_id, transcript=transcript, confirm_transcript=confirm_transcript,
            on_transcript_saved=saved.append,
        )
    # A baseline-state rebuild can wait on the same executor; never hold the job lock here.
    if on_transcript_saved is not None:
        for parent_id in saved:
            on_transcript_saved(parent_id)
    return binding


def cancel(voice_id: str, engine_id: str) -> bool:
    """Ask a queued or waiting preparation to stop. False when none is running.

    A preparation still waiting for its engine to load, or still queued, stops and the voice reads
    ``needs_preparation``. One already inside the worker's ``prepare`` op (seconds, bounded by the
    adapter's timeout) finishes; the voice then reads ``ready``.
    """
    key = (voice_id, engine_id)
    with _lock:
        event = _cancels.get(key)
        future = _futures.get(key)
        if event is None:
            return False
        event.set()
        if future is not None and future.cancel():
            _cancels.pop(key, None)
            _futures.pop(key, None)
            voice_bindings.clear_job(voice_id, engine_id)
    return True
