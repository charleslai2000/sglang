# P0-C 3060 server-profile and capacity-semantics reconnaissance — R59

- ENTRY: ACCEPT
- task_id: `P0-C-PROFILE-RECON-20260911-R59`
- invocation: `ses-p0c-profile-recon-r59-20260911`
- role: `scout`
- epoch: `2026-09-11`
- status: `done`
- scope: read-only local reconnaissance of the launch/profile surfaces, capacity
  and limit definitions, phase2 R32/R34/R52 telemetry, and the capacity-semantics
  design contracts for the authorized RTX 3060 12G experiment. No remote access,
  no experiment, no product/test/gate/storage/Git change, no server start was
  performed by this invocation. Only this report was written.
- gate position: **P0-B remains NOT_VERIFIED; P0-C remains NOT_VERIFIED.** This
  report is reconnaissance for the P0-C gate; it is not P0-C acceptance and it
  does not bypass the P0-B hard gate (`plan.md:20-24,65-67`).
- supersedes: the earlier thin stub at this path (previous content was a 31-line
  summary with no file/line references or procedure). The values it listed as
  unknown are pinned below from durable evidence.

## 1. Bottom line

The exact live RTX-3060 launch invocation and the full derived server/capacity
profile used in the most recent authorized 3060 run are recoverable from the
durable R32 raw bundle. The three production source files in that remote run are
SHA256-identical to the current local worktree (`scheduler.py`,
`unified_radix_cache.py`, `hicache_restore.py`), so the observed profile
corresponds to the current production revision.

However, two facts keep the profile "observed candidate", not "frozen/ratified":

1. There is **no reviewed, pinned 3060 launch script**; the earlier scout already
   recorded the negative finding `no existing 3060-specific server launch script
   that pins the P0-B capacity profile`
   (`work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md:104`). The invocation is an
   ad-hoc shell argv captured while running.
2. The run it came from (R32) was **NOT_VERIFIED** and never demonstrated the
   capacity transition; the same source revision emitted `attempt_id=null`,
   `session_generation=null`, `trace_context=null`, so the live semantics of the
   profile were not exercised (`work/P0-B-LIVENESS-RUN-20260911-R32.md:22-23`,
   `work/R32-artifacts/remote-server-log.txt:78,144`).

Therefore P0-C closure still requires a bounded, evidence-preserving **capture**
(and, only if no captured instance exists at the time, one bounded server start)
that pins the values and hashes below under review. Section 6 gives that
procedure.

## 2. Authorized target identity (already frozen by prior evidence)

| Dimension | Value | Source (path:line) |
|---|---|---|
| SSH endpoint | `root@i-1.gpushare.com:27460` | `work/P0-A-RH-REGRESSION-20260911.md:9-14`; `work/P0-A-RESIDENCY-REVIEW-20260911-R22.md:27` |
| SSH key | `/home/dev-codex/.ssh/sglang_3060_ed25519` | `work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md:73` |
| Remote checkout | `/root/sglang-3060-12g-hicache` (no `.git`; not a Git repo) | `work/P0-A-RH-REGRESSION-20260911.md:9-14,86` |
| Python env | `/root/sglang-env-3060-4b/bin/python`, Python 3.11.11 | `work/P0-A-RH-REGRESSION-20260911.md:9-14`; `work/P0-B-LIVENESS-RUN-20260911-R32.md:10` |
| Deps | pytest 9.1.1, orjson 3.12.0, msgspec 0.21.1, torch 2.6.0+cu124 / CUDA 12.4 | `work/P0-B-LIVENESS-RUN-20260911-R32.md:10-11` |
| GPU | `NVIDIA GeForce RTX 3060`, 12288 MiB, compute capability 8.6, driver 550.144.03 | `work/R32-artifacts/post-test-safety.txt:4`; `work/P0-A-REMOTE-SOURCE-RECONCILE-20260911.md:14` |
| Local branch | `3060-12g-qwen35-4b` | `plan.md:80`; `context.md:11` |
| Local HEAD | `4f41f5bab562b99562f30c67540eb05344d13637` | `plan.md:81`; verified locally this invocation |
| Profile inference gateway | none (`gpushare.com` is the experiment host) | n/a |

