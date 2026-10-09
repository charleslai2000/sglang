# G3 Profile C sweet-spot execution DAG

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-PLAN-20260908
epoch: E4
role: task-manager

## Goal and execution verdict

This is an execution plan, not an execution record. It converts the authorized
Profile-C decision into a serialized, fail-closed DAG for the single RTX 3090.
No remote command, benchmark request, service transition, download, or product
write was performed while producing this report.

**GO for execution**, conditional on the gates and open decisions below. The
plan stops at the first failed candidate. C4 is not admitted by default: it
requires a fresh explicit go/no-go decision after C3 is independently accepted
as healthy and the higher capacity is still needed.

The prior Profile-B over-capacity startup failure is evidence for a hard
pre-traffic startup gate, not permission to change quality, graph, prefill, or
allocator flags. The accepted user decision is to keep frozen Profile-B startup
over-capacity closed and test this independent Profile-C line.

## Fixed authorization and assumptions

### User-fixed (not reopenable in this DAG)

- Experimental host only: `175.155.64.171:22109`; one RTX 3090; SGLang only.
- Frozen v1 quality profile, model weights, sampling, prompt/history policy,
  verifier semantics, KV dtype, Mamba strategy, parser selection, and workload
  scope remain unchanged.
- Frozen flags remain:
  `--reasoning-parser auto`, `--tool-call-parser qwen3_coder`,
  `--kv-cache-dtype fp8_e4m3`,
  `--mamba-radix-cache-strategy extra_buffer_lazy`, and
  `--default-chat-template-kwargs '{"preserve_thinking": false}'`.
- Do not rerun Profile-B pool64/C16. Do not carry over 9B pool64 assumptions.
- Candidate envelopes:

  | Candidate | `max_running_requests` | Mamba pool envelope | decode graph envelope |
  |---|---:|---:|---:|
  | C1 | 4 | 20–24 | `<=4` |
  | C2 | 6 | 30–32 | `<=6/8` |
  | C3 | 8 | 40/44 | `<=8` |
  | C4 (optional) | 10 | 48/52 | `<=8/10` |

- Each admitted candidate is exclusive on the GPU, measured with actual active
  concurrency, and restored to frozen v1 before any next candidate or after any
  failure.
- Required measurements are fixed 256-token generation runs with aggregate
  output TPS, per-request TPS, TTFT, and TPOT; default repeats are 3.
- Input generation uses native SGLang `random-ids` plus `--tokenize-prompt`.
  No `dataset=random`, ShareGPT, network/download, random text, or client-side
  GGUF loading is allowed.
- All raw JSONL, telemetry, logs, exact commands, manifests, and hashes are
  retained beneath `/data/qwen3-g3-baseline/e3-profile-c/<RUN_ID>/`.

### Explicit planning assumptions (must be recorded in every manifest)

- The user's “prior B decode” binds `ISL=1024`, `seed=42`, and
  `--random-range-ratio 1.0`; no contrary new ISL binding was supplied. Use
  `ISL=1024`, `OSL=256`, `ratio=1.0`, and `seed=42`, recording:
  `isl_assumption: reused prior B decode ISL=1024; no new user binding`.
- To make the candidate requests long enough to expose actual active capacity,
  use `num-prompts = 8 * candidate max_running`: C1=32, C2=48, C3=64,
  C4=80. This is a planning default and must not be silently changed.
- To make each bounded envelope executable and comparable, use the lowest
  permitted pool/graph tuple first: C1=(20,4), C2=(30,6), C3=(40,8), and
  C4=(48,8). The selected exact tuple is a planning default, not a claim that
  the upper envelope fits. A runbook owner may propose a second value inside a
  candidate envelope only through a fresh Task ID/decision; it must never be
  smuggled into a repeat or treated as the same candidate.
- The three formal repeats use the same command shape and input parameters.
  `--warmup-requests 3` is allowed only on C1/repeat-1, the first formal
  Profile-C invocation. All later repeats and candidates use `0`. Each measured
  repeat performs cache flush immediately before measurement, including after
  the one-time warmup.
- The settled GGUF-safe runner is an input prerequisite. Passing a GGUF path as
  the runner's model identity is allowed only if evidence proves the client did
  not parse/load GGUF (patched `check_chat_template`, sidecar tokenizer, bounded
  RSS, and no network). This is not client-side GGUF loading.

### Flags permitted to differ from v1

Only these capacity knobs may differ per candidate:

