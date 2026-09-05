"""Persona Forge — voice cloning and design studio."""

__version__ = "1.4.8"  # x-release-please-version

import logging
import warnings

# rope_config_validation was removed in transformers 5.x; the deprecated shim
# in modeling_rope_utils.py emits a FutureWarning when called from qwen_tts
# config initialization.  Nothing to fix on our end — suppress the noise.
warnings.filterwarnings(
    "ignore",
    message=".*rope_config_validation.*",
    category=FutureWarning,
)

# transformers 5.x generate() warns when repetition_penalty is passed with
# inputs_embeds but no input_ids.  The penalty still applies correctly to
# newly generated tokens; the warning is informational.
warnings.filterwarnings(
    "ignore",
    message=".*repetition_penalty.*inputs_embeds.*",
    category=UserWarning,
)


class _TransformersNoiseFilter(logging.Filter):
    """Drop noisy transformers 5.x INFO/WARNING lines that are not actionable."""

    _SUPPRESSED = (
        "Setting `pad_token_id` to `eos_token_id`",
        "`rope_config_validation` is deprecated",
        "`layer_type_validation` is deprecated",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(s in msg for s in self._SUPPRESSED)


logging.getLogger("transformers").addFilter(_TransformersNoiseFilter())
