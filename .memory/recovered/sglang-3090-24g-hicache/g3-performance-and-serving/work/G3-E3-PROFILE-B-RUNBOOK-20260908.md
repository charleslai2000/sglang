# G3-E3-PROFILE-B-RUNBOOK-20260908

ENTRY: ACCEPT

Task ID: `G3-E3-PROFILE-B-RUNBOOK-20260908`; epoch E3; role `devops`.
Invocation status: **done**.

This is a design-only, execution-ready runbook. It performed no benchmark
request, remote write, process signal, restart, download, source/model edit,
audit injection, tracing, or instrumentation. The only local write is this
report. Execution requires the separate launch/admission task and its
dependent decode/prefill/restore tasks; this task is not authority to transition
the host.

## 1. Observed baseline and boundaries

Only `root@175.155.64.171:22109` is in scope. At read-only inspection on
2026-09-07 UTC (local 2026-09-08), unchanged v1 was:

```text
PID/listener: 298123 / 127.0.0.1:8035; health HTTP 200; loads idle
version: SGLang 0.5.10.dev0; Python 3.12.0
interpreter: /data/sglang-qwen35-env/bin/python
source/cwd: /data/sglang-qwen35 /data/sglang-qwen35
model: /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
model md5: a37cff66ad81b0e6311d4b6671ac2b09
runner: /data/sglang-qwen35/python/sglang/benchmark/serving.py
runner sha256: 01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb
server_args.py sha256: aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9
```

Observed v1 argv, also the exact rollback argv:

```text
/data/sglang-qwen35-env/bin/sglang serve --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs {"preserve_thinking": false} --log-level info
```

Frozen quality/runtime settings are the model/weights, native SGLang engine,
`--reasoning-parser auto`, `--tool-call-parser qwen3_coder`,
`--kv-cache-dtype fp8_e4m3`, `--mamba-radix-cache-strategy extra_buffer_lazy`,
and `--default-chat-template-kwargs {"preserve_thinking": false}`. B does not
change these, tokenizer files, sampling, prompts, or weights.

The current v1 `/v1/loads?include=all` and startup log report
`max_total_num_tokens=132436`, `max_running_requests=5`,
`max_mamba_cache_size=23` (four Mamba state slots/request), Mamba conv/SSM
allocation 0.07/3.38 GB, KV K/V allocation 2.02/2.02 GB, decode CUDA graph
max batch 24, prefill max batch 2048, and resolved `mem_fraction_static=0.833`.
Tokenizer sidecars are present. Port 8036 was free at inspection but is not
reserved and must be rechecked immediately before launch.

## 2. Exact temporary Profile B contract

Temporary B binds loopback **8036**. If 8036 is occupied at the transition
gate, do not select another port: record the occupant and request a fresh
Task ID/runbook. This avoids silently changing the artifact contract.

These capacity/scheduling flags define B. The first five are changed from v1;
the last two make v1's effective prefill settings explicit:

```text
--max-running-requests 16
--max-mamba-cache-size 64
--max-total-tokens 33024
--mem-fraction-static 0.95
--cuda-graph-max-bs-decode 16
--chunked-prefill-size 2048
--max-prefill-tokens 16384
```

`33024` covers the largest `32768 + 32 = 32800` prefill case with headroom;
64 Mamba slots covers four slots/request at active C16. The explicit request
and Mamba caps are both required, because admission uses observed server
capacity, not the client argument. Decode graphs are capped at 16; prefill
chunking remains at the v1 effective 2048 and is made explicit below. The
temporary memory fraction is a capacity setting and is subject to the VRAM
hard gate below.

Exact B command (executor runs it from `/data/sglang-qwen35`):

```bash
env PATH=/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' PYTHONUNBUFFERED=1 \
  /data/sglang-qwen35-env/bin/sglang serve \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 8036 --tp-size 1 --pp-size 1 --trust-remote-code \
  --reasoning-parser auto --tool-call-parser qwen3_coder \
  --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs '{"preserve_thinking": false}' --log-level info \
  --chunked-prefill-size 2048 --max-prefill-tokens 16384 \
  --max-running-requests 16 --max-mamba-cache-size 64 \
  --max-total-tokens 33024 --mem-fraction-static 0.95 \
  --cuda-graph-max-bs-decode 16
```