## 3. Profile dimensions — frozen-vs-unknown table

Status key:

- **FROZEN** = ratified by prior reviewed/verified evidence.
- **OBSERVED** = exact value captured from the authorized 3060 run's raw artifacts
  but not yet ratified by a P0-C review.
- **UNKNOWN** = not established by any inspected artifact.

| # | Dimension | Observed value (authorized 3060, R32) | Defined at (source) | Evidence (artifact:line) | Status |
|---|---|---|---|---|---|
| 1 | Served model weights | `/hy-tmp/models/Qwen3.5-4B-AWQ` | launch argv | `post-test-safety.txt:6-7`; `runtime-log-inspection.txt:90` | OBSERVED |
| 2 | Model class | `Qwen3_5ForConditionalGeneration` | model config / loader | `remote-server-log.txt:31` | OBSERVED |
| 3 | Weight quantization | `quant=compressed-tensors` (AWQ) | model checkpoint | `remote-server-log.txt:31` | OBSERVED |
| 4 | `--dtype` | `auto` (Marlin ran in bf16 on SM86) | `server_args.py` | `remote-server-log.txt:6,42` | OBSERVED |
| 5 | KV cache dtype | `fp8_e4m3`, scaling factors defaulted to 1.0 | `server_args.py` | `remote-server-log.txt:6,30,34` | OBSERVED |
| 6 | TP size | `1` | `server_args.py:981-988` | `remote-server-log.txt:6` | OBSERVED |
| 7 | PP size | `1` | `server_args.py:997-1004` | `remote-server-log.txt:6` | OBSERVED |
| 8 | `--context-length` | `None` (model config); engine logged `context_len=262144` | `server_args.py:537-545` | `remote-server-log.txt:6,60` | OBSERVED |
| 9 | `--max-total-tokens` (device KV pool tokens) | `65536` | `server_args.py:743-756` | `remote-server-log.txt:6,34,60` | OBSERVED |
| 10 | `--mem-fraction-static` | `0.82` | `server_args.py` | `remote-server-log.txt:6` | OBSERVED |
| 11 | Device KV pool footprint | K `0.50 GB` + V `0.50 GB` (`float8_e4m3fn`) | derived | `remote-server-log.txt:34` | OBSERVED |
| 12 | Device Mamba pool size | `max_mamba_cache_size: 53` (auto) | `server_args.py:2604-2606`; `kv_cache_configurator.py:2075-2163` | `remote-server-log.txt:33` | OBSERVED |
| 13 | Device Mamba footprint | `conv_state 0.06 GB`, `ssm_state 2.53 GB` | derived | `remote-server-log.txt:33` | OBSERVED |
| 14 | Host KV pool capacity | `131073` tokens, `2.15 GB` | `server_args.py:2750-2759`; `kv_cache_builder.py:158-166`; `hybrid_pool_assembler.py:96-124` | `remote-server-log.txt:62` | OBSERVED |
| 15 | Host Mamba pool capacity | `5.51 GB` (layout `page_first`) | derived from `--hicache-ratio` | `remote-server-log.txt:63` | OBSERVED |
| 16 | `--hicache-ratio` | `2.0` | `server_args.py:2750-2754` (default 2.0 cache mode) | `remote-server-log.txt:6` | OBSERVED |
| 17 | `--hicache-size` | `0` (disabled; ratio governs) | `server_args.py:2755-2759` | `remote-server-log.txt:6` | OBSERVED |
| 18 | Page size | `page_size=1`; `c128_page_size=16` | `server_args.py:852-861` (`page_size` default `None`, resolved) | `remote-server-log.txt:6` | OBSERVED |
| 19 | Hierarchical cache | `enable_hierarchical_cache=True`; mode `cache` | `server_args.py` | `remote-server-log.txt:6` | OBSERVED |
| 20 | HiCache IO / layout / write / storage / prefetch policy | `io_backend=kernel`, `mem_layout=page_first`, `write_policy=write_through`, `storage_backend=file`, `storage_prefetch_policy=wait_complete` | `server_args.py:2760-2789` | `remote-server-log.txt:6`; `post-test-safety.txt:6` | OBSERVED |
| 21 | Storage dir + extra config | `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-rh-clean-20260910`; `{"hicache_storage_pass_prefix_keys":true}` | env + argv | `post-test-safety.txt:6`; `remote-server-log.txt:65` | OBSERVED |
| 22 | Physical prefetch budget (`physical_budget_limit_tokens`) | `65536` = `int(0.5 * host pool 131073)` | `cache_controller.py:657-662`; `scheduler.py:4707-4708,4208` | `remote-server-log.txt:106,178,296` | OBSERVED |
| 23 | Speculative prefetch fraction | `0.6` | `server_args.py:2881-2893` | `remote-server-log.txt:6` | OBSERVED |
| 24 | Speculative budget limit | `39321` = `int(0.6 * 65536)` | `cache_controller.py:667-669`; `scheduler.py:4709-4711,4209` | `remote-server-log.txt:106,178,296` | OBSERVED |
| 25 | Ready Horizon enable | `--enable-ready-horizon` = `True` | `server_args.py:2866-2880` | `remote-server-log.txt:6`; `post-test-safety.txt:6` | OBSERVED |
| 26 | RH frontier N | `--ready-horizon-frontier-n 8` | `server_args.py:2894-2904` | `remote-server-log.txt:6` | OBSERVED |
| 27 | RH host watermark (token mode) low/high | `55000` / `110000` | `server_args.py:2905-2940` | `remote-server-log.txt:6,69` | OBSERVED |
| 28 | RH count-mode watermarks | `None` / `None` (token mode active) | `server_args.py:2941-2968` | `remote-server-log.txt:6` | OBSERVED |
| 29 | Max running requests | `1` | `server_args.py` | `remote-server-log.txt:6,60` | OBSERVED |
| 30 | Chunked prefill / max prefill tokens | `2048` / `16384` | `server_args.py:757-761` | `remote-server-log.txt:6,60` | OBSERVED |
| 31 | Radix cache | `disable_radix_cache=False` | `server_args.py` | `remote-server-log.txt:6` | OBSERVED |
| 32 | Attention backend | `flashinfer` | default / resolver | `remote-server-log.txt:4,6` | OBSERVED |
| 33 | CUDA graphs | decode `full` bs `[1]`; prefill `breakable` bs `[4,8,16,32]` | argv | `remote-server-log.txt:6,39,53` | OBSERVED |
| 34 | Pool topology | `KV + MAMBA`, `transfer_layer_num=32`, `hybrid_swa=False`, `hybrid_ssm=True`, `hicache_attached=True` | derived | `remote-server-log.txt:61,66,67` | OBSERVED |
| 35 | Startup timing / free-mem | `scheduler_e2e=28.04 s`, `available_gpu_mem=3.61 GB` | derived | `remote-server-log.txt:60,68` | OBSERVED |
| 36 | Live capacity semantics exercised | RH `physical/speculative` fields and HAE per-pool generations emitted, but request identity null; no park/wake/retry chain | source + runtime | `remote-server-log.txt:78,106,144,178,296,344` | UNKNOWN (not demonstrated) |
| 37 | Canonical/pinned profile artifact | none found | negative finding | `work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md:104` | UNKNOWN |

