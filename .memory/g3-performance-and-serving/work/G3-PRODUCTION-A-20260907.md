# G3-PRODUCTION-A-20260907 specialist report

- Task ID: `G3-PRODUCTION-A-20260907`
- Orchestration epoch: `E2`
- Specialist role: `devops-executor`
- Authorized host: `root@175.155.64.171:22109`
- Authorized service: `http://127.0.0.1:8035`, PID `298123`
- Evidence window: 2026-09-07 10:02–10:13 UTC
- Result: blocked before warmup or any measured request; no valid C1/C4/C5 score exists.

## Outcome

The exact production-A matrix could not run with the execution-time deployed runner. Four C1 client processes were killed by the Linux OOM killer before dataset preparation completed, before the three authorized warmups, before `POST /flush_cache`, and before any measured `POST /generate`. No `result.jsonl` was produced. C4 and C5 were therefore not started.

The immediate execution-time failure was the runner's `check_chat_template(args.model)` call. `GET /v1/models` returned the raw 11.77 GB GGUF file path, and the deployed `serving.py` passed that file to `AutoTokenizer.from_pretrained` before honoring an explicit `--tokenizer`. Kernel evidence records each killed client near 42.64–42.65 GB anonymous RSS. An explicit tokenizer-directory retry reproduced the same failure because of that call order.

Source inspection then established a second exact-contract conflict: this deployed runner maps `--dataset-name random` to `RandomDataset(random_sample=True)`. Without a valid `--dataset-path`, it calls the Hugging Face download helper for `anon8231489123/ShareGPT_Vicuna_unfiltered`, file `ShareGPT_V3_unfiltered_cleaned_split.json`. The task explicitly prohibits downloading ShareGPT. No ShareGPT cache or approved immutable dataset path was present in the runner's configured Hugging Face cache.

I did not substitute `random-ids`, invent a local dataset JSON, monkeypatch dataset selection, download ShareGPT, edit product code, or alter the frozen v1 profile. Each would require a fresh Task ID because it changes the authorized runner/workload binding or product source.

Required compatibility note: `compat_note: requested fixed-length workload; current runner requires random_range_ratio=1.0`.

## Confirmed baselines

Initial local repository state, captured before remote execution:

- HEAD: `dac6db1ebabdb80209b757fd063cf53e05c091e7`
- Modified: `python/sglang/srt/entrypoints/openai/protocol.py`, `serving_chat.py`, `serving_completions.py`, `python/sglang/srt/sampling/custom_logit_processor.py`, and `test/registered/unit/sampling/test_custom_logit_processor.py`.
- Existing untracked state included `.memory/`, `AGENTS.md`, `CODEX_DPRIME_STATIC_REVIEW.md`, `CODEX_HANDOFF.md`, and `HANDOFF-G3-2026-09-07.md`.
- This specialist added only this local report. A later modification to `python/sglang/benchmark/serving.py` appeared after this task's evidence window and was not made by this invocation.

Execution-time deployed source identity:

- SGLang version: `0.5.10.dev0`.
- Interpreter: `/data/sglang-qwen35-env/bin/python`.
- Editable package path: `/data/sglang-qwen35/python/sglang/__init__.py`.
- `pip show` editable root: `/data/sglang-qwen35/python`.
- `/data/sglang-qwen35` had no Git metadata, so no deployed Git commit was fabricated.
- SHA-256 of the complete execution-time deployed Python-file checksum manifest: `3026151769d78763f0a5c42446293491f7f3366832881f1d916038e0b8f95c1f`.
- Execution-time `serving.py` SHA-256: `0d65ec5e4490eaf5bc999cd11f045688b05ff6a040b6fabc4e5e60faf134e574`.
- Execution-time `datasets/random.py` SHA-256: `a1242f133dfc3d4c5d30a396cedb5351e6d6b447a632091eaf6e6c403beada7c`.
- Model SHA-256: `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810` for `/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`.
- Tokenizer sidecars: `tokenizer.json` `ff085286192c3f94a1b2ff7629c4833abed1a0a09eb38e992a4795a38f8e3716`; `tokenizer_config.json` `34676b1f57e90fccf6cc8e3555cc9f37302718dadd4e92ef61011d082458d238`; `config.json` `995ae9da1c5640b48ae4be7ffaeeb0f4259c71cff55cf0d8df76003e9876e2c6`.