Do not pass `--tokenizer` to the server. The benchmark client below uses the
explicit tokenizer sidecar. Do not add graph, attention, dtype, parser, model,
or quality flags. B startup stdout/stderr goes to a fresh run-local log.

## 3. Transition, PID ownership, and admission

Use a fresh remote root:

```text
/data/qwen3-g3-baseline/e3-profile-b/<RUN_ID>/
```

Before any signal, capture `pre-transition/`: UTC time; `ps -eo
pid,ppid,stat,etimes,args --forest`; `pstree -ap 298123`; raw and normalized
`/proc/298123/cmdline`; direct and normalized SHA-256; cwd; `/health`,
`/v1/loads?include=all`, `/v1/models`, `/server_info`; model stat/md5; runner
and source hashes; `ss -ltnp`; and GPU compute/query snapshots. Require v1 PID
alive, health 200, all loads zero, no benchmark/serving client, no stale dmon,
GPU idle except v1, and no 8036 listener. The accepted A evidence gives
direct cmdline hash `750ac48907968dacfd3175b1547a1cd8b9b89cc3eeaa5ebfd625ce221717d200`
and normalized hash
`7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`.

Stop only the freshly re-verified numeric v1 PID (expected 298123): TERM,
wait, re-read its exact cmdline/tree, then KILL only that same verified PID if
still alive. Enumerate any surviving scheduler/detokenizer/resource-tracker
children from that captured tree and handle only explicit numeric PIDs after
identity checks. Never use name/pattern matching. Require no 8035 listener,
zero GPU compute apps, and no v1 descendants before B launch.

The executor's stop/health primitives are explicit and PID-scoped:

```bash
A_PID=298123
test "$(tr '\0' ' ' </proc/$A_PID/cmdline)" = "$V1_ARGV" || exit 74
kill -TERM "$A_PID"
for _ in $(seq 1 120); do kill -0 "$A_PID" 2>/dev/null || break; sleep 1; done
if kill -0 "$A_PID" 2>/dev/null; then
  test "$(tr '\0' ' ' </proc/$A_PID/cmdline)" = "$V1_ARGV" || exit 74
  kill -KILL "$A_PID"
fi
ss -ltnp 'sport = :8035'
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
curl --fail --max-time 5 http://127.0.0.1:8036/health
curl --fail --max-time 5 'http://127.0.0.1:8036/v1/loads?include=all'
```

Launch with the exact §2 command wrapped only for log/PID capture (the command
itself is not shortened or edited):

```bash
cd /data/sglang-qwen35
nohup env ... /data/sglang-qwen35-env/bin/sglang serve <exact §2 argv> \
  >"$RUN/launch/profile-b.log" 2>&1 &
B_PID=$!
printf '%s\n' "$B_PID" >"$RUN/launch/profile-b.pid"
```

The executor must expand `env ... <exact §2 argv>` literally from the recorded
command, not use an alias or a broad process matcher. Save `ps`, `pstree`, and
`/proc/$B_PID/cmdline` after startup.

Launch B with `nohup`, save `$!` in `launch/profile-b.pid`, the literal argv in
`launch/profile-b.command`, stdout/stderr in `launch/profile-b.log`, and all
children in `launch/profile-b.tree`. Poll only that PID and 8036; startup
timeout is 600 seconds. No generation/smoke request is allowed for admission.

Admission is PASS only when all are evidenced in `launch/`:

- B parent/tree is alive and matches the exact command; 8036 health is 200 and
  8035 is not listening.
- `/v1/loads?include=all` reports one scheduler with effective
  `max_running_requests >= 16` (target 16), `max_total_num_tokens >= 33024`
  (target 33024), and startup log/config proves effective Mamba cache >=64.
- Startup log proves the frozen model, parser/tool parser, KV dtype, Mamba
  strategy, template, and no model/download change.