## 4. Exact launch invocation (the profile to be pinned)

Captured verbatim from the running scheduler of the authorized 3060 run
(`work/R32-artifacts/post-test-safety.txt:6-7`, duplicated at
`work/R32-artifacts/runtime-log-inspection.txt:90`):

```text
cd /root/sglang-3060-12g-hicache
export SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-rh-clean-20260910
source /root/sglang-env-3060-4b/bin/activate
python -m sglang.launch_server \
  --model-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --tokenizer-path /hy-tmp/models/Qwen3.5-4B-AWQ \
  --host 127.0.0.1 --port 30000 \
  --tp-size 1 \
  --mem-fraction-static 0.82 \
  --max-running-requests 1 \
  --max-total-tokens 65536 \
  --chunked-prefill-size 2048 \
  --max-prefill-tokens 16384 \
  --kv-cache-dtype fp8_e4m3 \
  --enable-hierarchical-cache \
  --hicache-host-memory-mode cache \
  --hicache-ratio 2.0 \
  --hicache-write-policy write_through \
  --hicache-io-backend kernel \
  --hicache-mem-layout page_first \
  --hicache-storage-backend file \
  --hicache-storage-prefetch-policy wait_complete \
  --hicache-storage-backend-extra-config '{"hicache_storage_pass_prefix_keys":true}' \
  --hicache-prefetch-speculative-fraction 0.6 \
  --cuda-graph-backend-decode full \
  --cuda-graph-backend-prefill breakable \
  --cuda-graph-bs-decode 1 \
  --cuda-graph-bs-prefill 4 8 16 32 \
  --enable-ready-horizon \
  --ready-horizon-frontier-n 8 \
  --ready-host-watermark-low 55000 \
  --ready-host-watermark-high 110000
```