```text
--max-running-requests <4|6|8|10>
--max-mamba-cache-size <20|30|40|48>   # selected conservative tuple
--cuda-graph-max-bs-decode <4|6|8|8>  # selected conservative tuple
```

No `--max-total-tokens`, memory fraction, prefill graph, chunking, attention,
dtype, parser, tokenizer, model, or quality flag may be added or changed by a
candidate task. The effective `max_total_num_tokens` must be observed and
recorded, not tuned in this DAG. If a candidate cannot start without an
additional flag, stop and request a fresh decision/Task ID.

## DAG and ownership

All nodes below have disjoint write sets. They share one serialized process/GPU
resource, so the apparent write independence of reports does not permit
parallel execution. Every child dispatch must include the node ID, epoch E4,
role, exact scope, dependencies, acceptance/evidence requirements, report path,
and: **“Extra work requires a fresh Task ID.”** No node may spawn children or
edit this plan, the ledger, context, product files, or another node's report.

| Node / Task ID | Owner | Dependencies | Authorized write/process scope | Acceptance and required evidence | State |
|---|---|---|---|---|---|
| `G3-PROFILE-C-PREFLIGHT-20260908` | `devops` | This plan; current v1 restoration report | Read-only local/remote preflight; report only `work/G3-PROFILE-C-PREFLIGHT-20260908.md` | Verify v1 is healthy/idle, exact frozen cmdline and hashes, model/source/runner identity, no benchmark/dmon/query client, no unknown GPU owner, candidate port free, artifact disk >=5 GB, and that the settled runner/sidecar are present. Select one free loopback port and record it. Any stale/unattributable GPU owner or missing runner fix blocks all launch nodes. | ready |
| `G3-PROFILE-C-C1-LAUNCH-20260908` | `devops-executor` | Preflight PASS; v1 idle | Exclusive transition only; remote `e3-profile-c/<RUN_ID>/c1/launch/`; report `work/G3-PROFILE-C-C1-LAUNCH-20260908.md` | Capture v1 pre-transition state; stop only the reverified numeric v1 PID/tree; launch exact C1 tuple; prove one owner, health/admission, effective capacities, complete weight/Mamba/KV/graph/free-VRAM allocations, CUDA graph capture completion, no OOM before traffic, frozen flags/weights, and no competing process. On any failure write `HALTED.txt` and send no traffic. | blocked on preflight |
| `G3-PROFILE-C-C1-DECODE-20260908` | `devops-executor` | C1 launch/admission PASS | Exclusive C1 service; write only `c1/measure/` plus report `work/G3-PROFILE-C-C1-DECODE-20260908.md` | Run C1, C=4/N=32, ISL=1024/OSL=256, 3 repeats, one-time W=3 then W=0, cache flush before every measured repeat. Capture raw JSONL, actual active concurrency, aggregate/per-request TPS, TTFT/TPOT, loads/logs, dmon/query, process and error evidence. Any OOM, short input/output, active-C mismatch, timeout, incomplete raw artifact, or invariant failure halts the line. | blocked on C1 admission |
| `G3-PROFILE-C-C1-RESTORE-20260908` | `devops-executor` | C1 launch outcome; decode outcome if admitted | Exclusive transition/rollback; write only `c1/restore/` plus report `work/G3-PROFILE-C-C1-RESTORE-20260908.md` | Always runs after launch admission succeeds or fails. Stop only the identified C1 PID/tree; restore exact v1 argv on the same authorized host/port contract; verify health, idle loads, frozen flags, model hash, one attributable GPU owner, and no C1/client descendants. Restoration PASS is a hard dependency for any next candidate. | blocked on C1 outcome |
| `G3-PROFILE-C-C1-VERIFY-20260908` | `tester` | C1 restore PASS | Read-only remote/local evidence; report only `work/G3-PROFILE-C-C1-VERIFY-20260908.md` | Independently recompute C1 metrics from raw JSONL, verify all 3 repeats/flushes/warmup semantics, actual active C=4, allocation/admission evidence, no mixed run IDs, and v1 restore. PASS permits C2 only if no failed-gate stop applies. | blocked on C1 restore |
| `G3-PROFILE-C-C2-LAUNCH-20260908` | `devops-executor` | C1 verify PASS; no stop condition; v1 restored/idle | Same as C1, under fresh `c2/launch/`; report `work/G3-PROFILE-C-C2-LAUNCH-20260908.md` | Launch exact C2 tuple (6,30,6); repeat all admission/allocation/graph/free-VRAM gates before traffic. No inherited C1 evidence. | blocked on C1 verify |
| `G3-PROFILE-C-C2-DECODE-20260908` | `devops-executor` | C2 launch/admission PASS | Write only `c2/measure/`; report `work/G3-PROFILE-C-C2-DECODE-20260908.md` | C2 C=6/N=48, same ISL/OSL/seed/ratio, W=0 for all 3 repeats, flush before each; capture and validate the same metrics/evidence. | blocked on C2 admission |
| `G3-PROFILE-C-C2-RESTORE-20260908` | `devops-executor` | C2 launch outcome; decode outcome if admitted | Write only `c2/restore/`; report `work/G3-PROFILE-C-C2-RESTORE-20260908.md` | Unconditional v1 restoration and identity/health/idle verification. | blocked on C2 outcome |
| `G3-PROFILE-C-C2-VERIFY-20260908` | `tester` | C2 restore PASS | Read-only; report `work/G3-PROFILE-C-C2-VERIFY-20260908.md` | Independent metric/artifact/gate verification; PASS permits C3. | blocked on C2 restore |
| `G3-PROFILE-C-C3-LAUNCH-20260908` | `devops-executor` | C2 verify PASS; no stop condition; v1 restored/idle | Write only `c3/launch/`; report `work/G3-PROFILE-C-C3-LAUNCH-20260908.md` | Launch exact C3 tuple (8,40,8); same startup allocation, graph, capacity, free-VRAM, frozen-profile, and no-traffic gates. | blocked on C2 verify |
| `G3-PROFILE-C-C3-DECODE-20260908` | `devops-executor` | C3 admission PASS | Write only `c3/measure/`; report `work/G3-PROFILE-C-C3-DECODE-20260908.md` | C3 C=8/N=64, same workload and telemetry contract, W=0, 3 flushed repeats, actual active C=8 required. | blocked on C3 admission |
| `G3-PROFILE-C-C3-RESTORE-20260908` | `devops-executor` | C3 launch outcome; decode outcome if admitted | Write only `c3/restore/`; report `work/G3-PROFILE-C-C3-RESTORE-20260908.md` | Unconditional v1 restoration and verification. C3 restore is required even if C4 is never admitted. | blocked on C3 outcome |
| `G3-PROFILE-C-C3-VERIFY-20260908` | `tester` | C3 restore PASS | Read-only; report `work/G3-PROFILE-C-C3-VERIFY-20260908.md` | Independently verify C3 and declare healthy/failed. A healthy result is necessary but not sufficient for C4. | blocked on C3 restore |
| `G3-PROFILE-C-C4-DECISION-20260908` | `orchestrator` | C3 verify PASS; fresh user decision | Control-plane decision only; report `work/G3-PROFILE-C-C4-DECISION-20260908.md` | Record explicit GO/NO-GO, rationale that C3 is healthy and C4 is needed, exact C4 tuple/port/RUN_ID. NO-GO ends execution after v1 restore. No implicit continuation. | blocked on C3 verify |
| `G3-PROFILE-C-C4-LAUNCH-20260908` | `devops-executor` | C4 decision GO; v1 restored/idle; preflight recheck PASS | Write only `c4/launch/`; report `work/G3-PROFILE-C-C4-LAUNCH-20260908.md` | Launch exact C4 tuple (10,48,8) by default; if a fresh decision selects 52/10, it must be recorded before launch. Same fail-closed admission/allocation/graph gates. | blocked on decision |
| `G3-PROFILE-C-C4-DECODE-20260908` | `devops-executor` | C4 admission PASS | Write only `c4/measure/`; report `work/G3-PROFILE-C-C4-DECODE-20260908.md` | C4 C=10/N=80, same workload/telemetry contract, 3 flushed repeats, W=0, actual active C=10 required. | blocked on C4 admission |
| `G3-PROFILE-C-C4-RESTORE-20260908` | `devops-executor` | C4 launch outcome; decode outcome if admitted | Write only `c4/restore/`; report `work/G3-PROFILE-C-C4-RESTORE-20260908.md` | Unconditional v1 restoration and verification; this is the terminal hard safety gate. | blocked on C4 outcome |
| `G3-PROFILE-C-C4-VERIFY-20260908` | `tester` | C4 restore PASS | Read-only; report `work/G3-PROFILE-C-C4-VERIFY-20260908.md` | Independent C4 verification, or explicit failed/blocked conclusion with preserved evidence. | blocked on C4 restore |
| `G3-PROFILE-C-SCORECARD-20260908` | `external-analyst` | All executed candidate verifications; terminal v1 restore PASS | Read-only synthesis; report `work/G3-PROFILE-C-SCORECARD-20260908.md` | Compare only independently valid candidates; identify sweet spot using throughput/latency/active-C/VRAM/failure evidence; keep failed/unrun candidates distinct; do not infer BF16 quality or merge official SWE and internal clean-pass denominators. | blocked on executed frontier |

