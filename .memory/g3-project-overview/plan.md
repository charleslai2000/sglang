# G3 baseline plan

## Epoch E2 DAG

1. Freeze and validate the user-authorized two-profile protocol contract.
2. Run production-profile A only: unchanged v1 service, C1/C4/C5, 3 repetitions per point.
3. Independently verify A artifacts and confirm the production service remains unchanged.
4. Design and launch the temporary performance-only profile with true active C16 capacity; record exact args and health evidence.
5. Run performance-profile B decode and prefill baselines, 3 repetitions per point.
6. Independently verify B active-batch evidence and artifacts.
7. Only after the baseline is complete, dispatch the MMQ implementation task; then rerun B with identical profile and matrices.
8. Review pre/post gates: C1 no regression, C8/C16 aggregate output TPS, and 8K/32K prefill TTFT/input TPS.

## Completed E1

- Reconnected to the explicit experimental host using the configured key.
- Verified baseline PID/API/GPU state and the unchanged frozen profile.
- Ran and captured the C1 readiness smoke.
- Discovered the old protocol was absent; no matrix was run under invented defaults.

## Current frontier

- `G3-PROTOCOL-FREEZE-20260907`: ready/running.
- `G3-PERF-PROFILE-DESIGN-20260907`: ready/running; read-only capacity and launch-flag design.
- Production A: waiting for protocol-contract verification.
- Performance B: serialized after A because both require the single experimental GPU.

## Current frontier

- C1 smoke: done and verified.
- SSH key setup: done and verified on the authorized experimental host only.
- Formal C1/C4/C8/C16 matrix: blocked pending an authoritative protocol decision or artifact containing the exact command, fixed lengths, seed, warmup/flush behavior, prompt count, output schema, and concurrency mapping.

## E2 verification update

- Protocol freeze and performance-profile design are complete as read-only reports.
- Benchmark execution remains gated by the runner's fixed-length incompatibility (`random_range_ratio=0` is not fixed-length here), the exact prefill prompt-count binding, the existing dataset/hash binding, and an authorized exclusive transition from the unchanged v1 service to a temporary true-C16 profile.
- The scorecard extension is being reviewed as a layered diagnostic contract: core A/B remains the causal MMQ gate; extended concurrency, long-context, and graph comparisons must be labeled baseline-only unless repeated with byte-identical pre/post profiles.
- Scorecard review is complete: throughput/latency/concurrency/GPU/VRAM/failure fields are adopted; HiCache fields are `N/A` because HiCache is disabled. C2/C6, 64K/128K, and Graph OFF are separate strata.
- Remote bindings discovery is complete: no immutable ShareGPT source is staged, candidate B port 8036 was only point-in-time free, `/v1/loads?include=all` plus 1-second `nvidia-smi dmon` are available, `/metrics` is absent, and the live v1 service remains unchanged.
- Execution gate: do not start A or B until the fixed-length interpretation, dataset staging/hash, B-prefill prompt count, warmup semantics, and temporary-profile authorization are explicitly frozen.
- D1-D3 are now frozen by the user: synthetic `ratio=1.0` with compatibility note; ShareGPT is a separate pinned realistic layer; B-prefill is C1/20 prompts/2K, 8K, 32K × 32 output × 3, with RadixCache flush before every measured repeat; B admission requires observed `max_running_requests >= 16`.
- Frontier recomputed: production A is ready and dispatched; B temporary launch is serialized after A on the single GPU; ShareGPT realistic validation is independent and must not block synthetic core.
- Handoff recomputation: prior A execution is blocked and its runner processes are stopped; runner-fix settlement is now the sole frontier task. Fresh A may start only after dual-side fix verification and a new run ID using D4 `random-ids --tokenize-prompt`; Profile B remains serialized after a verified A baseline.
- D5 settlement is verified and the frontier is now fresh Production-A retry. The retry must use a new RUN_ID, D4 synthetic random-ids input IDs, no implicit ShareGPT, and the settled dual-side runner. Profile B remains serialized until A artifacts are independently verified.