Service command line remained:

```text
/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs {"preserve_thinking": false} --log-level info
```

The command-line SHA-256 was `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`. Preflight `/v1/loads?include=all` resolved `max_running_requests=5`, `max_total_num_tokens=132436`, weight memory `11.857 GB`, KV cache `4.042 GB`, graph memory `1.955 GB`, and token capacity `132436`. KV dtype was confirmed from the real process arguments as `fp8_e4m3`. Both completed post-failure invariant checks passed; health and load endpoints returned HTTP 200, PID `298123` survived, and its arguments were unchanged.

HiCache was disabled, so HiCache/cache device/host/storage fields are `N/A`. The regular radix cache was not flushed because no attempt reached the runner's post-warmup flush stage.

## Exact execution commands

Remote wrapper invocation:

```text
ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=60 -p 22109 root@175.155.64.171 /data/qwen3-g3-baseline/production-A-20260907/<run_id>/run-production-A.sh
```

Initial C1 repeat-1 runner command:

```text
cd /data/sglang-qwen35
PYTHONUNBUFFERED=1 /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving --backend sglang --base-url http://127.0.0.1:8035 --dataset-name random --random-input-len 2048 --random-output-len 512 --random-range-ratio 1.0 --request-rate inf --seed 42 --max-concurrency 1 --num-prompts 20 --output-details --output-file /data/qwen3-g3-baseline/production-A-20260907/G3-PRODUCTION-A-20260907T100230Z/C1/repeat-1/result.jsonl --flush-cache --flush-cache-timeout 60 --warmup-requests 3
```

Repeat 2 used the identical command with `repeat-2/result.jsonl` and `--warmup-requests 0`. The explicit-tokenizer retry used a new immutable run directory and inserted only:

```text
--tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF
```

All requested streaming and ignore-EOS defaults remained enabled: neither `--disable-stream` nor `--disable-ignore-eos` was passed. The wrapper command files preserve every shell-quoted argument.

Telemetry commands used for every started attempt were:

```text
nvidia-smi dmon -s pucvmt -d 1 -o DT
nvidia-smi --query-gpu=timestamp,index,uuid,name,pstate,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,temperature.gpu,clocks.current.sm,clocks.current.memory --format=csv,noheader,nounits
curl -sS --max-time 5 http://127.0.0.1:8035/v1/loads?include=all
```

The query and load samplers ran at one-second intervals. Each `nvidia-smi dmon` PID was recorded and its process/children checked before stopping. Only the identified benchmark wrapper/client/telemetry PIDs were terminated after repeated OOM behavior; PID `298123` was never targeted.

## Point and repeat outcomes

| Run ID / attempt | Point | Repeat | Requested warmups | Client interval (s) | Exit | Measured completions | Actual running concurrency max | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `G3-PRODUCTION-A-20260907T100230Z` default resolution | C1 | 1 | 3 | 48.026 | 137 | 0 | 0 | OOM before warmup |
| `G3-PRODUCTION-A-20260907T100230Z` default resolution | C1 | 2 | 0 | 59.565 | 137 | 0 | 0 | OOM before flush/measurement |
| `G3-PRODUCTION-A-20260907T101034Z` explicit tokenizer | C1 | 1 | 3 | 47.671 | 137 | 0 | 0 | OOM before warmup |
| `G3-PRODUCTION-A-20260907T101034Z` explicit tokenizer | C1 | 2 | 0 | 62.772 | 137 | 0 | 0 | OOM before flush/measurement |
| both run IDs | C1 | 3 | as scheduled | N/A | not completed | 0 | 0 | wrappers stopped after repeat-2 reproduction; partial directories retained |
| both run IDs | C4 | 1–3 | 0 | N/A | not started | 0 | N/A | blocked by C1 pre-request failure |
| both run IDs | C5 | 1–3 | 0 | N/A | not started | 0 | N/A | blocked by C1 pre-request failure |

