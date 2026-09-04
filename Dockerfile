# Why this is a container and not a standalone (pip/pipx/binary) app: the runtime needs
# pinned CPU-only torch/torchaudio wheels that diverge from PyPI defaults (ARGs below,
# enforced again in pyproject.toml's override-dependencies), source-level monkey-patches
# applied to installed qwen_tts/transformers packages (see the compat_patch.py RUN step
# further down), a per-accelerator-family install resolved at first boot by
# scripts/entrypoint.sh (GPU_FAMILY probing into /opt/accel-venv), and a separately built
# frontend bundle. Reproducing that on an arbitrary host's Python install is a real, ongoing
# maintenance burden — the container is what makes those pins/patches invisible to users.
# Revisit only if standalone packaging becomes a real ask (today there's a single known user).
ARG PYTHON_IMAGE=python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
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

ARG TORCH_VERSION=2.14.0
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

# Single source of truth for both the container and local-dev patch paths (Phase 5) — see
# persona_forge/compat_patch.py's module docstring for the full patch inventory and the
# idempotency-marker design. Copied in isolation (not the full `COPY src/ src/` below) so this
# layer's cache key depends only on this one file, not on unrelated source changes.
COPY src/persona_forge/compat_patch.py /tmp/compat_patch.py
RUN python -c "\
import sys, json; \
sys.path.insert(0, '/tmp'); \
from compat_patch import apply_qwen_patches; \
report = apply_qwen_patches(); \
print(json.dumps(report, indent=2)); \
sys.exit(1 if report['status'] == 'failed' else 0)"

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
