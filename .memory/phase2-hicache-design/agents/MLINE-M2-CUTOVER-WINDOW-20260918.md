# MLINE-M2-CUTOVER-WINDOW-20260918

Task: Make M2 (`/data/models/omnicoder-9b-gptq-int4`) the `:30000` production service, healthy
and verified. M1 (`/data/models/qwen35-9b-w4a16`) is only a fallback.

Scope: State determination (read-only) → M1 baseline capture → stop M1 via `stop.sh prod` →
launch M2 sequentially on the one RTX 3090 → validate health/models/deterministic chat/
coder-style/tool-call/throughput → on failure restore M1. No product source, test, frozen-tree,
or git modification. No `pkill`.

Result: **DONE — `:30000` now serves M2 (OmniCoder-9B GPTQ-INT4), healthy and verified.**
No rollback was needed. State found at start was `M1_UP`; M1 was stopped cleanly and M2 came up
in 89 s cold start. All Step-4 validation passed.

Budget: 15 min allowed for M2 start attempts; M2 cold start took 89 s (one attempt, 0 retries).
Evidence window: 2026-09-18 10:02–10:11 UTC.

Terminal state: DONE

---

## Step 1 — State classification (read-only)

**Classification: `M1_UP`.** The prior 402-died attempt did NOT stop M1.

At 2026-09-18 10:02–10:04 UTC, before any action:

```
$ ss -ltnp | grep :30000
LISTEN 0  2048  0.0.0.0:30000  0.0.0.0:*  users:(("python",pid=1761822,fd=68))

$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health
200
$ curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.250:30000/health
200
$ curl -s http://127.0.0.1:30000/v1/models
{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16","object":"model","created":1789726048,"owned_by":"sglang","root":"/data/models/qwen35-9b-w4a16","parent":null,"max_model_len":131072}]}
```

PID 1761822 argv (`/proc/1761822/cmdline`, verbatim): `--model-path /data/models/qwen35-9b-w4a16
--host 0.0.0.0 --port 30000 ...` (the M1 frozen argv). `ps -o pid,ppid,lstart`:
`1761822 1761795 Fri Sep 18 08:42:26 2026`.

```
$ nvidia-smi
|   0  NVIDIA GeForce RTX 3090 ... |  22573MiB / 24576MiB |   0%  Default |
|    0   N/A  N/A  1761822  C  ....2.1-candidate/env/bin/python   300MiB |
|    0   N/A  N/A  1762267  C  sglang::scheduler                22198MiB |
```

Lock `/tmp/opencode/gpu-3090.lock`:
`{"owner": "supervise-prod-prod-20260918T084226Z-1761580", "pid": 1761795, "generation": 20, "acquired": "2026-09-18T08:42:26Z"}`.
`state/gpu-owner.json`: role=prod, state=held, pid=1761822, port=30000, identity=LOCAL-PROD-v1.2.1.

No stray M2 process existed (ps sweep: 0 matches for `omnicoder-9b-gptq-int4`).

## Step 2 — Action taken by state

`M1_UP` → captured the M1 comparison baseline ONCE, then stopped M1, then started M2.

M1 stop (canonical entrypoint, identity-checked, no `pkill`):

```
$ timeout 300 bash /tmp/opencode/prod-service-20260917/bin/stop.sh prod
[10:08:22] prod: terminating supervisor pid=1761795 (SIGTERM)
[10:08:22] stopping owned server pid=1761822 (SIGTERM, graceful)
[10:08:36] server pid=1761822 stopped
[10:08:36] prod: stopped
[10:08:36] GPU released; state published as free
rc=0
```

Immediately after: `NO LISTENER on :30000`; `nvidia-smi --query-compute-apps` header-only (empty);
GPU `1 MiB, 24124 MiB`; lock flock `LOCK_FREE`; `gpu-owner.json` role=free/state=free/pid=null.

## Step 3 — M2 launch command

No M2 profile exists under `3090-dev/`: `grep -rIl 'omnicoder' 3090-dev` returned nothing and
every frozen launcher (`v1`, `v1.1`, `v1.1.2`, `v1.2`, `v1.2.1`) hardcodes
`--model-path /data/models/qwen35-9b-w4a16`. The M1 `launcher/launch.sh` is fail-closed on the
M1 model path and on `SGLANG_RUN_ID`/L3, so it cannot launch M2.

The **only existing M2 configuration with successful bring-up evidence** is
`m2-bringup-smoke-20260916` (report.json `status=completed`, `startup_s=86.07`,
`vram_after_load_mib=18651`, decode `83.4 tok/s`, `gptq_marlin`, no fallback). It uses explicit
`PYTHONPATH` + `python -m sglang.launch_server` (NOT the M1-pinned launcher), MTP off, L3 off.
The M2 launch for this window is derived from that proven profile. I preferred it over invention.

