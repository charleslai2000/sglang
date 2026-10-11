# G3 Profile C1 restore2 — 2026-09-08

ENTRY: ACCEPT

Final status: **done**

Authorized target was `175.155.64.171:22109` only. The identified C1 candidate
PID `478926` was identity-checked and stopped with TERM; no other candidate or
production PID was targeted. Candidate port `127.0.0.1:18035` is absent.

Frozen v1 was restored on `127.0.0.1:8035` using the prior command and the
offline/no-proxy environment. Restore PID is `482817`; health is HTTP 200 and
`/v1/loads?include=all` reports zero running and waiting requests.

Exact restore command:

```text
/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs={"preserve_thinking": false} --log-level info
```

Observed loads: `max_total_num_tokens=132436`, `max_running_requests=5`,
weight `11.857 GB`, KV `4.042 GB`, graph `1.955 GB`; all request counters are
zero. Frozen parser/tool/KV/Mamba/template flags are present in the captured
argv. No product files, model files, or service configuration were changed.

Remote artifacts:
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-decode-retry2-20260908/restore2/`

Key artifacts include `candidate-before.ps`, `candidate-before.cmdline`,
`stop-status`, `restore-v1.log`, `restore.ps`, `restore.cmdline`,
`listeners.txt`, `loads.json`, and `artifacts.sha256`.

Open issues: none for this restore. Any further benchmark or process action
requires a fresh Task ID.