## Epoch E3 — G3 core unblock DAG (Task ID `G3-CORE-UNBLOCK-20260907`)

### Scope and invariants

This E3 plan appends to the E2 history; it does not invalidate the prior blocked A
evidence. The sole execution host is `root@175.155.64.171:22109`. No traffic may be
sent to `22151`, `24052`, VM 901, or unrelated work. The v1 service at
`127.0.0.1:8035`, PID `298123`, remains untouched until A is independently accepted.

Every synthetic node uses the deployed interpreter
`/data/sglang-qwen35-env/bin/python`, deployed source `/data/sglang-qwen35/python`,
native `--backend sglang`, `--dataset-name random-ids`, `--tokenize-prompt`,
`--random-range-ratio 1.0`, seed `42`, streaming and ignore-EOS enabled by omission
of the negative flags, and no ShareGPT, random text, or client-side GGUF loading.
The settled GGUF-safe runner patch is a prerequisite and must be verified, not
reimplemented by an executor. Every manifest carries both:

```text
compat_note: requested fixed-length workload; current runner requires random_range_ratio=1.0
dataset_compat_note: random-ids + --tokenize-prompt; raw input_ids, exact length, no ShareGPT dependency
```

All measured points have three measured repetitions and a RadixCache flush
immediately before each measured repeat. Exactly three kernel-warmup requests are
allowed only for the initial run of each service/profile; later repeats use
`--warmup-requests 0`. The one-request admission smoke uses `--warmup-requests 0`.
HiCache fields are `N/A` because HiCache is disabled.
Raw runner output, raw JSONL, command/manifest, server-load snapshots, one-second
`nvidia-smi dmon -s pucvmt` and query samples, process/service evidence, and hashes
are mandatory; unavailable metrics remain `N/A` rather than fabricated.

### Executable DAG and frontier

