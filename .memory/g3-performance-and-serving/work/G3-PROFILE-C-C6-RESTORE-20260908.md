# G3-PROFILE-C-C6-RESTORE-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-C6-RESTORE-20260908
epoch: E4
role: devops-executor

## Result

Restored the unchanged frozen v1 service after the completed C6 candidate
measurement. No product files, model files, profile flags, or benchmark inputs
were changed.

## Candidate stop evidence

- Authorized host: `175.155.64.171:22109` only.
- Identity-verified candidate PID `488839` had port `18036` and C6 argv:
  `--max-running-requests 6 --max-mamba-cache-size 32
  --cuda-graph-max-bs-decode 8`, with the frozen parser, tool parser, FP8 KV,
  Mamba strategy, and template flags.
- Explicit descendants `488990`, `488991`, and `488992` were also identity
  checked and sent `SIGTERM`.
- Port `18036` was absent after stop; no unrelated process was targeted.

## Exact restore

Remote restore artifacts:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-equals-20260908/restore/`

Local copy:
`.memory/g3-baseline-20260907/work/raw/g3-profile-c6-equals-20260908/restore/`

The exact command is preserved in `restore/v1.command`. It uses PATH beginning
with `/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin` and the unchanged v1
flags:

```text
/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code \
  --reasoning-parser auto --tool-call-parser qwen3_coder \
  --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs '{"preserve_thinking": false}' --log-level info
```

Restore wrapper PID: `494280`.

## Verification

- `GET http://127.0.0.1:8035/health`: HTTP 200.
- `/v1/loads?include=all`: idle, `num_running_reqs=0`,
  `max_running_requests=5`, `max_total_num_tokens=132436`, one RTX 3090.
- Port 8035 is owned by PID 494280; candidate port 18036 is absent.
- Actual process argv retains model, `reasoning-parser auto`,
  `tool-call-parser qwen3_coder`, `kv-cache-dtype fp8_e4m3`,
  `mamba-radix-cache-strategy extra_buffer_lazy`, and
  `preserve_thinking=false`.
- Model SHA-256:
  `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- No benchmark client, dmon, download, or product edit was performed.

## Open issues

None. C6 performance evidence remains in the separately assigned decode
artifacts; this report makes no throughput claim.

Final status: **done**
