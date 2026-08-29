# Why this is a container and not a standalone (pip/pipx/binary) app: the runtime needs
# pinned CPU-only torch/torchaudio wheels that diverge from PyPI defaults (ARGs below,
# enforced again in pyproject.toml's override-dependencies), source-level monkey-patches
# applied to installed qwen_tts/transformers packages (see the sed/python patch RUN steps
# further down), a per-accelerator-family install resolved at first boot by
# scripts/entrypoint.sh (GPU_FAMILY probing into /opt/accel-venv), and a separately built
# frontend bundle. Reproducing that on an arbitrary host's Python install is a real, ongoing
# maintenance burden — the container is what makes those pins/patches invisible to users.
# Revisit only if standalone packaging becomes a real ask (today there's a single known user).
ARG PYTHON_IMAGE=python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f
# Not digest-pinned like PYTHON_IMAGE below (build-stage only, never shipped in the final
# image) — override via --build-arg if you need reproducibility guarantees for CI.
ARG NODE_IMAGE=node:24-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e

# Static export, served by Flask at / (see src/persona_forge/app.py). Independent stage so the
# final image never needs a Node toolchain.
FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE}

ARG TORCH_VERSION=2.13.0
ARG TORCHAUDIO_VERSION=2.11.0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app/src/export

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git gnupg libjemalloc2 libgomp1 libsox-fmt-all sox ffmpeg && \
      apt-get clean && rm -rf /var/lib/apt/lists/*

# Phase A6f: Intel iGPU userspace (compute-runtime + Level-Zero loader), so only the torch
# wheel varies per accelerator family at runtime (A6e installs that). Off by default —
# `INSTALL_ACCEL_SYSLIBS=0` keeps the canonical CPU image byte-identical (D3). Debian's own
# apt archive (this base image is Debian trixie) does not carry these packages — confirmed by
# `apt-cache search` returning nothing for level-zero/libze/intel-opencl — so this pulls Intel's
# official GPU apt repo, which has historically targeted Ubuntu; compatibility with a Debian
# base is UNVALIDATED (escalate→device — needs a real build + generate check on Intel iGPU
# hardware, e.g. plexxie, once Docker is available there). Package/version set mirrors the
# native-venv recipe already proven on plexxie (A6.1): intel-opencl-icd, libze1,
# libze-intel-gpu1, libigc2, libigdgmm12.
ARG INSTALL_ACCEL_SYSLIBS=0
RUN if [ "${INSTALL_ACCEL_SYSLIBS}" = "1" ]; then \
      curl -fsSL https://repositories.intel.com/gpu/intel-graphics.key \
        | gpg --dearmor -o /usr/share/keyrings/intel-graphics.gpg && \
      echo "deb [signed-by=/usr/share/keyrings/intel-graphics.gpg arch=amd64] https://repositories.intel.com/gpu/ubuntu jammy unified" \
        > /etc/apt/sources.list.d/intel-gpu.list && \
      apt-get update && apt-get install -y --no-install-recommends \
        intel-opencl-icd libze1 libze-intel-gpu1 libigc2 libigdgmm12 && \
      apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY requirements/ requirements/

RUN python -m pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==${TORCH_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}" && \
    python -m pip install qwen-tts==0.1.1 --no-deps && \
    python -m pip install -r requirements/requirements-runtime.txt && \
    python -m pip install omnivoice==0.2.1 --no-deps
    # ^ PyPI release. The 0.2.0 changelog lists commit 398b6113 ("Expose pad_duration and
    #   fade_duration to let users control fade-in/out and silence padding") — the support
    #   needed for accurate segment duration targeting. Verified 2026-08-22 against the
    #   0.2.1 tag source: OmniVoiceGenerationConfig.pad_duration/fade_duration exist and
    #   generate() passes them through, matching our omnivoice_engine.py usage.

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
t = t.replace('\"input_embeds\": inputs_embeds,', '\"inputs_embeds\": inputs_embeds,'); \
t = t.replace('\n                \"cache_position\": cache_position,\n', '\n'); \
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
RUN python -m pip install -r requirements/requirements-openvino.txt && \
    python -m pip install -r requirements/requirements-export.txt

# Pocket TTS: lightweight CPU TTS backend
RUN python -m pip install -r requirements/requirements-pocket-tts.txt

COPY src/ src/
COPY scripts/ scripts/
COPY --from=frontend-build /frontend/dist frontend/dist
RUN chmod +x scripts/entrypoint.sh

ENTRYPOINT ["scripts/entrypoint.sh"]

EXPOSE 8318

HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8318/health >/dev/null || exit 1

LABEL org.opencontainers.image.source="https://github.com/nmorgowicz-org/persona-forge"

# Default command serves the API. The compose `export` service overrides this with
# `python scripts/export.py` to build IR and quantize using the same image.
CMD ["gunicorn","persona_forge.app:app","-w","1","-k","gthread","--threads","4","--timeout","300","--bind","0.0.0.0:8318","--log-level","info"]