| Node / Task ID | Owner | Dependencies | Authorized write/process scope | Acceptance and evidence | State |
|---|---|---|---|---|---|
| `G3-E3-AUDIT-20260907` | `scout` | E2 reports and this plan | Read-only audit of local `.memory` and remote `/data/qwen3-g3-baseline`; no benchmark traffic; report only `work/G3-E3-AUDIT-20260907.md` | Inventory any pre-existing random-ids clients, dmon processes, RUN_IDs, and artifact roots; prove no evidence will be duplicated, overwritten, or combined; record service PID/cmdline/hash and GPU/process baseline. Newly confirmed: old E2 wrapper PID `368185` is still active (`C1` complete, `C4/repeat-1` active) | done/verified |
| `G3-E3-SMOKE-EXEC-20260907` | `devops-executor` | audit done; PID 368185 exited; service/GPU idle; runner-settle report `done` | Only experimental host; one native `sglang` request against loopback 8035; remote artifacts under `/data/qwen3-g3-baseline/e3-smoke/<RUN_ID>/`; report `work/G3-E3-SMOKE-EXEC-20260907.md`; no product edits/restart | Exact one-request smoke at ISL 2048/OSL 512 (the frozen A lengths), `random-ids`, `--tokenize-prompt`, ratio 1.0, seed 42, `--warmup-requests 0`. Capture exact runner version/argv, client RSS timeline, open/network evidence, server observed input length, completion/status, raw result and telemetry. Abort on any invariant failure. Do not start while PID 368185 or any benchmark/dmon child remains active | waiting on E2 wrapper drain |
| `G3-E3-SMOKE-VERIFY-20260907` | `tester` | smoke execution done | Read-only local/remote artifact verification; report only `work/G3-E3-SMOKE-VERIFY-20260907.md` | Gate PASS only if: benchmark client did not load/parse GGUF; RSS was small/stable; no network/dataset download; server saw exact input length; one request completed successfully; service PID/cmdline/health remained invariant. Any unproven gate blocks A | blocked on smoke |
| `G3-E3-PROD-A-EXEC-20260907` | `devops-executor` | smoke verification PASS | Baseline service only, PID 298123 at 8035; remote root `/data/qwen3-g3-baseline/e3-prod-a/<RUN_ID>/`; report `work/G3-E3-PROD-A-EXEC-20260907.md`; no restart or product edits | Nine exact invocations C1/C4/C5 × repeats 1–3, prompts 20/40/50, ISL 2048/OSL 512; exactly 3 kernel warmups only on the initial A-profile run, then `--warmup-requests 0` on later repeats; `--flush-cache` immediately before every measured repeat; exact command/version/hash and full raw scorecard. Any OOM, invariant, timeout, zero-progress, or incomplete artifact produces HALTED evidence and blocks acceptance | blocked on smoke |
| `G3-E3-PROD-A-VERIFY-20260907` | `reviewer` | A execution done | Read-only review of A remote root and local report; report only `work/G3-E3-PROD-A-VERIFY-20260907.md` | Independently verify all nine commands are exact, every repeat has flush/raw JSONL/telemetry/manifest, server stayed unchanged, observed concurrency matches C, completion/error counts and medians recompute from raw files, and no prior RUN_ID evidence was mixed. PASS admits B | blocked on A |
| `G3-E3-PROFILE-B-RUNBOOK-20260907` | `devops` | A verification PASS | Read-only remote capacity/launch discovery; report only `work/G3-E3-PROFILE-B-RUNBOOK-20260907.md`; no process transition | Freeze exact temporary launch/transition/restore contract, selected free port, model/quantization and frozen parser/KV/Mamba args, memory fraction, Mamba slots, token capacity, PID/process ownership, health checks, and rollback. Must target observed `max_running_requests >= 16`; no B execution admission without this report | blocked on A; open decision |
| `G3-E3-PROFILE-B-LAUNCH-ADMIT-20260907` | `devops-executor` | B runbook PASS; A verification PASS | Exclusive experimental GPU transition only; remote artifacts under `/data/qwen3-g3-baseline/e3-profile-b/<RUN_ID>/`; may stop only explicitly verified baseline PID/process tree and launch the approved temporary B service; report `work/G3-E3-PROFILE-B-LAUNCH-ADMIT-20260907.md` | Capture pre-transition A state; stop/restart only as specified; prove exactly one service/GPU owner, health 200, frozen quality flags/weights, no competing clients, and observed `max_running_requests >= 16` via server evidence. On failure, no measurements and restore A | blocked on B runbook |
| `G3-E3-PROFILE-B-DECODE-20260907` | `devops-executor` | B admission PASS | Same exclusive temporary B service; write only `e3-profile-b/<RUN_ID>/decode/` and report `work/G3-E3-PROFILE-B-DECODE-20260907.md`; no concurrent B/prefill traffic | Decode matrix C1/C4/C8/C16, E2 frozen B lengths ISL 1024/OSL 1024 and prompts 32/32/64/128, seed 42, ratio 1.0, three repeats, exactly 3 kernel warmups only on the initial B-profile run, then `--warmup-requests 0` on later repeats, and flush before every repeat; raw artifacts and actual server-side concurrency/throughput evidence | blocked on admission |
| `G3-E3-PROFILE-B-PREFILL-20260907` | `devops-executor` | B decode done; B service remains admitted | Same exclusive B service; write only `e3-profile-b/<RUN_ID>/prefill/` and report `work/G3-E3-PROFILE-B-PREFILL-20260907.md`; no concurrent traffic | C1/20 prompts at ISL 2048, 8192, 32768 with OSL 32, seed 42, ratio 1.0, three repeats per length, `--warmup-requests 0` because B-profile warmup was already consumed, flush before every repeat; exact input lengths via raw IDs; retain all raw scorecard/telemetry | blocked on decode |
| `G3-E3-PROFILE-B-RESTORE-20260907` | `devops-executor` | B decode and prefill done, or abort path | Exclusive experimental host; process transition and restore evidence under `e3-profile-b/<RUN_ID>/restore/`; report `work/G3-E3-PROFILE-B-RESTORE-20260907.md`; no other host | Stop only identified temporary B PID/tree; restore the exact v1 launch profile on 8035 (or the approved documented rollback), verify health, parser/tool parser/KV/Mamba/default-template flags, model hash, capacity, and idle GPU; retain failure/rollback evidence | blocked on B workloads |
| `G3-E3-PROFILE-B-VERIFY-20260907` | `reviewer` | B restore done | Read-only review of decode/prefill/restore artifacts; report only `work/G3-E3-PROFILE-B-VERIFY-20260907.md` | Recompute all medians from raw JSONL; verify true observed C16 admission and no contention, exact commands/repetitions/flushes, telemetry completeness, unchanged weights/profile semantics, and successful v1 restoration. PASS closes E3 baseline collection | blocked on restore |
| `G3-E3-SYNTHESIS-20260907` | `orchestrator` | smoke/A/B verification PASS or explicitly recorded blocked evidence | Control-plane synthesis only; no product/remote writes; final packet/report path chosen by orchestrator | Record PASS/blocked per gate, preserve all raw roots/hashes, and keep MMQ implementation/rerun out of this DAG until a fresh implementation Task ID | blocked on verifications |

