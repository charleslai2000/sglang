#!/usr/bin/env bash
# Frozen Round-1 attempt launcher.
#
# STATUS: RECORDED, NOT RUN during the freeze (no model endpoints exist yet).
#
# Fairness contract (frozen):
#   Allowed model-specific differences: (a) endpoint/base URL, (b) model name,
#   (c) required chat-template/protocol adapter.
#   NOT allowed: model-specific prompts, tools, repo hints, turn limits.
# This launcher therefore only ever passes (a), (b), (c) as `-c key=value`
# overrides on top of the single frozen config; everything else is identical.
set -euo pipefail

: "${SWE_MODEL_NAME:?set SWE_MODEL_NAME (e.g. openai/qwen3-27b)}"
: "${SWE_API_BASE:?set SWE_API_BASE (e.g. http://127.0.0.1:30000/v1)}"
: "${SWE_OUTPUT_DIR:?set SWE_OUTPUT_DIR for this model's run}"
SWE_SEED="${SWE_SEED:-0}"
SWE_VENV="${SWE_VENV:-/home/ubuntu/venvs/mini-swe-agent}"
SWE_DATASET_DIR="${SWE_DATASET_DIR:-/home/ubuntu/swe-round1/data/swe-verified-78f471bf}"
SWE_CONFIG="${SWE_CONFIG:-/home/ubuntu/swe-round1/config/round1-swebench-local.yaml}"
SWE_FILTER_FILE="${SWE_FILTER_FILE:-/home/ubuntu/swe-round1/data/blind24-filter.txt}"
SWE_WORKERS="${SWE_WORKERS:-1}"

mkdir -p "$SWE_OUTPUT_DIR"
SWE_FILTER="$(cat "$SWE_FILTER_FILE")"

SPECS=(
  -c "model.model_name=${SWE_MODEL_NAME}"
  -c "model.model_kwargs.api_base=${SWE_API_BASE}"
  -c "model.model_kwargs.seed=${SWE_SEED}"
)

# (c) optional required protocol adapter (e.g. chat_template_kwargs).
if [[ -n "${SWE_PROTOCOL_ADAPTER_SPECS:-}" ]]; then
  while IFS= read -r spec; do
    [[ -n "$spec" ]] && SPECS+=(-c "$spec")
  done <<< "${SWE_PROTOCOL_ADAPTER_SPECS}"
fi

exec "$SWE_VENV/bin/mini-extra" swebench \
  --subset "$SWE_DATASET_DIR" \
  --split test \
  --filter "$SWE_FILTER" \
  -c "$SWE_CONFIG" \
  "${SPECS[@]}" \
  -w "$SWE_WORKERS" \
  -o "$SWE_OUTPUT_DIR"
