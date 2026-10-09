# OPS-20260908-3060-CHECKPOINT-DOWNLOAD-028

status: blocked
invocation_status: blocked
task_id: D3060-CHECKPOINT-DOWNLOAD-028
orchestration_epoch: 20260908-3060
role: devops-executor

## Summary

Downloaded the exact `LostGentoo/Qwen3.5-4B-AWQ@main` repository into the authorized
destination `/hy-tmp/models/Qwen3.5-4B-AWQ` using the HF API inventory and resumable
`curl --continue-at - --retry 3 --max-time 900` transfers. Existing partials were
preserved. No `/hy-model` access, server/benchmark start, source/3090 modification, or
deletion was performed.

The files are present and locally complete, but exact remote-size verification remains
incomplete for three small files because repeated HF requests ended with transient TLS
EOF/HTTP 416 responses. No further procedure was selected; extra work requires a new
Task ID.

## Commands and outputs

- Read `AGENTS.md` and the prior storage microcheck/direct-exact reports.
- Remote baseline: `hostname` = `I2aff9805ac001019d1`; destination resolved to
  `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- HF revision API: `API_ID=LostGentoo/Qwen3.5-4B-AWQ`, `API_FILES=12`, HTTP/API request
  succeeded.
- Transfer method: per API-listed path, `curl -fL --continue-at - --retry 3
  --retry-delay 5 --connect-timeout 30 --max-time 900 --output DEST URL`.
- Existing complete files returned HTTP 416 on resume and were retained; large files
  transferred successfully.
- Local verification: `VERIFY_FILES=12`, local aggregate file bytes
  `5,313,539,080`; no local file-size mismatch was found where the expected size was
  available.
- Destination disk usage: `DEST_BYTES_FINAL=7,168,281,608` (includes filesystem
  allocation/metadata); `/hy-tmp` final `df -Pk` showed 45,428,496 KiB available.
- Per-file HF response-header verification passed for:
  `config.json` (10,677), `generation_config.json` (116),
  `model.safetensors.index.json` (102,641), `model_mtp.safetensors` (241,200,704),
  `processor_config.json` (1,191), `recipe.yaml` (1,085), `tokenizer.json`
  (19,989,424), and `tokenizer_config.json` (1,166).
- The same header probe failed transiently for `.gitattributes`, `README.md`, and
  `chat_template.jinja` (TLS unexpected EOF on retries); those local sizes are 1,570,
  4,198, and 7,756 bytes respectively.

## Configuration verification

`config.json` contains:

- `quant_method`: `compressed-tensors`
- quantization format: `pack-quantized`
- bits: `4` (`config_groups.group_0.weights.num_bits`)
- group size: `128`
- symmetric: `true`
- ignored modules: 137 entries in `quantization_config.ignore`, including visual
  blocks/merger, selected linear-attention layers, `lm_head`, and `re:^mtp.*`.

## Changed resources

- Created/continued only files below `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- Temporary remote API/list files were written under `/tmp`.
- No other authorized or prohibited resource was changed.
- SSH secret was not printed or written to the report.

## Open issues

- Exact API-size comparison is incomplete for the three small files listed above due
  transient HF TLS failures; aggregate API byte total could therefore not be completed.
- The initial transfer command exited nonzero solely because resume requests for already
  complete files returned HTTP 416; all 12 local paths exist and local verification
  completed.

## Followups

Issue a fresh Task ID to retry the three remote size probes and close the exact
API-size verification gate. Do not delete or restart the existing download.
