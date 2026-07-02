ARG PYTHON_IMAGE=python:3.13-slim@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280
FROM ${PYTHON_IMAGE}

ARG TORCH_VERSION=2.12.1
ARG TORCHAUDIO_VERSION=2.11.0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app/src/export

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git libjemalloc2 libgomp1 libsox-fmt-all sox && \
      apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/ requirements/

RUN python -m pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==${TORCH_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}" && \
    python -m pip install qwen-tts==0.1.1 --no-deps && \
    python -m pip install -r requirements/runtime.txt

RUN sed -i 's/option\.intra_op_num_threads = 1/option.intra_op_num_threads = 6/' \
    /usr/local/lib/python3.13/site-packages/qwen_tts/core/tokenizer_25hz/vq/speech_vq.py || true && \
    sed -i '/@check_model_inputs/d' \
    /usr/local/lib/python3.13/site-packages/qwen_tts/core/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py || true && \
    sed -i 's/create_sliding_window_causal_mask/create_causal_mask/g' \
    /usr/local/lib/python3.13/site-packages/transformers/models/mimi/modeling_mimi.py && \
    python -c "\
p = '/usr/local/lib/python3.13/site-packages/qwen_tts/core/models/modeling_qwen3_tts.py'; \
t = open(p).read(); \
t = t.replace('from transformers.activations import ACT2FN', 'from transformers import initialization as init\nfrom transformers.activations import ACT2FN'); \
t = t.replace('module.weight.data.normal_(mean=0.0, std=std)', 'init.normal_(module.weight, mean=0.0, std=std)'); \
t = t.replace('module.bias.data.zero_()', 'init.zeros_(module.bias)'); \
t = t.replace('module.weight.data.fill_(1.0)', 'init.ones_(module.weight)'); \
t = t.replace('if module.padding_idx is not None:\n                module.weight.data[module.padding_idx].zero_()', 'if module.padding_idx is not None and not getattr(module.weight, \"_is_hf_initialized\", False):\n                module.weight.data[module.padding_idx].zero_()'); \
t = t.replace('self.padding_idx = config.pad_token_id', 'self.padding_idx = getattr(config, \"pad_token_id\", None)'); \
t = t.replace('input_embeds=inputs_embeds', 'inputs_embeds=inputs_embeds'); \
t = t.replace('\n            cache_position=cache_position,\n', ''); \
open(p, 'w').write(t)" && \
    python -c "\
p = '/usr/local/lib/python3.13/site-packages/qwen_tts/core/models/configuration_qwen3_tts.py'; \
t = open(p).read(); \
t = t.replace('from transformers.configuration_utils import PretrainedConfig, layer_type_validation', 'from transformers.configuration_utils import PretrainedConfig'); \
t = t.replace('layer_type_validation(self.layer_types)', 'self.validate_layer_type()'); \
open(p, 'w').write(t)" && \
    python -c "\
import pathlib; \
p = pathlib.Path('/usr/local/lib/python3.13/site-packages/transformers/modeling_rope_utils.py'); \
t = p.read_text(); \
fn = '''\ndef _compute_default_rope_parameters(config=None, device=None, **kwargs):\n    import torch as _t\n    base = float(getattr(config, 'rope_theta', 10000.0))\n    factor = float(getattr(config, 'partial_rotary_factor', 1.0))\n    head_dim = getattr(config, 'head_dim', None) or (getattr(config, 'hidden_size', 512) // getattr(config, 'num_attention_heads', 8))\n    dim = int(head_dim * factor)\n    inv_freq = 1.0 / (base ** (_t.arange(0, dim, 2, dtype=_t.int64).float().to(device) / dim))\n    return inv_freq, 1.0\n\n'''; \
t = t.replace('ROPE_INIT_FUNCTIONS:', fn + 'ROPE_INIT_FUNCTIONS:'); \
t = t.replace('\"linear\": _compute_linear_scaling_rope_parameters', '\"default\": _compute_default_rope_parameters,\n    \"linear\": _compute_linear_scaling_rope_parameters'); \
p.write_text(t)"

# One image, all capabilities: OpenVINO serving runtime + export/quantization tooling.
RUN python -m pip install -r requirements/openvino.txt && \
    python -m pip install -r requirements/export.txt

COPY src/ src/
COPY scripts/ scripts/
RUN chmod +x scripts/entrypoint.sh

ENTRYPOINT ["scripts/entrypoint.sh"]

EXPOSE 8318

HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8318/health >/dev/null || exit 1

LABEL org.opencontainers.image.source="https://github.com/nmorgowicz-org/qwen3-tts-openvino"

# Default command serves the API. The compose `export` service overrides this with
# `python scripts/export.py` to build IR and quantize using the same image.
CMD ["gunicorn","qwen3_tts.app:app","-w","1","-k","gthread","--threads","4","--timeout","300","--bind","0.0.0.0:8318","--log-level","info"]
