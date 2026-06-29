#!/usr/bin/env bash
set -euo pipefail
# run_bench.sh: convenience entrypoint for running test_ov_generation.py
# from the exporter container with sane defaults.

: "${OPENVINO_MODE:=full}"
: "${OPENVINO_BUFFER_KV:=1}"
: "${OMP_NUM_THREADS:=6}"
: "${OMP_WAIT_POLICY:=PASSIVE}"
: "${TRANSFORMERS_VERBOSITY:=error}"
: "${PYTHONUNBUFFERED:=1}"
: "${PYTHONDONTWRITEBYTECODE:=1}"

export OPENVINO_MODE OPENVINO_BUFFER_KV OMP_NUM_THREADS OMP_WAIT_POLICY \
   TRANSFORMERS_VERBOSITY PYTHONUNBUFFERED PYTHONDONTWRITEBYTECODE

if [ -z "${OPENVINO_MODEL_DIR:-}" ]; then
  echo "[run_bench] ERROR: OPENVINO_MODEL_DIR not set" >&2
  exit 1
fi

if [ -z "${MODEL_REPO:-}" ]; then
  echo "[run_bench] ERROR: MODEL_REPO not set" >&2
  exit 1
fi

# Default output JSON path
OUTPUT_JSON="${OUTPUT_JSON:-/tmp/ov_generation_report.json}"

exec python test_ov_generation.py \
  --model-dir "${OPENVINO_MODEL_DIR}" \
  --mode "${MODE:-all}" \
  --output-json "${OUTPUT_JSON}" \
  "${@}"
