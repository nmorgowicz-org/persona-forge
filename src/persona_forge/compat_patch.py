"""Single source of truth for the qwen_tts/transformers site-package source patches (Phase 5).

``qwen-tts==0.1.1`` was written against an older ``transformers`` API. Both the local dev path
(``scripts/patch_local_compat.py``, run once per fresh ``uv sync --extra qwen-tts`` venv) and the
Dockerfile used to bake two independent, drifting copies of the same six text rewrites into
installed ``qwen_tts``/``transformers`` site-packages. This module is now the one place those
rewrites are defined; both callers import it.

This is a different, unrelated kind of patch from ``persona_forge.transformers_compat``: that
module applies *runtime* monkey-patches to in-memory classes on every model load (RoPE buffer
repair, ``prepare_inputs_for_generation`` fixes, attention-mask broadcasting) and is unaffected by
this one, which rewrites *installed source files* once, out-of-process, before any model ever
loads. Neither supersedes the other; both are required.

Each patch's ``old`` text carries an *exact* verified occurrence count against the pinned
versions (``qwen-tts==0.1.1``, ``transformers==5.12.1``) — live-counted against a real installed
copy of both packages. A count that isn't the expected number, and isn't the zero that means
"already applied", is a version-drift signal and a hard failure rather than a silent skip.

Idempotency hazard: three substitutions insert text that contains their own ``old`` pattern as a
substring (the RoPE-parameters insertion is literally ``old + new_function + old``, so re-running
a naive count-based check would insert the function a second time on every subsequent run). Those
three carry an explicit ``already_applied_marker`` — text that only exists post-patch — so
"already applied" is detected by marker presence, not by an old-count that can never legitimately
reach zero.
"""

from __future__ import annotations

import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Status = str  # "applied" | "already_applied" | "failed"


@dataclass(frozen=True)
class Substitution:
    """One literal (non-regex) find/replace, applied via ``str.replace`` (all occurrences)."""

    old: str
    new: str
    expected_matches: int
    # Set only when `old` remains a substring of `new` post-patch, so a plain old-count check
    # would never settle at zero and the substitution would silently re-apply every run.
    already_applied_marker: str | None = None


@dataclass(frozen=True)
class DeleteLines:
    """Delete every line containing `contains` (mirrors the original `sed -i '/pattern/d'`)."""

    contains: str
    expected_matches: int


@dataclass(frozen=True)
class Patch:
    name: str
    relative_path: str  # relative to a site-packages root
    substitutions: tuple[Substitution, ...] = ()
    delete_lines: DeleteLines | None = None


def _rope_default_fn() -> str:
    return (
        "\ndef _compute_default_rope_parameters(config=None, device=None, **kwargs):\n"
        "    import torch as _t\n"
        "    base = float(getattr(config, 'rope_theta', 10000.0))\n"
        "    factor = float(getattr(config, 'partial_rotary_factor', 1.0))\n"
        "    head_dim = getattr(config, 'head_dim', None) or (getattr(config, 'hidden_size', 512)"
        " // getattr(config, 'num_attention_heads', 8))\n"
        "    dim = int(head_dim * factor)\n"
        "    inv_freq = 1.0 / (base ** (_t.arange(0, dim, 2, dtype=_t.int64).float().to(device)"
        " / dim))\n"
        "    return inv_freq, 1.0\n\n"
    )


PATCHES: tuple[Patch, ...] = (
    Patch(
        name="speech_vq_threads",
        relative_path="qwen_tts/core/tokenizer_25hz/vq/speech_vq.py",
        substitutions=(
            Substitution("option.intra_op_num_threads = 1", "option.intra_op_num_threads = 6", 1),
        ),
    ),
    Patch(
        name="tokenizer_v2_check_model_inputs",
        relative_path="qwen_tts/core/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py",
        delete_lines=DeleteLines("@check_model_inputs", 1),
    ),
    Patch(
        name="mimi_sliding_window_mask",
        relative_path="transformers/models/mimi/modeling_mimi.py",
        substitutions=(
            Substitution("create_sliding_window_causal_mask", "create_causal_mask", 2),
        ),
    ),
    Patch(
        name="modeling_qwen3_tts_transformers5_api",
        relative_path="qwen_tts/core/models/modeling_qwen3_tts.py",
        substitutions=(
            Substitution(
                "from transformers.activations import ACT2FN",
                "from transformers import initialization as init\n"
                "from transformers.activations import ACT2FN",
                1,
                already_applied_marker="from transformers import initialization as init",
            ),
            Substitution(
                "module.weight.data.normal_(mean=0.0, std=std)",
                "init.normal_(module.weight, mean=0.0, std=std)",
                4,
            ),
            Substitution("module.bias.data.zero_()", "init.zeros_(module.bias)", 3),
            Substitution("module.weight.data.fill_(1.0)", "init.ones_(module.weight)", 2),
            Substitution(
                "if module.padding_idx is not None:\n"
                "                module.weight.data[module.padding_idx].zero_()",
                "if module.padding_idx is not None and not getattr(module.weight,"
                ' "_is_hf_initialized", False):\n'
                "                module.weight.data[module.padding_idx].zero_()",
                2,
            ),
            Substitution(
                "self.padding_idx = config.pad_token_id",
                'self.padding_idx = getattr(config, "pad_token_id", None)',
                2,
            ),
            Substitution("input_embeds=inputs_embeds", "inputs_embeds=inputs_embeds", 1),
            Substitution('"input_embeds": inputs_embeds,', '"inputs_embeds": inputs_embeds,', 1),
            Substitution('\n                "cache_position": cache_position,\n', "\n", 1),
            Substitution("\n            cache_position=cache_position,\n", "", 6),
        ),
    ),
    Patch(
        name="configuration_qwen3_tts_layer_type_validation",
        relative_path="qwen_tts/core/models/configuration_qwen3_tts.py",
        substitutions=(
            Substitution(
                "from transformers.configuration_utils import PretrainedConfig,"
                " layer_type_validation",
                "from transformers.configuration_utils import PretrainedConfig",
                1,
            ),
            Substitution(
                "layer_type_validation(self.layer_types)", "self.validate_layer_type()", 1
            ),
        ),
    ),
    Patch(
        name="rope_utils_default_rope_parameters",
        relative_path="transformers/modeling_rope_utils.py",
        substitutions=(
            Substitution(
                "ROPE_INIT_FUNCTIONS:",
                _rope_default_fn() + "ROPE_INIT_FUNCTIONS:",
                1,
                already_applied_marker="_compute_default_rope_parameters(config=None",
            ),
            Substitution(
                '"linear": _compute_linear_scaling_rope_parameters',
                '"default": _compute_default_rope_parameters,\n'
                '    "linear": _compute_linear_scaling_rope_parameters',
                1,
                already_applied_marker='"default": _compute_default_rope_parameters,',
            ),
        ),
    ),
)