- `nvidia-smi --query-compute-apps=pid,used_memory` shows exactly one compute
  owner attributable to B, with at least 256 MiB free VRAM. Any OOM/CUDA
  allocation failure or unidentified owner fails closed.
- No benchmark runner, wrapper, dmon/query sampler, or unrelated GPU process
  exists. `/metrics` and usable `pmon` are unavailable and are recorded as
  limitations, not fabricated values.

A failed gate writes `launch/HALTED.txt`, preserves startup evidence, sends no
traffic, and immediately follows §8 restoration.

## 4. Locked decode matrix

Use the deployed native runner, explicit sidecar, and offline/no-proxy env:

```text
PY=/data/sglang-qwen35-env/bin/python
MODEL=/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
TOKENIZER=/data/models/Qwen3.8-27B-GSQ-RCO-GGUF
BASE_URL=http://127.0.0.1:8036
```

Exact command shape (only C, N, W, and OUT vary):

```bash
env HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' TOKENIZERS_PARALLELISM=false \
  PYTHONUNBUFFERED=1 "$PY" -m sglang.benchmark.serving \
  --backend sglang --base-url "$BASE_URL" --model "$MODEL" \
  --tokenizer "$TOKENIZER" --dataset-name random-ids \
  --random-input-len 1024 --random-output-len 1024 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 --tokenize-prompt \
  --max-concurrency "$C" --num-prompts "$N" --output-details \
  --output-file "$OUT/result.jsonl" --flush-cache --flush-cache-timeout 60 \
  --warmup-requests "$W"
```

Mapping: C1=`C=1,N=32`; C4=`4,32`; C8=`8,64`; C16=`16,128`. Each has three
measured repeats. Only C1/repeat-1 (the first formal B invocation) has `W=3`;
all later repeats have `W=0`. Flush immediately before every repeat. Capture
before/after loads, server-log byte delta, process state, dmon, and one-second
GPU query. Server logs must show active `#running-req` reaching each C,
especially C16; configured capacity alone is insufficient.

No `--disable-stream`, `--disable-ignore-eos`, ShareGPT, `dataset=random`,
random text, second runner, audit hook, `LD_PRELOAD`, or client GGUF parsing.

## 5. Locked prefill matrix

Keep B admitted and serialize prefill after decode. Use C1/20 prompts,
`--random-output-len 32`, seed 42, ratio 1.0, `--tokenize-prompt`, sidecar,
and the same offline env. Run each independently at input 2048, 8192, and
32768, three repeats each. Every prefill repeat uses `--warmup-requests 0`
(the only B warmup was C1/decode repeat-1) and flushes immediately before
measurement. Output JSONL files and server-log deltas remain independent.

Exact prefill command shape (only `ISL`, `OUT`, and repeat metadata vary):

```bash
env HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' TOKENIZERS_PARALLELISM=false \
  PYTHONUNBUFFERED=1 "$PY" -m sglang.benchmark.serving \
  --backend sglang --base-url "$BASE_URL" --model "$MODEL" \
  --tokenizer "$TOKENIZER" --dataset-name random-ids \
  --random-input-len "$ISL" --random-output-len 32 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 --tokenize-prompt \
  --max-concurrency 1 --num-prompts 20 --output-details \
  --output-file "$OUT/result.jsonl" --flush-cache --flush-cache-timeout 60 \
  --warmup-requests 0
```

## 6. Artifacts, telemetry, scorecard, and capacity gates

Remote layout:

```text
e3-profile-b/<RUN_ID>/{launch,decode/{C1,C4,C8,C16},prefill/{P2K,P8K,P32K},restore}
```

Each repeat retains exact command, UTC start/end, exit code, stdout/stderr,
single-run result JSONL, metadata, before/after loads/health, server-log delta,
process tree/cmdline/hash, one-second `nvidia-smi dmon -s pucvmt`, GPU query
CSV, and hashes. `manifest.json` records host, source/interpreter/runner/model
hashes, exact launch/runner argv, frozen/capacity flags, effective server
capacity, C/N/ISL/OSL/seed, warmup/flush, completion/errors, token totals,
duration, request/input/output/aggregate throughput, median/p99 TTFT/TPOT/E2E,
GPU/KV/Mamba usage, and active-concurrency evidence. `scorecard.json` must
recompute medians from raw JSONL, separately for decode/prefill.