Note: the running instance was launched from `/root/sglang-3060-12g-hicache`
with `python -m sglang.launch_server` (the CLI warns `sglang serve` is
preferred, `remote-server-log.txt:1-3`). `sglang` is resolved from
`/root/sglang-env-3060-4b`, and the effective interpreter in the process tree is
that env. `page_size` is resolved to `1` at runtime even though the flag was not
passed (`server_args.py:852-856`).

## 5. Capacity-semantics definitions to freeze (source contracts)

These are the semantics that later measurements must use; P0-C pins them as
source contracts, not as live-transition evidence.

1. **Physical prefetch budget** (`physical_budget_limit_tokens`): in host
   `cache` mode it is `int(0.5 * mem_pool_host.size)`
   (`cache_controller.py:657-662`). The RH telemetry field is read from
   `cc.prefetch_capacity_limit` and `cc.prefetch_tokens_occupied`
   (`scheduler.py:4707-4708`, emitted at `scheduler.py:4208`). Observed `65536`
   against host pool `131073` (`remote-server-log.txt:62,106`).
2. **Speculative sub-budget** (`speculative_budget_limit_tokens`):
   `int(hicache_prefetch_speculative_fraction * prefetch_capacity_limit)`
   (`cache_controller.py:667-669`), read at `scheduler.py:4709-4711` and emitted
   at `scheduler.py:4209`. Observed `int(0.6 * 65536) = 39321`. Demand restores
   are not charged against it; the physical budget still bounds everything
   (`server_args.py:2881-2893`).
3. **Host headroom** (`host_headroom_tokens`): computed per pass and emitted in
   `rh_preadmission_decision` / `ready_stage`
   (`scheduler.py:4195-4210`); observed `131009`/`75908`
   (`remote-server-log.txt:79,92,178`).
4. **RH watermarks**: token mode uses `ready_tokens < watermark_low` to refill
   and `watermark_high` as the single-pass token cap; count mode takes precedence
   only when both `*_count` flags are set; `high >= low` is asserted
   (`ready_horizon.py:204-259`; `server_args.py:2905-2968`). Observed token mode
   `55000/110000` (`remote-server-log.txt:69`).
5. **Wait-reason taxonomy**: `RestoreWaitReason` enum
   (`hicache_restore.py:202-207`); `DENIED_ALLOC -> HOST_ALLOC`,
   non-genuine `REVOKED_MISS -> HOST_ALLOC`
   (`hicache_restore.py:439-461`). `capacity_wake_applies` includes `HOST_ALLOC`
   (and `DEVICE_QUOTA`, `PREFETCH_BUDGET`, `FRONTIER`, `BACKUP_PENDING`) but not
   `REVALIDATE` (`hicache_restore.py:678-697`).
