"""Project-owned, versioned Pocket-TTS English config.

The upstream package's ``config/english.yaml`` points ``weights_path`` at the
gated ``kyutai/pocket-tts`` repository. Loading through a project-owned config
changes the model's ``origin`` (the package checks
``origin.is_relative_to(CONFIGS_DIR)`` before honoring built-in voice names),
which is intended: the runtime adapter resolves built-in voice names itself to
resolver-verified local files (see ``pocket_tts_runtime``).

This module only rewrites the three downloadable paths (cloning weights,
non-cloning fallback weights, tokenizer) to resolver-verified local files; the
architecture of the template is byte-for-byte the pocket-tts 2.1.0
``config/english.yaml`` (strict schema, ``extra=forbid``), so the generated file
is loadable by the pinned package version.
"""

from __future__ import annotations

import contextlib
import datetime
import os
import tempfile
from pathlib import Path

from persona_forge.pocket_artifact_resolver import (
    KYUTAI_WITHOUT_CLONING_REPO,
    KYUTAI_WITHOUT_CLONING_REVISION,
    POCKET_TTS_PACKAGE_VERSION,
)

CONFIG_FILENAME = "english-pf.yaml"

# ``{weights_path}`` / ``{noncloning_weights_path}`` / ``{tokenizer_path}`` are
# substituted with resolver-verified local paths (quoted: paths may contain
# spaces). Provenance is recorded in the header comment, never in values.
_TEMPLATE = """\
# Persona Forge project-owned Pocket-TTS English config.
# Template mirrors pocket-tts {package_version} config/english.yaml (strict schema).
# weights_path / tokenizer_path point at resolver-verified local artifacts.
# Provenance: {provenance}
# Generated {generated_at}; do not edit by hand.

weights_path: "{weights_path}"
weights_path_without_voice_cloning: "{noncloning_weights_path}"


flow_lm:
  insert_bos_before_voice: true
  dtype: float32
  flow:
    depth: 6
    dim: 512
  transformer:
    d_model: 1024
    hidden_scale: 4
    max_period: 10000
    num_heads: 16
    num_layers: 6
  lookup_table:
    dim: 1024
    n_bins: 4000
    tokenizer: sentencepiece
    tokenizer_path: "{tokenizer_path}"
  #weights_path: final.safetensors

mimi:
  dtype: float32
  sample_rate: 24000
  inner_dim: 32
  outer_dim: 512
  channels: 1
  frame_rate: 12.5
  seanet:
    dimension: 512
    channels: 1
    n_filters: 64
    n_residual_layers: 1
    ratios:
    - 6
    - 5
    - 4
    kernel_size: 7
    residual_kernel_size: 3
    last_kernel_size: 3
    dilation_base: 2
    pad_mode: constant
    compress: 2
  transformer:
    d_model: 512
    num_heads: 8
    num_layers: 2
    layer_scale: 0.01
    context: 250
    dim_feedforward: 2048
    input_dimension: 512
    output_dimensions:
    - 512
  quantizer:
    dimension: 32
    output_dimension: 512
  #weights_path: codec.safetensors
"""


def render_english_config(
    *,
    weights_path: str,
    noncloning_weights_path: str | None = None,
    tokenizer_path: str | None = None,
    provenance: str = "unknown",
) -> str:
    """Render the project-owned English config text."""
    if not noncloning_weights_path:
        noncloning_weights_path = (
            f"hf://{KYUTAI_WITHOUT_CLONING_REPO}/languages/english/model.safetensors"
            f"@{KYUTAI_WITHOUT_CLONING_REVISION}"
        )
    if not tokenizer_path:
        tokenizer_path = (
            f"hf://{KYUTAI_WITHOUT_CLONING_REPO}/languages/english/tokenizer.model"
            f"@{KYUTAI_WITHOUT_CLONING_REVISION}"
        )
    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _TEMPLATE.format(
        package_version=POCKET_TTS_PACKAGE_VERSION,
        provenance=provenance,
        generated_at=generated_at,
        # Backslashes are YAML escape characters inside a double-quoted scalar;
        # a raw Windows path (e.g. "D:\scripts\...") is invalid YAML. Forward
        # slashes are safe in both YAML and as Windows file paths.
        weights_path=weights_path.replace("\\", "/"),
        noncloning_weights_path=noncloning_weights_path.replace("\\", "/"),
        tokenizer_path=tokenizer_path.replace("\\", "/"),
    )


def write_pocket_english_config(
    artifact_dir: str | Path,
    *,
    weights_path: str,
    noncloning_weights_path: str | None = None,
    tokenizer_path: str | None = None,
    provenance: str = "unknown",
) -> Path:
    """Atomically write the config under ``artifact_dir/config/`` and return its path."""
    config_dir = Path(artifact_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    final_path = config_dir / CONFIG_FILENAME
    text = render_english_config(
        weights_path=weights_path,
        noncloning_weights_path=noncloning_weights_path,
        tokenizer_path=tokenizer_path,
        provenance=provenance,
    )
    tmp_fd, tmp_name = tempfile.mkstemp(dir=config_dir, prefix=f".{CONFIG_FILENAME}.")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, final_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    return final_path