Every manifest includes:

```text
compat_note: requested fixed-length workload; current runner requires random_range_ratio=1.0
dataset_compat_note: random-ids + --tokenize-prompt; raw input_ids, exact length, no ShareGPT dependency
telemetry_notes: /metrics unavailable; pmon attribution unusable; dmon + GPU query + /v1/loads retained
```

Expected elapsed time is about 1.5–3.5 hours (launch/restore 3–5 minutes;
decode 30–75 minutes; prefill 45–120 minutes, P32K dominant). Require 5 GB
free artifact disk before start; expected artifacts are under 2 GB. Hard
gates: effective B capacity >=16/33024/64; observed active C=1/4/8/16;
exact input lengths including P32K; no OOM; three flushed repeats per point;
and complete telemetry/artifacts.

## 7. Rollback and byte-for-byte v1 restoration

On any launch/admission failure, timeout, OOM, benchmark error, or incomplete
artifact, stop only the explicitly verified failed client PID (if any), write
`HALTED.txt`, then stop only the Profile-B parent PID from its PID file after
checking its exact cmdline/tree. TERM, wait, then KILL only the same explicit
PID/tree if needed. Never retry a failed invocation in a loop.

Restore from `/data/sglang-qwen35` with the exact §1 argv, stdout/stderr to
`restore/v1.log`, and the new PID in `restore/v1.pid`:

```bash
cd /data/sglang-qwen35
nohup /data/sglang-qwen35-env/bin/sglang serve \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code \
  --reasoning-parser auto --tool-call-parser qwen3_coder \
  --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs '{"preserve_thinking": false}' --log-level info \
  > /data/qwen3-g3-baseline/e3-profile-b/<RUN_ID>/restore/v1.log 2>&1 &
echo $! > /data/qwen3-g3-baseline/e3-profile-b/<RUN_ID>/restore/v1.pid
```

Restore PASS requires health 200; 8035 owned by the explicit restore PID;
loads idle with effective v1 `max_running_requests=5` and
`max_total_num_tokens=132436`; model md5 equal to
`a37cff66ad81b0e6311d4b6671ac2b09`; source/runner hashes unchanged; frozen
parser/KV/Mamba/template present; no 8036 listener; one identifiable service
GPU owner; and direct/normalized cmdline hashes matching the captured v1 argv
(or a fresh hash pair proven byte-equivalent). Save pre/post snapshots and
`RESTORED.txt` only after all checks. If restore fails, status is blocked:
preserve evidence and do not improvise another launch.

## 8. Execution decision

**GO for the separate execution task**, conditional on rechecking the dynamic
gates (A verification PASS and service idle, 8036 free, exclusive GPU, no old
clients/dmon) and using the existing explicitly scoped process-transition
authorization. **NO-GO for this invocation itself**: this runbook is read-only
and must not stop PID 298123, launch 8036, or send traffic. If 8036 is busy,
startup fails the capacity/VRAM gates, active C16 cannot be observed, or exact
v1 restoration cannot be proven, execution is NO-GO and needs a fresh decision/
Task ID.

Artifacts: this report only.
Evidence: E3 ledger/plan, accepted A verification
`G3-E3-PRODUCTION-A-VERIFY-20260908.md`, native smoke verification, current
read-only host inspection, v1 startup log, and preserved A raw evidence.
Summary: fixed launch/restore contract, capacity flags, explicit PID safety,
health/admission gates, complete decode/prefill matrices, telemetry/artifact
schema, runtime estimate, rollback, and byte-for-byte restoration checks are
specified. Profile-B memory fit remains an empirical hard startup gate on the
single 24-GB GPU; it is not guessed.
Followups: dispatch launch/admit, serialized decode, prefill, restore, then
independent review under their existing Task IDs.
Open issues: port 8036 is not reserved; B fit and active C16 require exclusive
proof; `/metrics` and usable `pmon` remain unavailable; this task does not
authorize execution.

Final status: **done**
