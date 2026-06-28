ARG PYTHON_IMAGE=python:3.13-slim
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

COPY app_api.py app_worker.py model_config.py ./
COPY scripts/download_model.py scripts/download_model.py

FROM base AS runtime

RUN python -m pip install -r requirements-ov-runtime.txt

EXPOSE 8318 8319

CMD ["sh", "-c", \
    "gunicorn app_worker:app -w 1 -k gthread --threads 4 --timeout 300 --bind 0.0.0.0:8319 --preload --log-level info & \
     sleep 10 && \
     gunicorn app_api:app -w 1 -k gthread --threads 2 --timeout 300 --bind 0.0.0.0:8318 --log-level info"]

FROM runtime AS exporter

RUN python -m pip install -r requirements-ov-export.txt

LABEL org.opencontainers.image.source="https://github.com/nmorgowicz-org/qwen3-tts-openvino"