M2 argv vs M1 frozen argv — every change and its reason:

| Flag | M1 | M2 | Reason |
|---|---|---|---|
| `--model-path` | qwen35-9b-w4a16 | omnicoder-9b-gptq-int4 | target model (required) |
| `--host` | 0.0.0.0 | 0.0.0.0 | retained, production LAN bind |
| `--port` | 30000 | 30000 | retained, target port |
| `--tp-size` | 1 | 1 | single GPU |
| `--mem-fraction-static` | 0.92 | 0.92 | retained measured profile |
| `--context-length` | 131072 | 131072 | retained; M2 supports 262144 but 128K prod profile kept |
| `--max-total-tokens` | 524288 | **262144** | M2 weights load 10.97 GB vs M1 ~9.6 GB; M1's 524288 KV (8 GB) does not fit the 24 GiB 3090 with M2 (measured: 262144 KV = 4 GB, avail 5.86 GB) |
| `--max-running-requests` | 8 | 8 | retained C8 profile |
| `--max-mamba-cache-size` | 48 | 48 | same linear-attn/Mamba arch |
| `--kv-cache-dtype` | fp8_e4m3 | fp8_e4m3 | retained (verified: `dtype: torch.float8_e4m3fn`) |
| `--attention-backend` / `--linear-attn-*-backend` / `--mamba-radix-cache-strategy` / `--mamba-ssm-dtype` | flashinfer/triton/triton/extra_buffer/float32 | same | same Qwen3_5 text architecture |
| `--enable-hierarchical-cache` (+write-policy/storage-backend/storage-prefetch/hicache-size) | on | **off** | `/data/l3` is 96% full (21 GiB free, `df -h`); M2+extent L3 is unproven; proven M2 profile omits L3 |
| `--enable-ready-horizon` | on | **off** | part of the HiCache/Ready-Horizon L3 stack; off with L3 |
| `--reasoning-parser` | qwen3 | qwen3 | M2 chat template emits `<think>`/`reasoning_content` (template lines 90–101, 148–152) |
| `--tool-call-parser` | qwen3_coder | qwen3_coder | M2 template uses the qwen3_coder `‹tool_call›/‹function=…›` XML (template lines 46–60) |
| `--disable-prefill-cuda-graph` | set | set | retained; decode graph default `full` |
| `--enable-metrics --export-metrics-to-file --export-metrics-to-file-dir` | on | on (new run dir) | retained |

Deliberate deviation: the M1 `supervise.sh` path is bypassed (it invokes the M1-pinned launcher).
M2 is launched by `launch-m2.sh`, which itself takes and holds the canonical flock for the whole
server lifetime, so GPU mutual exclusion is preserved.

## Step 4 — Validation (all passed)

- `/health` 200 loopback **and** LAN `192.168.20.250`: PASS.
- `/v1/models` 200 with served id `/data/models/omnicoder-9b-gptq-int4`, `max_model_len=131072`
  (loopback and LAN): PASS.
- One deterministic chat completion (`temperature=0`, `max_tokens=1024`): HTTP 200,
  `content="\n\n4"`, non-empty and coherent (reasoning budget avoided the empty-content trap).
- One coder-style prompt: HTTP 200, `content="\n\n{\"name\": \"Ada\", \"age\": 36}"` — valid JSON,
  no corruption.
- Tool-call style: HTTP 200, `finish_reason="tool_calls"`,
  `tool_calls[0].function={"name":"get_weather","arguments":"{\"city\": \"Paris\"}"}`.
- Throughput sample (N=3 non-streaming, `max_tokens=400`, `temperature=0`): 80.7 tok/s aggregate.
- Streaming TTFT (N=3, `max_tokens=200`): 0.159 s / 0.113 s / 0.114 s.

## M1 vs M2 comparison (owner's "is M2 much better?")

Same method for both: same host, frozen v1.2.1 tree, temp=0, non-streaming, `max_tokens=400`,
3 requests of "Write a short paragraph about why caching helps web performance."