### Serialization and stop rules

The profiles cannot run in parallel even though each candidate has a separate
artifact subtree: they share the single GPU, model weights, CUDA allocator,
server port, and v1 restoration state. Launch, traffic, and restore are also
serialized within each profile because CUDA graph capture and cache flushing
change shared service state. This is the explicit `serialization_reason`, not
an implementation convenience.

The first failed candidate means no later candidate runs. “Failed” includes
launch OOM, graph-capture failure, unknown GPU owner, insufficient free VRAM,
effective capacity below the tuple, frozen-flag/weight mismatch, health failure,
active concurrency below target, any request/error/invariant failure, or
incomplete artifacts. The launch owner must halt before traffic when possible,
write evidence, and invoke the restore node. A later candidate can run only
after all prior candidates are independently accepted and v1 is restored. C4
also requires the separate decision node.

## Launch/admission gate

Each candidate gets a fresh `RUN_ID` and remote root:

```text
/data/qwen3-g3-baseline/e3-profile-c/<RUN_ID>/
  preflight/ launch/measure/{C1|C2|C3|C4}/ restore/ manifests/ hashes/
```

The exact candidate server command is the frozen v1 command plus only the three
candidate capacity flags in the tuple. The launch manifest must retain the
literal argv, environment, PID/tree, port, source/interpreter/runner/model
hashes, and v1 pre-transition snapshot. It must not use a second server or
change the production host/ports outside the selected experimental loopback
port.