Runner stderr identifies container client PIDs `336860`, `337354`, `339083`, and `339609`; host-kernel OOM records identify corresponding killed Python processes at approximately 42.64–42.65 GB RSS. All 215 captured `/v1/loads` samples across the four completed failure intervals returned HTTP 200 and reported `num_running_reqs=0`, `num_waiting_reqs=0`, `num_used_tokens=0`, `num_active_tokens=0`, and `gen_throughput=0`.

No runner result JSONL exists. Consequently duration, total input/output tokens, aggregate/input/output/request/per-request throughput, TTFT p50/p95/p99, TPOT p50/p95/p99, full-turn latency p50/p95/p99, and prefill/decode performance fields are all `N/A`, not zero. Request HTTP status is also `N/A` because no generation request was issued; readiness, health, model, load, and post-failure service checks returned HTTP 200. There were no benchmark timeout signals; zero-progress was positively observed.

Raw 1-second query telemetry contains 211 GPU samples across the four completed failure intervals. VRAM stayed at `22802 MiB`. GPU utilization ranged `0–18%`, sampled power `25.41–128.01 W`, and temperature `31–44 C`; these are client-failure intervals, not model performance data. Full dmon/query records remain preserved and are not reported as a production score.

## Remote artifacts and hashes

Primary blocked-evidence root:

```text
/data/qwen3-g3-baseline/production-A-20260907/G3-PRODUCTION-A-20260907T101034Z/
```

Important files:

- `failure-scorecard.json`: SHA-256 `6b1f47c6d6f4a92b76d0fe6be95b64d46c6f4de2af19a9233b90e699515be466`.
- `failure-scorecard.csv`: SHA-256 `37f97f30768b5b2a424e4e3429c91469e1b27d0e55d8c57aea64d7b4f26f3bba`.
- `BLOCKED.json`: SHA-256 `ca1cc7421ec75df932ea987cde0bf2174533ca6c2ecf4f701c3f5184dd7faa7b`.
- `run-production-A.sh`: SHA-256 `b25b4be747847f5469748336ae60f10af8e05bcb5ea2b370fdb0ff3297c9a6c5`.
- `artifacts.sha256`: SHA-256 `4301c7a6dab75fd29f2e5b0261bf6f572acec337abbd73d5b2a5f4897ed198b2`.
- `artifacts-manifest.sha256`: SHA-256 `d3a1b18397b93cac95d50c917ad79dfc00023e8416c498e22a36ac0650c7c1b5`.

Initial failed-evidence root:

```text
/data/qwen3-g3-baseline/production-A-20260907/G3-PRODUCTION-A-20260907T100230Z/
```

- Initial `run-production-A.sh`: SHA-256 `28280271085cf9403fd323af834c14d49007539383787608b69caef5f848ad94`.
- `artifacts.sha256`: SHA-256 `77171d6c6b05493be907836776f140f2c8ba1fc58176a8d3c55e46d171d0c94c`.
- `artifacts-manifest.sha256`: SHA-256 `c0ad93ffd9ed1361aec5cff797a9c837991734a696fb6a377e4459cbb945e760`.

Each started repeat directory contains the exact command, runner stdout/stderr, exit code when completed, timestamps, raw `nvidia-smi dmon`, raw one-second GPU query samples, raw one-second load snapshots with HTTP status, pre/post query/load snapshots, telemetry PID records, and server-log byte-range delta. The local task tree was not populated with copies because the dispatch separately restricted local writes to this specialist report; remote artifacts and hashes are complete.

## Terminal-claim gate and required decision

Observed facts, tested assumptions, and rejected bypasses are preserved in `failure-evidence/terminal-claim-gate.txt`. The minimal unblock is a fresh Task ID that does one of the following explicitly:

1. authorizes the already-deployed runner compatibility fix plus `--dataset-name random-ids --tokenize-prompt` as the synthetic payload binding; or
2. supplies and authorizes an immutable existing JSON path for `--dataset-name random --dataset-path ...`, including its SHA-256 and prompt-corpus semantics; or
3. authorizes a specific non-product wrapper that changes `RandomDataset` to random IDs while retaining the requested display label.

A different `random-ids` benchmark and a later `serving.py` change were observed after this task's evidence window under another artifact directory. They were not touched or incorporated into this report.

Invocation final status: blocked
