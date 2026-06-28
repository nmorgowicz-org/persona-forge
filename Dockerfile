ARG PYTHON_IMAGE=python:3.13-slim@sha256:2b7445fb71ca9cb15e9aab053fe8cb3162796f8e1d92ada12a49c766a811bc1e
FROM ${PYTHON_IMAGE} AS base

ARG TORCH_VERSION=2.12.1
ARG TORCHAUDIO_VERSION=2.11.0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl git libgomp1 libsox-fmt-all sox && \
      apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-ov-runtime.txt requirements-ov-export.txt ./

# Install CPU-only Torch explicitly before qwen-tts so pip does not pull CUDA libraries.
RUN python -m pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==${TORCH_VERSION}" "torchaudio==${TORCHAUDIO_VERSION}" && \
    python -m pip install -r requirements.txt

# Fix Qwen3-TTS ONNX Runtime: set intra threads to 6 instead of 1
RUN sed -i 's/option\.intra_op_num_threads = 1/option.intra_op_num_threads = 6/' \
    /usr/local/lib/python3.13/site-packages/qwen_tts/core/tokenizer_25hz/vq/speech_vq.py || true

COPY app_api.py app_worker.py model_config.py serve.py ./
COPY scripts/download_model.py scripts/download_model.py

FROM base AS runtime

RUN python -m pip install -r requirements-ov-runtime.txt

EXPOSE 8318 8319

HEALTHCHECK --interval=30s --timeout=5s --start-period=10m --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8318/health >/dev/null || exit 1

CMD ["python", "serve.py"]

FROM runtime AS exporter

RUN python -m pip install -r requirements-ov-export.txt

COPY export_openvino.py ov_export_wrappers.py parity_contract.py test_vocoder_parity.py benchmark_vocoder.py test_transformer_parity.py ./

LABEL org.opencontainers.image.source="https://github.com/nmorgowicz-org/qwen3-tts-openvino"