| Metric | M1 (qwen35-9b-w4a16) | M2 (omnicoder-9b-gptq-int4) |
|---|---|---|
| Cold start | 132 s (recorded) | 89 s (this run) |
| Aggregate tokens/s (N=3×400) | 86.5 tok/s | 80.7 tok/s |
| Streaming TTFT | ~0.48 s (prior artifact) | 0.11–0.16 s |
| Deterministic 2+2 | `"\n\n4"` | `"\n\n4"` |
| Coder JSON output | `{"name": "Ada", "age": 36}` | `{"name": "Ada", "age": 36}` |
| Tool call | `get_weather({"city":"Paris"})` | `get_weather({"city":"Paris"})` |
| Quant dispatch | pack-quantized (W4A16) | GPTQ int4 → `gptq_marlin`, 0 fallbacks |
| GPU VRAM | 22.1 GiB | 19.1 GiB |

Observation: on this box/configuration M2 is **not clearly "much better"** than M1 in raw decode
throughput — it is ~7% slower (80.7 vs 86.5 tok/s), though it starts faster and uses ~3 GiB less
VRAM. Behavioral quality on the smoke prompts is equivalent. Throughput/quality alone is not a
decisive win; the case for M2 would rest on coding-task evaluations and the smaller VRAM
footprint, which are outside this window.

M1 baseline captured (before stopping M1):
- loopback health=200, LAN health=200
- models: `{"id":"/data/models/qwen35-9b-w4a16", ... "max_model_len":131072}`
- chat: HTTP 200, `total_s=1.928`, `content="\n\n4"`, `completion_tokens=162`
- coder JSON: HTTP 200, `total_s=3.600`, `content="\n\n{\"name\": \"Ada\", \"age\": 36}"`
- tool call: HTTP 200, `finish_reason=tool_calls`, `get_weather({"city":"Paris"})`
- throughput: req1 82.8, req2 88.6, req3 88.3 → **1200 tok / 13.876 s = 86.5 tok/s**

## Evidence

### Final state — what serves `:30000` right now

```
$ ss -ltnp | grep :30000
LISTEN 0  2048  0.0.0.0:30000  0.0.0.0:*  users:(("python",pid=1764114,fd=68))

$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:30000/health      → 200
$ curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.250:30000/health → 200
$ curl -s http://192.168.20.250:30000/v1/models
{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4","object":"model","created":1789726264,"owned_by":"sglang","root":"/data/models/omnicoder-9b-gptq-int4","parent":null,"max_model_len":131072}]}

$ cat /tmp/opencode/prod-service-20260917/state/gpu-owner.json
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "prod", "state": "held", "pid": 1764114, "port": 30000,
  "run_id": "m2-cutover-20260918T100839Z-1764091",
  "l3_namespace": "",
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate",
  "identity": "M2-OMNICODER-9B-GPTQ-INT4",
  "lock_generation": 21, "updated_at_utc": "2026-09-18T10:08:39Z",
  "note": "serving M2 (cutover window; direct launch_server, L3 off)"
}

$ nvidia-smi
NVIDIA GeForce RTX 3090, 19107 MiB, 5018 MiB, 24576 MiB, 0 %
1764114, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1764226, sglang::scheduler, 18792 MiB
```

PIDs / logs:
- supervisor (holds canonical flock, pid 1764091, fd 9 → `/tmp/opencode/gpu-3090.lock`)
- server 1764114, scheduler 1764226, detokenizer 1764227
- log dir `/tmp/opencode/MLINE-M2-CUTOVER-20260918/logs/m2-cutover-20260918T100839Z-1764091/`
  (`driver.log`, `server.console.log`, `launch_argv.txt`, `sglang-request-metrics-20260918_10.log`)

Effective M2 argv (`/proc/1764114/cmdline`, verbatim):

```
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server
--model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000
--tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072
--max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3
--attention-backend flashinfer --linear-attn-prefill-backend triton
--linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer
--mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder
--enable-metrics --export-metrics-to-file
--export-metrics-to-file-dir /tmp/opencode/MLINE-M2-CUTOVER-20260918/logs/m2-cutover-20260918T100839Z-1764091
--disable-prefill-cuda-graph
```

`/proc/1764114/environ`:
`PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`,
`CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587`.

### Deterministic chat (M2), verbatim

```json
{"id":"fba7dd3e87024d5ba0a80479ae39f1e1","object":"chat.completion","created":1789726222,"model":"/data/models/omnicoder-9b-gptq-int4","choices":[{"index":0,"message":{"role":"assistant","content":"\n\n4","reasoning_content":"Thinking Process:\n\n1.  **Analyze the Request:**\n    *   Question: \"What is 2+2?\"\n    *   Constraint: \"Answer with just the number.\"\n\n2.  **Determine the Answer:**\n    *   2 + 2 = 4.\n\n3.  **Format the Output:**\n    *   The user explicitly requested *just the number*.\n    *   No text, no explanations, no punctuation (unless it's part of the number, but \"4\" is sufficient).\n\n4.  **Final Decision:**\n    *   Output: 4\n\n5.  **Review against constraints:**\n    *   Is it just the number? Yes.\n    *   Is it the correct answer? Yes.\n\n6.  **Construct Output:** 4\n","tool_calls":null},"logprobs":null,"finish_reason":"stop","matched_stop":248046}],"usage":{"prompt_tokens":23,"total_tokens":200,"completion_tokens":177,"prompt_tokens_details":null,"reasoning_tokens":174}}
HTTP=200 total_s=2.218641 ttfb_s=2.218530
```