6. **HAE per-pool generations**: `host_alloc.v1` records carry
   `cache_instance_id`, `pool` (`kv`/`mamba`), `generation_before/after`,
   `cause`, `returned_units`, `evictable_before/after`, `telemetry_seq`
   (observed `remote-server-log.txt:144,298,326,344`).
7. **Allocation-failure terminal mapping**: a positive-hit allocation failure
   must map to `WAIT_CAPACITY/HOST_ALLOC`, not a genuine miss; the reviewed
   contract is in `review/gates/REVIEW-20260909-CAPACITY-SEMANTICS.md:33-73` and
   `review/gates/REVIEW-20260909-ALLOC-FAILED-TERMINAL.md` (cited by
   `work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md:65-66`). The Mamba auto-size
   solver that produced `53` is at `kv_cache_configurator.py:2075-2163`.
8. **Page alignment**: page size participates in storage-hit alignment and
   expected-token math (`unified_radix_cache.py:5209,5620,5889,6060`); observed
   page size is `1`, so alignment is a no-op on this profile.

## 6. Concrete bounded freeze procedure (for a fresh execution dispatch)

This procedure is **not executed here**. It is the minimal evidence-preserving
capture for a `devops-executor` under a fresh Task ID, still gated by P0-B.

### 6.0 Preconditions

- Fresh Task ID + explicit 3060-only authorization; 3090/production forbidden.
- No product/test/gate/storage/Git change; no dependency install; no model
  download; no request workload.
- Record the SSH identity/known-host policy from the existing procedure.
- One bounded capture; at most one bounded server start if no live instance is
  already running.

### 6.1 Read-only identity + hash capture (no server action)

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  'set +e; printf "hostname="; hostname; \
   printf "gpu="; nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader; \
   printf "python="; /root/sglang-env-3060-4b/bin/python --version; \
   printf "deps="; /root/sglang-env-3060-4b/bin/python -c "import orjson,msgspec,torch;print(orjson.__version__,msgspec.__version__,torch.__version__,torch.version.cuda)"; \
   printf "cd="; cd /root/sglang-3060-12g-hicache && pwd; \
   printf "server_argv=\n"; ps -eo pid,args | grep "[s]glang.launch_server"; \
   printf "log=\n"; ls -l /tmp/sglang*.log 2>/dev/null; \
   printf "src_hashes=\n"; sha256sum python/sglang/srt/managers/scheduler.py \
     python/sglang/srt/mem_cache/unified_radix_cache.py \
     python/sglang/srt/managers/scheduler_components/hicache_restore.py' \
  2>&1 | tee /tmp/P0-C-freeze-<TASKID>.transcript
