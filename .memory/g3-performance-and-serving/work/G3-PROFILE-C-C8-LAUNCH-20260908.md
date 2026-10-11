# G3-PROFILE-C-C8-LAUNCH-20260908

ENTRY: ACCEPT

Status: blocked

The authorized C8 admission attempt did not start because the shell-safe
equals-form for `--default-chat-template-kwargs` was rejected by this checkout's
CLI JSON parser. No benchmark request or candidate traffic was sent. The
explicitly identified v1 service was restored and is healthy on port 8035.

## Scope and command

Host: `175.155.64.171:22109`, root, passwordless SSH key. Candidate port:
`127.0.0.1:18037`. Frozen v1 PID before transition: 494280, port 8035.

Candidate command attempted (only capacity knobs changed):

```text
/data/sglang-qwen35-env/bin/python -m sglang.launch_server \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 18037 --tp-size 1 --pp-size 1 --trust-remote-code \
  --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 \
  --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs={"preserve_thinking":false} \
  --max-running-requests 8 --max-mamba-cache-size 40 \
  --cuda-graph-max-bs-decode 8 --log-level info
```

The candidate exited before model loading with:

```text
sglang serve: error: argument --default-chat-template-kwargs: invalid loads value: '{preserve_thinking:false}'
```

This is a runner/quoting incompatibility, not a C8 capacity result. Do not
interpret it as OOM or an admission failure.

## Rollback and verification

The identity-verified v1 tree (PID 494280 and its children) was stopped before
the candidate attempt. v1 was relaunched with the frozen flags and is healthy:

```text
PID 496268
/data/sglang-qwen35-env/bin/python -m sglang.launch_server ... --host 127.0.0.1 --port 8035 ... --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs={"preserve_thinking":false}
HTTP GET http://127.0.0.1:8035/health -> 200
LISTEN 127.0.0.1:8035 by PID 496268
127.0.0.1:18037 absent
```

No product files, model weights, or source files were changed. No download,
benchmark traffic, audit hook, or monitoring injection was used.

## Artifacts

Remote directory:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-20260908/launch/`

- `server.log` SHA-256 `fdb9c04e0c7b322117ec6e3e2f3f64bbc7035acd8d78510ea5f07152c197ef7f`
- `v1_restore.log` SHA-256 `87392d32c56f12ebb55f25faec390dfa7c50404fe227804544c9b6aab7cda327`
- `evidence.txt`, `pre_ps.txt`, `server.pid`, `v1_restore.pid`, and startup timestamps

## Follow-up

Fresh Task ID is required for any retry using the checkout's accepted JSON
argument form. No C8 capacity conclusion is supported by this attempt.

invocation: blocked
open_issues: CLI rejected the specified shell-safe equals-form before startup; v1 restored healthy.