### Coder-style JSON (M2), content field

```json
"content":"\n\n{\"name\": \"Ada\", \"age\": 36}"
HTTP=200 total_s=3.935551
```

### Tool call (M2), verbatim

```json
"tool_calls":[{"id":"call_85b2e9224eb64b5585f8c00c","index":0,"type":"function","function":{"name":"get_weather","arguments":"{\"city\": \"Paris\"}"}}]
"finish_reason":"tool_calls"
HTTP=200 total_s=1.022674
```

### Throughput (M2)

```
req1: completion_tokens=400 wall_s=4.987 tps=80.2
req2: completion_tokens=400 wall_s=4.989 tps=80.2
req3: completion_tokens=400 wall_s=4.895 tps=81.7
AGGREGATE: tokens=1200 wall_s=14.872 tokens_per_s=80.7
```

### Streaming TTFT (M2)

```
req1: ttft_s=0.1593 chunks=200 total_s=2.542
req2: ttft_s=0.1125 chunks=200 total_s=2.494
req3: ttft_s=0.1141 chunks=200 total_s=2.496
```

### GPTQ dispatch / memory / graph (M2 server log)

```
[10:08:53] The model is convertible to gptq_marlin during runtime. Using gptq_marlin kernel.
[10:08:39 → 10:09:39] Load weight end. elapsed=7.57 s, type=Qwen3_5ForConditionalGeneration,
                       quant=gptq, bits=4, avail mem=12.27 GB, mem usage=10.97 GB.
[10:09:54] Mamba Cache is allocated. max_mamba_cache_size: 48, conv_state size: 0.05GB, ssm_state size: 2.30GB
[10:09:54] KV Cache is allocated. dtype: torch.float8_e4m3fn, #tokens: 262144, K size: 2.00 GB, V size: 2.00 GB
[10:09:54] Memory pool end. avail mem=5.86 GB
[10:09:55] Capture target decode CUDA graph begin. backend=full, num_tokens_per_req=1, bs=[1, 2, 4, 8]
[10:09:59] Capture target decode CUDA graph end. elapsed=4.51 s
```

Counts: `Using gptq_marlin kernel` = 4; `UnquantizedLinearMethod` = 0; fallback lines = 0.

Startup timings from log: `load_weight=7.57, scheduler_e2e=49.22, tokenizer_e2e=65.18,
cuda_graph.decode=4.51`. `/health` first 200 at 10:10:08 → **89 s** after launch.

### Negative self-checks (real output)

1. Exactly ONE `launch_server` process:
   ```
   launch_server count = 1
     1764114 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server
   ```
2. No stale M1 (`qwen35-9b-w4a16`) process; the only `omnicoder-9b-gptq-int4` matches are the live
   M2 server and a transient probe-shell cmdline (pid 1764702 = my own probe wrapper), not a
   second server.
3. Only `:30000` listener is M2: `LISTEN 0 2048 0.0.0.0:30000 ... users:(("python",pid=1764114,fd=68))`.
4. Canonical flock is HELD by the M2 supervisor (negative test fails as required):
   ```
   $ cat /tmp/opencode/gpu-3090.lock
   {"owner": "m2-cutover-m2-cutover-20260918T100839Z-1764091", "pid": 1764091, "generation": 21, "acquired": "2026-09-18T10:08:39Z"}
   $ ls -l /proc/1764091/fd/9
   lrwx------ ... 9 -> /tmp/opencode/gpu-3090.lock
   $ python3 -c "fcntl.flock(...LOCK_NB)"
   BlockingIOError: [Errno 11] Resource temporarily unavailable
   ```
5. Frozen tree unchanged: `sha256sum launcher/launch.sh` =
   `4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5` (matches identity.json)
   and `sha256sum manifest/TREE-SHA256.txt` =
   `5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950` (matches recorded
   `tree_manifest_sha256_self`/`TREE_HASH`). `launch.sh` mtime still Sep 17 21:16.

## Defects / blockers

No blockers. Observations recorded for the orchestrator:

