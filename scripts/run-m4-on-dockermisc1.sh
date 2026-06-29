#!/usr/bin/env bash
#
# Run the Milestone 4 generation-parity + warm-latency harness on dockermisc1.
#
# Stops the prod qwen3-tts container (so the full model load does not contend for memory
# or swap-thrash), runs test_ov_generation.py inside the exporter image against an exported
# IR directory, then ALWAYS restarts the service — even if the harness fails or is
# interrupted. The harness writes ov_generation_report.json beside the IR files.
#
# Run this ON dockermisc1, not from a dev box.
#
# Usage:
#   scripts/run-m4-on-dockermisc1.sh <ir-dir-name> [fp32|int8]
#
#   <ir-dir-name>   directory name under $OV_ROOT, e.g.
#                   qwen-tts-0.1.1_0.6b_5d83992436ea_ov-2026.2.1
#   second arg      optional compression to load (defaults to the metadata's declared set)
#
# Override any path/image via environment:
#   COMPOSE_FILE   /home/nick/docker/docker-compose.yml
#   SERVICE        qwen3-tts
#   EXPORTER_IMAGE ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-latest  (pin a tag!)
#   MODEL_CACHE    /var/data/autopirate/qwen3-tts/model
#   OV_ROOT        /var/data/autopirate/qwen3-tts/openvino
#   MODEL_SIZE     0.6B
#   REF_AUDIO_PATH host WAV mounted as the voice-clone reference
#                  (default: /var/data/autopirate/qwen3-tts/voice/voice_A.wav — project-owned,
#                  persistent. Do not point at hermes-agent scratch; it gets wiped.)
#   REF_TEXT       transcript of the reference audio. Defaults to the committed transcript of
#                  voice_A.wav (the same default app_worker.py / bench_common.py use), so you
#                  only need to set this if you swap in a different reference WAV.
#   THREADS        6
#
set -euo pipefail

IR_DIR_NAME="${1:?Usage: $0 <ir-dir-name> [fp32|int8]}"
COMPRESSION="${2:-${COMPRESSION:-}}"

COMPOSE_FILE="${COMPOSE_FILE:-/home/nick/docker/docker-compose.yml}"
SERVICE="${SERVICE:-qwen3-tts}"
EXPORTER_IMAGE="${EXPORTER_IMAGE:-ghcr.io/nmorgowicz-org/qwen3-tts-openvino:exporter-latest}"
MODEL_CACHE="${MODEL_CACHE:-/var/data/autopirate/qwen3-tts/model}"
OV_ROOT="${OV_ROOT:-/var/data/autopirate/qwen3-tts/openvino}"
MODEL_SIZE="${MODEL_SIZE:-0.6B}"
REF_AUDIO_PATH="${REF_AUDIO_PATH:-/var/data/autopirate/qwen3-tts/voice/voice_A.wav}"
REF_TEXT="${REF_TEXT:-}"
THREADS="${THREADS:-6}"
# The harness holds the full PyTorch model AND the OpenVINO graphs at once, so 7g OOM-kills
# (exit 137). 13g is the validated default for 0.6B; bump for 1.7B.
MEMORY="${MEMORY:-13g}"
MEMORY_SWAP="${MEMORY_SWAP:-14g}"

if [[ ! -d "$OV_ROOT/$IR_DIR_NAME" ]]; then
  echo "error: IR directory not found: $OV_ROOT/$IR_DIR_NAME" >&2
  exit 1
fi
if [[ ! -f "$REF_AUDIO_PATH" ]]; then
  echo "error: reference audio not found: $REF_AUDIO_PATH (set REF_AUDIO_PATH)" >&2
  exit 1
fi
if [[ "$EXPORTER_IMAGE" == *:exporter-latest ]]; then
  echo "warning: using a moving 'exporter-latest' tag; pin EXPORTER_IMAGE to an immutable tag for reproducible runs." >&2
fi

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

echo ">> stopping $SERVICE to free model memory ..."
compose stop "$SERVICE"

# Always bring the service back, whatever happens to the harness.
restart_service() {
  echo ">> restarting $SERVICE ..."
  compose start "$SERVICE" || compose up -d "$SERVICE" || true
}
trap restart_service EXIT

harness_cmd=(python test_ov_generation.py --model-dir "/ov_output/$IR_DIR_NAME" --threads "$THREADS")
if [[ -n "$COMPRESSION" ]]; then
  harness_cmd+=(--compression "$COMPRESSION")
fi

echo ">> running M4 harness in $EXPORTER_IMAGE against $IR_DIR_NAME ..."
docker run --rm \
  --memory "$MEMORY" --memory-swap "$MEMORY_SWAP" \
  -e "MODEL_SIZE=$MODEL_SIZE" \
  -e "OMP_NUM_THREADS=$THREADS" \
  -e "MKL_NUM_THREADS=$THREADS" \
  -e "REF_AUDIO=/voice/voice_A.wav" \
  ${REF_TEXT:+-e "REF_TEXT=$REF_TEXT"} \
  ${OPENVINO_BUFFER_KV:+-e "OPENVINO_BUFFER_KV=$OPENVINO_BUFFER_KV"} \
  ${OPENVINO_VOCODER_ENABLED:+-e "OPENVINO_VOCODER_ENABLED=$OPENVINO_VOCODER_ENABLED"} \
  ${OPENVINO_VOCODER_DIR:+-e "OPENVINO_VOCODER_DIR=$OPENVINO_VOCODER_DIR"} \
  ${OPENVINO_RELEASE_TORCH:+-e "OPENVINO_RELEASE_TORCH=$OPENVINO_RELEASE_TORCH"} \
  -v "$MODEL_CACHE:/root/.cache/huggingface/hub:rw" \
  -v "$OV_ROOT:/ov_output:rw" \
  -v "$REF_AUDIO_PATH:/voice/voice_A.wav:ro" \
  "$EXPORTER_IMAGE" \
  "${harness_cmd[@]}"

echo ">> done. Report: $OV_ROOT/$IR_DIR_NAME/ov_generation_report.json"
