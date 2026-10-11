# G3-PROFILE-C-C8-RESTORE-20260908

ENTRY: ACCEPT

Status: done

Restored the frozen v1 service after the completed C8 candidate run. Authorized
host was `175.155.64.171:22109`; only identity-verified candidate PID `497622`
and its children were stopped. No product files, model files, or benchmark
inputs were changed.

Candidate evidence was preserved remotely at:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-python-20260908/restore/`

The candidate command line was verified before stop as the C8 process on port
18037 with `max-running-requests 8`, Mamba pool 40, and decode graph max 8.
After TERM, port `18037` was absent (`18037_status.txt: ABSENT`).

Frozen v1 restore command:

```text
/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs '{"preserve_thinking": false}' --log-level info
```

PATH began with `/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin`. Restore PID
was `503601`. Verification passed:

- `GET /health`: HTTP 200.
- `/v1/loads?include=all`: idle; running 0, waiting 0; max running 5;
  max total tokens 132436.
- Port 8035 is owned by PID 503601; candidate port 18037 is absent.
- Actual argv retains the frozen model, parser/tool parser, FP8 KV dtype,
  `extra_buffer_lazy` Mamba strategy, and `preserve_thinking=false`.
- Remote raw artifact SHA-256 manifest is `artifacts.sha256`; local copies are
  under `.memory/g3-baseline-20260907/work/raw/g3-profile-c8-python-20260908/restore/`.

Invocation: done

Followups: none.

Open issues: none for this restore.