Before sending any request, admission requires all of the following in raw
startup evidence:

1. The candidate parent/tree and listener match the literal argv; health is
   HTTP 200; v1 is not still listening; no benchmark, dmon, query sampler, or
   unrelated GPU process exists.
2. `/v1/loads?include=all` and startup logs expose effective
   `max_running_requests` equal to the candidate target and record effective
   `max_total_num_tokens`. The latter may remain the v1 default because it is
   not a permitted tuning knob; it must be observed, not assumed.
3. Startup logs/config show model/weights, parser/tool parser, KV dtype, Mamba
   strategy, template, Mamba allocation/pool, KV allocation, CUDA graph
   allocation/capture, and free VRAM. Any missing component is NOT ADMITTED.
4. CUDA graph capture completes without OOM before traffic. A startup failure
   like the prior Profile-B prefill graph OOM is a hard HALT; do not reduce
   quality or add prefill/allocator flags to rescue it.
5. `nvidia-smi` query/compute-app evidence attributes one candidate owner and
   shows documented free headroom. The plan does not set a numeric headroom
   threshold in advance; the launch owner must propose the measured threshold
   in its fresh preflight and fail closed if allocation leaves no meaningful
   headroom or an unknown owner appears.

No smoke request is permitted before these gates. Admission evidence and
measurement evidence must be separate files; a configured capacity is not proof
of actual active concurrency.

## Measurement command and artifact contract

Use the deployed interpreter and settled GGUF-safe runner with offline/no-proxy
environment. The command shape is fixed; only `C`, `N`, `W`, output path, and
base URL/manifest metadata vary:

```bash
env HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' \
  TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1 \
  /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:<PORT> \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF \
  --dataset-name random-ids --tokenize-prompt \
  --random-input-len 1024 --random-output-len 256 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency <C> --num-prompts <N> --output-details \
  --output-file <RUN>/measure/<candidate>/repeat-<r>/result.jsonl \
  --flush-cache --flush-cache-timeout 60 --warmup-requests <W>
```

The explicit `--tokenizer` points to the sidecar directory, never the GGUF.
The runner source/hash and RSS evidence must prove it does not deserialize the
GGUF. Any implicit data fetch, ShareGPT access, client GGUF read, or changed
runner requires a fresh decision/Task ID.