1. **M2 cannot be launched by the frozen `launcher/launch.sh`.** It is fail-closed on
   `--model-path /data/models/qwen35-9b-w4a16` and on the L3 `SGLANG_RUN_ID` namespace gate. A
   `:30000` M2 service therefore runs a different supervisor than M1's scaffold, and
   `state/gpu-owner.json` is published manually by `launch-m2.sh` (not by `supervise.sh`). A
   long-term M2 line needs its own frozen tree/launcher with an M2 model path and its own
   identity gate — this is a follow-on, not something this window should have built.
2. **`/data/l3` is at 96% (21 GiB free).** M2 was run with HiCache/L3 OFF for this reason. If the
   owner wants M2 with the 3-tier cache, L3 capacity must be addressed first (and the M2+extent
   combination is not yet proven — the only proven M2 bring-up also ran L3 off).
3. **`gpu-owner.json.identity` is `M2-OMNICODER-9B-GPTQ-INT4`**, a label authored by this window,
   because the M2 path has no frozen `manifest/identity.json`. It is a descriptive label, not a
   cryptographically verified identity.
4. **`/get_server_info.quantization` is `null`** even though the model is GPTQ; the authoritative
   quant evidence is the server log (`quant=gptq, bits=4` + `Using gptq_marlin kernel`).
5. M2 `tool_calls` here were produced by `--tool-call-parser qwen3_coder` on M2's template, which
   uses the same XML convention; this is consistent, not a defect.

## Remaining claims / exclusions

- **Claimed:** `:30000` serves M2, health/models/chat/coder/tool-call/throughput verified in the
  10:02–10:11 UTC window. M1 baseline captured on the same host in the same window.
- **Not claimed:** long-duration stability or load behavior beyond the bounded smoke above; any
  M2 quality advantage on coding benchmarks (smoke prompts show parity); M2 vision E2E (prior
  bring-up marked vision inconclusive on a small token budget); M2 with HiCache/L3 enabled.
- **Not claimed:** that M2's served bytes are cryptographically the owner-settled OmniCoder
  identity — provenance was settled by the owner and was not re-litigated here.
- **Excluded:** product source/tests/frozen-tree/git modification (none made); `pkill` (not used);
  M1 restore (not needed — M2 passed); L3 namespace allocation (L3 off).

## Changed-artifact list

- `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/MLINE-M2-CUTOVER-WINDOW-20260918.md`
  (this report — the only file written under the repo).
- New scratch artifacts (not product source):
  - `/tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh` (M2 launch path)
  - `/tmp/opencode/MLINE-M2-CUTOVER-20260918/logs/m2-cutover-20260918T100839Z-1764091/`
    (`driver.log`, `server.console.log`, `launch_argv.txt`, `server.pid`, metrics)
  - `/tmp/opencode/MLINE-M2-CUTOVER-20260918/{M1-models.json,M1-health-*.txt,M1-server-ps.txt,
    M1-argv.txt,M2-models.json,M2-models-lan.json,M2-argv.txt,M2-smoke.json,M2-coder.json,
    M2-tool.json,M2-throughput.txt,M2-ttft.txt,M2-server-info.txt,neg-*.txt,stop-m1.out}`
- Runtime state written by the launch path itself: `/tmp/opencode/gpu-3090.lock` (generation
  20→21), `/tmp/opencode/prod-service-20260917/state/gpu-owner.json`.
- No product source, tests, frozen tree, or git state changed.

## Commands (verbatim)

M2 launch command (what is running now, via supervisor `launch-m2.sh`):

```
setsid bash /tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh
```

Underlying server argv it execs is the effective argv quoted above; a re-run reuses
`launch-m2.sh` unchanged (it allocates a fresh run id / log dir and re-takes the canonical flock).

M1 rollback command (only needed if M2 had failed; not executed in this window):

```
bash /tmp/opencode/prod-service-20260917/bin/start.sh prod
```

M1 stop command used (verbatim, executed once):

```
timeout 300 bash /tmp/opencode/prod-service-20260917/bin/stop.sh prod
```

## Final statement

**What serves `:30000` right now: M2** — server pid 1764114, scheduler 1764226, supervisor/
lock-holder 1764091, model `/data/models/omnicoder-9b-gptq-int4`, health 200 loopback+LAN.
**GPU state:** RTX 3090, 19107 MiB used / 5018 MiB free / 24576 MiB, 0% util; compute apps are
the M2 server (300 MiB) and `sglang::scheduler` (18792 MiB). Canonical lock generation 21, held
by the M2 supervisor; `gpu-owner.json` role=prod/state=held/pid=1764114.

Terminal state: DONE
