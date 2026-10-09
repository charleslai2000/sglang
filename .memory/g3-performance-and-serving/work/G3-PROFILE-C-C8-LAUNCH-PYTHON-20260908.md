# G3-PROFILE-C-C8-LAUNCH-PYTHON-20260908

ENTRY: ACCEPT

Status: done

## Scope

Authorized host `175.155.64.171:22109`; candidate loopback service `127.0.0.1:18037`; no benchmark traffic. The prior v1 service PID `496268` on port 8035 was identity-verified and stopped before launch. No product files, audit hooks, downloads, or unrelated hosts were touched.

## Exact launch

Used `/data/sglang-qwen35-env/bin/python -m sglang.launch_server` with the IQ3_S GGUF, frozen parser/tool/KV/Mamba/template flags, and only candidate capacity knobs:

```text
--max-running-requests 8 --max-mamba-cache-size 40 --cuda-graph-max-bs-decode 8
```

The exact template token was preserved as:

```text
--default-chat-template-kwargs={"preserve_thinking":false}
```

Offline environment variables were set. Effective `/proc/497622/cmdline` is preserved remotely.

## Gates and observations

- Candidate PID: `497622`; port 18037.
- `/health`: HTTP 200.
- `/v1/loads?include=all`: idle, `max_running_requests=8`, `max_total_num_tokens=54093`.
- Weight allocation: 11.857 GB.
- Mamba allocation: pool 40; conv 0.11 GB; SSM 5.77 GB.
- KV allocation: 1.651 GB total; 54,093-token capacity.
- CUDA graph capture completed: prefill 71.45 s; decode 2.61 s; decode batch sizes 1,2,4,8.
- No OOM or startup failure. Only health/load and native startup warmup traffic were observed; no benchmark run was executed.
- Candidate remains running for the separately authorized decode task.

## Remote artifacts

`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-python-20260908/launch/`

Contains `server.log`, `proc_cmdline.txt`, `health.json`, `loads.json`, `nvidia_query.csv`, `key_events.txt`, `launcher_pid.txt`, `start_utc.txt`, and `SHA256SUMS`.

Selected SHA-256 values:

```text
a9b52cda06cfd71a9a495595f4e316e5df34b55534dfe121c058a6e902eb1897  server.log
465f5a6350f58286b59a20ac8290272fd79e8be0e280951fe5f64134243f7ebb  proc_cmdline.txt
6833374d98dfe1e69b2858607b74565003d088d9c058d393d3a25872bf204175  loads.json
77aba11ffa03e00ba45b175f38c93127941f2668abb0ada49d46e328813d0638  nvidia_query.csv
```

## Followups / open issues

Run the separately authorized C8 decode workload, then restore v1 and independently verify. No other work was performed.