Every repeat retains exact command, UTC start/end, exit code, stdout/stderr,
raw JSONL, metadata, loads/health before and after, server-log byte delta,
process tree/cmdline, one-second `nvidia-smi dmon -s pucvmt`, GPU query CSV,
and SHA-256 files. Each manifest records candidate tuple, C/N/ISL/OSL, seed,
ratio, warmup/flush, completed/errors, requested and observed token totals,
aggregate output TPS, per-request output TPS, TTFT, TPOT, E2E, active-C evidence,
weight/Mamba/KV/graph/free-VRAM fields, and these notes:

```text
compat_note: fixed 256-token generation; random-range-ratio=1.0 required by deployed runner
dataset_compat_note: random-ids + --tokenize-prompt; sidecar tokenizer; no ShareGPT/download/client GGUF load
isl_assumption: reused prior B decode ISL=1024; no new user binding
telemetry_notes: /metrics unavailable; pmon attribution unusable; dmon + GPU query + /v1/loads retained
```

The scorer must compute aggregate output TPS from total generated tokens over
wall time and per-request TPS from each request's output tokens over its own
generation time, retaining the raw definition in `scorecard.json`. TTFT and
TPOT are medians (and p99 when available) over successful requests only, with
failed/error counts shown separately. Actual active concurrency is the maximum
server-side running count observed in loads/server logs during the measured
phase; client `--max-concurrency` alone is not evidence.

## Restoration, hard stops, and rollback

Restoration is mandatory after every candidate, including pre-traffic failure.
The restore owner may stop only the freshly reverified numeric candidate PID and
explicit descendants from its captured process tree. Never use broad name
matching, GPU reset, destructive cleanup, or unrelated-host operations.

Restore acceptance requires the exact frozen v1 launch argv, health 200 on the
authorized v1 port, idle loads, frozen parser/tool/KV/Mamba/template flags,
unchanged model hash, one attributable v1 GPU owner, no candidate/client/dmon
descendants, and preserved candidate failure evidence. If restoration fails,
the DAG is blocked and no candidate or synthesis may claim a clean terminal
state; escalate with the exact restore evidence and a fresh Task ID.

## Expected cost and storage

Estimate per candidate: 3–5 minutes transition/admission and restoration plus
roughly 15–40 minutes for three 256-token repeats, depending on queueing and
actual decode speed. C1–C3 are approximately 1–2.5 hours end-to-end; optional
C4 adds approximately 20–45 minutes. Require at least 5 GB free before the
first transition. Expect less than 1 GB per candidate in ordinary raw JSONL,
logs, and telemetry, but preserve evidence rather than deleting files when a
run is halted.

## Open decisions and followups

1. **Exact port:** `G3-PROFILE-C-PREFLIGHT` must select and record a currently
   free loopback port; no stale historical port is assumed.
2. **Exact tuple policy:** this plan defaults to `(pool, graph)=(20,4),
   (30,6), (40,8), (48,8)`. A second value in any allowed envelope requires a
   fresh Task ID and must not be folded into the three repeats.
3. **C4 admission:** requires a fresh explicit GO after healthy C3 verification
   and a written need for C4. Without it, C4 is NO-GO and the terminal v1
   restore remains sufficient.
4. **Free-VRAM threshold:** launch owner must propose a measured, evidence-based
   minimum in preflight; this plan forbids proceeding with zero/ambiguous
   headroom but does not invent a numeric threshold from prior B evidence.
5. **ISL binding:** current assumption is prior-B ISL=1024. If the user binds a
   different ISL, stop before launch and issue a fresh plan/Task ID.
6. **Runner patch identity:** the deployed GGUF-safe runner/hash must match the
   accepted settled fix. If absent or changed, no execution is authorized by
   this plan.

## Evidence summary and handoff

Observed inputs used for planning were the repository `AGENTS.md`, local G3
context/plan and handoff, the accepted Profile-B runbook, Profile-B launch/OOM
reports, and the v1 restoration report. They establish that v1 restoration is
possible, that B failed before traffic during graph capture, and that admission
must prove allocations and effective capacities from actual process/server
evidence.

No product files, ledger, context, plan, remote artifacts, or service state were
changed. The only artifact produced by this invocation is this report:

`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/G3-PROFILE-C-PLAN-20260908.md`

Followups: dispatch only the ready preflight node, then recompute the frontier
after each outcome; do not dispatch C2/C3/C4 ahead of the dependency chain.

Open issues: the six decisions above remain execution-time inputs. They are
explicitly visible and are not silently resolved by this planning task.