```

### 6.2 Profile + derived-capacity capture from the running log (read-only)

```bash
LOG=/tmp/sglang3060-rh-clean-env-20260910   # or the live log from 6.1
grep -E "server_args=|max_mamba_cache_size|KV Cache is allocated|Mamba Cache is allocated|\
max_total_num_tokens=|hierarchical KV host pool|hierarchical Mamba cache|\
ready_pool size=|Tree cache initialized" "$LOG"
grep -oE "physical_budget_limit_tokens=[0-9]+|speculative_budget_limit_tokens=[0-9]+|\
headroom_tokens=[0-9]+" "$LOG" | sort -u
```

If no live server is running and no prior log is durably available on the remote,
start **one** bounded server using the Section 4 argv (same env/storage dir),
poll `GET /health` until first `200`, capture the startup block, then stop the
server. Do not issue any inference request. Bound this to one launch and a
predeclared timeout.

### 6.3 Pinned-value record to persist

Persist a table with, per dimension in Section 3: value, source-of-value
(argv / derived / model-config), the exact log line or source `path:line`, the
server source SHA256s from 6.1, the local branch/HEAD, and the capture timestamp.
Include the `server_args` dump line and the four derived values
(`max_mamba_cache_size`, host KV tokens/GB, host Mamba GB, physical/speculative
budget limits). Hash the transcript and the raw log.

### 6.4 Stop conditions (fail closed)

Stop and report `blocked`/`NOT_VERIFIED` without further action if any of:

1. endpoint/GPU/compute-capability/driver mismatch with Section 2;
2. no `/health` 200 within the timeout, or more than one launch is attempted;
3. the running argv or derived capacities differ from Section 3 (record the
   delta; do not "correct" it);
4. the production source SHA256s do not match the R32/current values for
   `scheduler.py`, `unified_radix_cache.py`, `hicache_restore.py`;
5. any command would need product/test/gate/storage/Git edits, a model download,
   a dependency install, or a 3090/production touch;
6. any request/load generation or allocator/scheduler-internal call is proposed
   (that is P0-B execution, out of P0-C scope);
7. the capture would require reading private/remote data outside the checkout and
   named log paths.

### 6.5 Explicitly not part of P0-C

Demonstrating `not allocable -> park -> real allocability change -> wake ->
successful restore` is the P0-B hard gate (`plan.md:20-24`) and is untouched
here. P0-C only pins the profile and the capacity-semantics contracts; it must
not be reported as a live capacity-transition result.

## 7. Search limits and provenance notes

- Searched: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (source,
  `3090-dev`, `review/gates`, `.memory/phase2-hicache-design`), and the partial
  mirror `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work`.
- Not searched: remote filesystem, `/hy-tmp` model directory contents (only the
  path is evidenced), systemd/container configs outside the checkout, and the
  3090-host profile.
- **Profile provenance gap:** the observed values come from a running process and
  its log, not from a reviewed launch script. The remote has no `.git`, so
  identity rests on the recorded SHA256s. The R32 report's self-declared hash
  (`work/P0-B-LIVENESS-RUN-20260911-R32.md:6`, `a6ddc7a9...`) does not equal the
  current file hash (`585a0499...`), so the R32 report text may have been edited
  after hashing; the raw artifact bundle hashes are recorded in the Evidence
  section below. Treat the report body as advisory and the raw artifacts as
  authoritative.
- **Source-hash reconciliation:** current local worktree SHA256s for
  `scheduler.py` (`18c39a18...`), `unified_radix_cache.py` (`35fae989...`), and
  `hicache_restore.py` (`92f4404d...`) exactly match the R32 remote hashes
  (`post-test-safety.txt:120-122`). The two test files differ
  (`test_hicache_host_allocability.py`, `test_drain_reentry.py`) because the
  R47/R52 fixture edits post-date R32; that does not affect production-profile
  identity.
- **Mirror ambiguity:** the dispatch path is relative to `/home/dev-codex/workspaces`,
  but the canonical phase2 root (with `context.md`, `plan.md`, `ledger.md` and the
  R59 stub) is the repository's `.memory/phase2-hicache-design/`. The report was
  written to the repository root; an identical mirror copy was also placed at
  `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`
  so the literal dispatch path resolves.
- No remote execution, no experiment, no server start, no product/test/gate/
  storage/Git change was performed by this invocation.

## Artifacts

- Primary: `.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`
  (repository `.memory` root).
- Mirror: `/home/dev-codex/workspaces/.memory/phase2-hicache-design/work/P0-C-PROFILE-RECON-20260911-R59.md`.

## Evidence

- `.memory/phase2-hicache-design/plan.md:20-24,65-67,80-81` (P0-C definition, hard gate, branch/HEAD).
- `.memory/phase2-hicache-design/context.md:9-15,24-32` (authorized boundary, frontier).
- `.memory/phase2-hicache-design/work/P0-B-LIVENESS-RUN-20260911-R32.md:8-23` and R32 raw bundle.
- `work/R32-artifacts/post-test-safety.txt:4-7,113-122` (GPU, launch argv, remote source hashes).
- `work/R32-artifacts/runtime-log-inspection.txt:3-7,90` (log path, argv, process tree).
- `work/R32-artifacts/remote-server-log.txt:1-6,30-34,60-69,78-79,90-107,144,178,296,344` (server_args, derived pools, RH budgets/watermarks, HAE generations, null-identity rows).
- `work/R32-artifacts/remote-server-log.txt` SHA256 `f1d374b32c8dfbc1419deb9ea01fb1732fe5af18238d55993d77e2f36b431a67`.
- `work/R32-artifacts/post-test-safety.txt` SHA256 `0e48674d454386aeff4f4df1986f1f915ae3b99cf3bb42c6254d9d5cce4439fb`.
- `work/R32-artifacts/runtime-log-inspection.txt` SHA256 `99d3d55c51d4c8f179a83f922bd56735eb801cd6774d8f11c8fb9cd259eaf0ab`.
- `work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md:68-77,104-106` (3060 env entry, negative launch-script finding).
- Source: `python/sglang/srt/server_args.py:537-545,743-756,852-861,981-1004,2604-2606,2750-2789,2866-2968`.
- Source: `python/sglang/srt/managers/cache_controller.py:293,363,652-669,1275-1280`.
- Source: `python/sglang/srt/managers/scheduler.py:4195-4210,4692-4712`.
- Source: `python/sglang/srt/managers/scheduler_components/hicache_restore.py:202-207,439-461,678-697`.
- Source: `python/sglang/srt/managers/scheduler_components/ready_horizon.py:204-259`.
- Source: `python/sglang/srt/mem_cache/kv_cache_builder.py:158-166`; `kv_cache_configurator.py:2075-2163`; `hybrid_cache/hybrid_pool_assembler.py:96-124`.
- Contract: `review/gates/REVIEW-20260909-CAPACITY-SEMANTICS.md:33-73,151-156`.
- Independent local checks this invocation: `git rev-parse` branch/HEAD; `sha256sum` of R32 artifacts and the seven production/test files.

## Summary

The authorized 3060 profile is fully recoverable from the R32 raw bundle: model
`Qwen3.5-4B-AWQ` (compressed-tensors, fp8_e4m3 KV), TP/PP 1/1, context_len
262144 with `max-total-tokens 65536`, device Mamba `53` slots, host KV pool
`131073` tokens / 2.15 GB, host Mamba 5.51 GB, page size 1, physical prefetch
budget `65536` and speculative budget `39321`, and RH flags
`frontier_n=8`, watermarks `55000/110000`. All of these are pinned to source
`path:line` references and to durable artifact lines. They are classified
OBSERVED rather than FROZEN because no reviewed 3060 launch script exists and the
R32 run never demonstrated the capacity transition. Section 6 gives the minimal
bounded, fail-closed capture procedure to ratify them. P0-B and P0-C remain
NOT_VERIFIED; this report does not accept P0-C or bypass the hard gate.

## Followups

1. Orchestrator: note that R60 (`P0-C-PROFILE-FREEZE-20260911-R60`) should use the
   Section 4 argv and Section 6 procedure; this recon is advisory and does not
   authorize execution. **NEEDS_REROUTE** only if the orchestrator wants the
   freeze re-scoped.
2. When P0-B permits, dispatch a fresh `devops-executor` for the bounded Section 6
   capture, then a fresh independent reviewer to ratify the pinned table before
   P0-C is treated as closed.
3. Do not treat the observed R32 values as P0-C acceptance until the capture is
   reviewed and hashed.

## Open issues

1. No reviewed/pinned 3060 launch script exists; the profile is process-captured,
   not declaratively frozen.
2. `max_mamba_cache_size: 53` and the host pool sizes are auto-derived from free
   memory and could drift with environment/driver changes; a fresh capture must
   confirm them.
3. Live capacity semantics under this profile remain undemonstrated (R32 emitted
   null request identity and no park/wake/retry chain). That is P0-B scope.
4. The R32 report's self-declared SHA256 does not match its current file hash;
   only the raw artifact bundle should be treated as authoritative.
5. The remote checkout has no Git identity; freeze evidence depends on recorded
   file hashes.
6. Two phase2 `.memory` roots exist (repository root and `/home/dev-codex/workspaces`).
   This report was written to both; the repository root is canonical.