def _default_site_packages() -> Path:
    return Path(sysconfig.get_paths()["purelib"])


def _substitution_status(text: str, sub: Substitution) -> tuple[Status, str | None]:
    if sub.already_applied_marker is not None:
        if sub.already_applied_marker in text:
            return "already_applied", None
        old_count = text.count(sub.old)
        if old_count == sub.expected_matches:
            return "applied", None
        return "failed", (
            f"expected {sub.expected_matches} occurrence(s) of {sub.old!r}, found {old_count},"
            f" and already-applied marker {sub.already_applied_marker!r} is absent"
        )
    old_count = text.count(sub.old)
    if old_count == sub.expected_matches:
        return "applied", None
    if old_count == 0:
        return "already_applied", None
    return "failed", f"expected {sub.expected_matches} occurrence(s) of {sub.old!r}, found {old_count}"


def _delete_lines_status(text: str, dl: DeleteLines) -> tuple[Status, str | None]:
    count = sum(1 for line in text.splitlines(keepends=True) if dl.contains in line)
    if count == dl.expected_matches:
        return "applied", None
    if count == 0:
        return "already_applied", None
    return "failed", f"expected {dl.expected_matches} matching line(s) for {dl.contains!r}, found {count}"


def _rollup(statuses: list[Status]) -> Status:
    if "failed" in statuses:
        return "failed"
    if "applied" in statuses:
        return "applied"
    return "already_applied"


def _process_patch(site_packages: Path, patch: Patch, *, dry_run: bool) -> dict[str, Any]:
    path = site_packages / patch.relative_path
    if not path.is_file():
        return {
            "name": patch.name,
            "path": str(path),
            "status": "failed",
            "detail": "file not found",
            "items": [],
        }

    text = path.read_text()
    original_text = text
    items: list[dict[str, Any]] = []

    for sub in patch.substitutions:
        status, detail = _substitution_status(text, sub)
        if status == "applied":
            text = text.replace(sub.old, sub.new)
        items.append({"old": sub.old, "status": status, "detail": detail})

    if patch.delete_lines is not None:
        dl = patch.delete_lines
        status, detail = _delete_lines_status(text, dl)
        if status == "applied":
            text = "".join(line for line in text.splitlines(keepends=True) if dl.contains not in line)
        items.append({"old": f"line containing {dl.contains!r}", "status": status, "detail": detail})

    overall = _rollup([item["status"] for item in items])
    if not dry_run and overall == "applied" and text != original_text:
        path.write_text(text)

    return {"name": patch.name, "path": str(path), "status": overall, "items": items}


def apply_qwen_patches(site_packages: Path | str | None = None) -> dict[str, Any]:
    """Apply every patch in ``PATCHES`` against ``site_packages`` (default: this interpreter's
    purelib). Idempotent: a second call against an already-patched tree reports
    ``already_applied`` everywhere and writes nothing."""
    sp = Path(site_packages) if site_packages is not None else _default_site_packages()
    patches = [_process_patch(sp, patch, dry_run=False) for patch in PATCHES]
    return {"site_packages": str(sp), "status": _rollup([p["status"] for p in patches]), "patches": patches}


def verify_qwen_patches(site_packages: Path | str | None = None) -> dict[str, Any]:
    """Read-only check of the same patches: never writes. ``status`` uses the same vocabulary as
    ``apply_qwen_patches`` (``applied`` here means "not yet applied — would apply"); ``fully_applied``
    is the convenience boolean for "everything is already in place"."""
    sp = Path(site_packages) if site_packages is not None else _default_site_packages()
    patches = [_process_patch(sp, patch, dry_run=True) for patch in PATCHES]
    status = _rollup([p["status"] for p in patches])
    return {
        "site_packages": str(sp),
        "status": status,
        "fully_applied": status == "already_applied",
        "patches": patches,
    }


def _main() -> int:
    import json

    report = apply_qwen_patches()
    print(json.dumps(report, indent=2))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())