Dependencies are strict: `AUDIT → (E2 wrapper 368185 drains and service/GPU idle) → SMOKE-EXEC → SMOKE-VERIFY → PROD-A-EXEC →
PROD-A-VERIFY → B-RUNBOOK → B-LAUNCH-ADMIT → B-DECODE → B-PREFILL → B-RESTORE →
B-VERIFY → SYNTHESIS`. Decode and prefill are intentionally serialized even though
their write sets are disjoint: they share one temporary GPU/service and cache state.
A and B are never concurrent; B is never launched before A's independent acceptance.

The old E2 wrapper PID `368185` is a hard serialization barrier: remote audit found
its C1 complete and C4/repeat-1 still active. Its artifacts remain excluded from
E3 and from all scorecards unless a separate independent admission explicitly
accepts them; no E3 node may overwrite, merge, or treat them as fresh evidence.

### Profile-B open decisions and admission contract

The existing E2 capacity note is not an executable launch contract. `G3-E3-PROFILE-B-
RUNBOOK-20260907` must resolve, with evidence, the following before any transition:

1. a currently free loopback port (8036 is only a historical point-in-time candidate),
   the exact launch argv, and the exact v1 rollback argv;
2. how the temporary service obtains observed `max_running_requests >= 16` (including
   Mamba slot/cache sizing and `max_total_num_tokens` sufficient for the 32K prefill);
3. safe GPU memory fraction and expected VRAM headroom on the single RTX 3090, with
   the baseline service fully quiesced before launch;
4. explicit PID/process-tree checks and the only permitted stop/start targets, plus
   restoration if admission or a matrix fails; and
5. whether the deployed source already exposes the needed capacity flags without a
   product/MMQ edit. If not, the node is blocked and must request a fresh Task ID;
   it must not invent a flag, edit product code, or lower the admission threshold.

Known accepted telemetry gaps remain `/metrics` unavailable and `nvidia-smi pmon`
process attribution unusable; dmon, one-second query samples, `/v1/loads?include=all`,
and before/after queries are required substitutes. These gaps do not waive the
server-side observed-concurrency admission gate.

### Child dispatch requirements

Each dispatch must carry its own Task ID, epoch `E3`, one role, exact node goal,
authorized read/write/process scope, listed dependencies, report path above,
acceptance/evidence requirements, and the statement: “Extra work requires a fresh
Task ID.” A child returns only `done`, `blocked`, or `pending`; it does not spawn
children or edit this plan, ledger, context, product files, or another report.
