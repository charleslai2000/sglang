# P0-B HOST_ALLOC harness scout — R34

- ENTRY: ACCEPT
- Task ID: `P0-B-HARNESS-SCOUT-20260911-R34`
- Invocation identity: `ses-p0b-harness-scout-r34-20260911`
- Epoch: `2026-09-11`
- Role: `scout`
- Status: `done`
- Scope: read-only local inspection of the two local SGLang worktrees, their tests/scripts/evidence, phase2 memory, and review gates. No remote access, experiments, engine/launcher execution, 3090/production access, or product edits were performed.

## Artifacts inspected

Primary candidate worktree:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_trace_context_v4.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore_scheduler_feed.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/test/registered/unit/managers/test_hicache_host_allocability.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_hicache_restore.py`, `test_drain_reentry.py`, `test_storage_regression.py`, `test_fbe_flush_before_evict.py`, `test_prefetch_budget_split_unit.py`, and `test_writeback_reserve_unit.py` were identified by the local README/gate references; only the directly relevant portions were searched, not executed.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/rh_durability_driver.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/README.md`
- Relevant gates: `review/gates/P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md`, `P0-R7-JOIN-ROBUSTNESS-FIX4.md`, `P0-R7-JOIN-ROBUSTNESS-FIX5.md`, `P0-RESIDENCY-BARRIER-EMITTER-FIX2.md`, `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md`, and HOST_ALLOC/RH pattern-intake gates under `storage/review/gates/`.

Secondary local worktree inspected for existing load drivers:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/cap_ratio_driver.py`
- Its `p2io_e24*`, `p2io_e25*`, `p2io_e26*`, `p2io_e27*`, and `p2io_e28*` names were located by targeted search; these are backend/shape probes rather than a P0-B session/barrier vehicle.

Phase2 memory search:

- `/home/dev-codex/workspaces/.memory/phase2-hicache-design/` contains P0-A reports/transcripts only in the inspected tree.
- No R32-named file, raw R32 artifact, or P0-B-specific memory report was found under that memory directory or the two repository trees by filename search.

Repository instructions read:

- Global `/home/dev-codex/AGENTS.md` (no unauthorized auditing; no edits beyond authorization).
- `/home/dev-codex/workspaces/neuron/AGENTS.md` was read during repository-rule discovery; it is outside the target worktrees and does not add a rule for this inspection.
- The only target-relevant discovered `AGENTS.md` is the documentation-scoped SGLang docs guide; it does not govern the Python vehicle/tests. No target repository-root `AGENTS.md` was found.

## Candidate capabilities and evidence

### 1. `p0_session_barrier_vehicle.py` — strongest existing vehicle, but not a HOST_ALLOC driver

Observed capabilities:

- It is explicitly a collector/vehicle, not an engine launcher (`:11-13`), and its manifest records `remote_process_started: False` (`:765-780`).
- It correlates per-session `session_id` with `build_rid`, `node_id`, and `final_kv_hash`; the exact required identity is declared at `:32-33` and enforced by reducer checks around `:202-245`.
- Its `ready_for_warm()` gate requires identity, explicit KV durability, explicit Mamba durability, combined durability, cold residency, exactly one identity, no early lookup, no invalid join, no barrier error, and no reducer errors (`:364-378`).
- Its row ordering requires build < KV/Mamba evidence < durability barrier < cold residency < warm (`:398-430`).
- Its final accounting requires all planned full sessions, exact identity/order, successful build and warm HTTP/SSE/response-ID admission, warm issuance, restore success, and no invalid join (`:731-754`).
- It has a real tailer and causal arrival-order reducer. `EventTailer.wait_for()` checks errors before and after the predicate (`:492-507`); FIX5 gate evidence says this narrow parser race/fixture scope was accepted, while historical live R7 evidence remains NOT_VERIFIED.
- Build phase submits all builds independently of later barrier waits (`:842-919`), and churn phase creates bounded auxiliary builds to pressure eviction (`:922-1034`). This is useful harness structure for a future live chain, but churn is not itself a verified HOST_ALLOC transition.

Missing capabilities for the requested full P0-B chain:

- No HOST_ALLOC event/state correlation is present in the vehicle's scoped event names (`:61-81`); there is no `host_alloc.v1` generation/FIFO/attempt reducer, no `HostAllocFailure`, no blocked-domain cursor, and no capacity snapshot join.
- The vehicle's explicit warm gate waits on product-emitted durability/residency events, not on a real positive-hit allocation failure followed by host-capacity release/transition and a scheduler retry.
- `ready_for_warm()` gates issuance of the warm request, but it does not drive or observe the scheduler's `WAIT_CAPACITY/HOST_ALLOC -> retry -> full restore -> READY` transition. `restore_ready()` only validates a restore success event/order (`:386-396`).
- The vehicle identity is four fields and omits session generation and HOST_ALLOC generation. This is consistent with the vehicle's V3 contract, but insufficient as evidence for the requested RID/session/node/build/generation chain.
- The vehicle's `mamba_durable` evidence is a boolean event predicate (`:115-120`), not proof that the full Mamba sidecar was allocated/restored atomically with the complete KV span.

### 2. `test_hicache_restore_scheduler_feed.py` — deterministic scheduler-side oracle, not a full driver

Observed capabilities:

- Positive allocation failure maps to `WAIT_CAPACITY` with `RestoreWaitReason.HOST_ALLOC` and clears miss evidence (`:218-232`).
- A capacity fixture uses a 54,976-token requested span and changes available host capacity from 54,976 to 54,992; the scheduler predicate returns true (`:234-254`).
- The file separately checks resident short-tail behavior does not enter revalidate (`:256-285`) and genuine miss epoch/generation handling (`:288-437`).
- The same file contains backup-pending wake/reissue tests that preserve FIFO/ticket behavior and demand-restore classification (`:1-15`, `:141-176`).

Missing capabilities:

- The tests use `SimpleNamespace` stubs and lambdas for `available_size`, terminal queues, and predicates. They do not perform a real allocator transition, release/eviction, storage restore, Mamba allocation, or final READY event.
- They do not correlate a live product request through RID/session/node/build/generation across engine events.
- They are scheduler mapping/capacity semantics oracles, not an executable end-to-end harness.

### 3. `test_hicache_host_allocability.py` — strongest HOST_ALLOC generation/FIFO unit fixture

Observed capabilities:

- Defines typed `HostAllocabilitySnapshot`, `HostAllocWaitCursor`, `HostAllocWakeArbiter`, and `HostAllocFailure` fixtures (`:8-20`, `:22-45`).
- Tests unlock-to-evict and actual-free generation opportunities, no-change no-spin/FIFO rotation, auxiliary/Mamba generation requirements, post-cleanup no-self-wake, full-span-only/trailing-sidecar no-crop, immediate waiter removal, telemetry schema, and generation bump rules (`:66-231`).
- The hybrid test explicitly requires both KV and Mamba generations to advance before retry (`:115-126`); the failure fixture requires full span and records Mamba as a failed domain (`:157-178`).

Missing capabilities:

- It is a dependency-backed unit suite, not a driver. It does not submit requests or consume a real event stream.
- The gate report records collection blocked by missing `orjson` (`REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:28-33`), so current checked-out evidence does not establish a passed runtime invocation here.
- The reviewed HOST_ALLOC telemetry gate has prior blocking findings: unsafe optional duck-typed transfer access, unbounded cache-side mutation telemetry, and discarded-hybrid restore-state mismatch (`REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:62-133`). These are design/evidence constraints against treating this unit as an auditable full-chain proof.

### 4. `rh_durability_driver.py` — synthetic reducer/dry-run vehicle, explicitly not sufficient

Observed capabilities:

- It reduces `p0_durable.v2` events and writes a manifest, JSONL trace, CSV, verdict, join log, metrics, cleanup log, and checksums (`:27-80`, `:100-122`).
- It has explicit synthetic build/backup/ACK/durability/residency/warm/restore fixture rows (`:82-98`).

Blocking limitations:

- It has no HOST_ALLOC state or generation fields, uses a four-field key (`:36-37`), and its fixture synthesizes the entire chain, including `restore_outcome` (`:82-98`).
- `--live` explicitly refuses incomplete integration (`:124-136`), stating that the existing parked driver cannot enforce the required per-session happens-before edge.
- Its dry-run verdict is `NOT_VERIFIED` (`:111-115`, `:137`). It cannot demonstrate a real capacity transition or full KV+Mamba restore.

### 5. `cap_ratio_driver.py` and P2-IO probes — load/backend probes, not P0-B

`cap_ratio_driver.py` does provide real client load-shape/evidence mechanics: deterministic multi-agent histories, warm turns, per-request RID/session/TTFT/cache-hit fields, metrics deltas, and evidence files (`:2-31`, `:147-179`). However, it assumes an already booted engine (`:27`), records host/device/storage hit counters rather than HOST_ALLOC generations or scheduler wait/retry identity, and has no full KV+Mamba finalization/READY oracle. The P2-IO probes target extent backend write/query/shape behavior; targeted names and snippets show Mamba pool registration and sidecar hit experiments, not a session barrier or HOST_ALLOC liveness chain.

## Design-gate constraints affecting acceptance

- `P0-VEHICLE-BARRIER-SCHEDULER-FIX4.md:51-66` accepts the local vehicle/fixture boundaries only. It explicitly says supplied live S=25 evidence is NOT_VERIFIED and not live runtime acceptance (`:80-100`).
- `P0-R7-JOIN-ROBUSTNESS-FIX5.md:75-101` confirms the V3 vehicle still requires exact four-field identity, ordered durability/residency barriers, and strict warm gating, but the historical runtime remains 25 unresolved joins/zero restores and is not acceptance evidence.
- `P0-RESIDENCY-BARRIER-EMITTER-FIX2.md:32-71` rejects the emitter gate because authoritative residency identity requires six fields including `run_id` and session generation; missing-context residency evidence is also absent (`:73-103`).
- HOST_ALLOC architecture/pattern gates keep HOST_ALLOC wake/fit/retry/queue authority in restore/scheduler, not Ready Horizon (`storage/review/gates/pattern-intake/PATTERN-INTAKE-20260909-RH-PREADMISSION.md:179-193`). Any procedure must therefore observe scheduler/allocator outcomes without making RH the driver authority.
- The deep HOST_ALLOC gate is rejected and records prior live-test prerequisites plus telemetry blockers (`REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:12-16`, `:150-170`).

## Finding

**BLOCKED for the requested claim.** There is no existing, test-backed, auditable HOST_ALLOC liveness harness/driver in the inspected local scope that can demonstrate the full P0-B chain without new product/harness integration or a separately supplied real trace:

`RID/session/node/build/generation correlation -> real positive-hit capacity failure -> actual capacity transition/release -> HOST_ALLOC generation/FIFO retry -> full KV + Mamba restore/finalization -> READY`.

The closest reusable pieces are composable but not already joined:

1. `test_hicache_host_allocability.py` supplies typed HOST_ALLOC generation/FIFO/full-span/Mamba-sidecar unit oracles.
2. `test_hicache_restore_scheduler_feed.py` supplies scheduler mapping and capacity predicate fixtures.
3. `p0_session_barrier_vehicle.py` supplies strict session/build/node/hash durability/residency/warm/restore event reduction and auditable bundle output.
4. `cap_ratio_driver.py` supplies real client load/evidence mechanics, but no HOST_ALLOC/READY oracle.

No candidate satisfies all acceptance legs simultaneously, and no R32 raw artifact was found to bridge the missing live evidence.

## Concrete minimal procedure if a real trace is supplied (no implementation claimed)

This is a bounded follow-on procedure, not an executed experiment and not a claim that the current files can perform it today:

1. Supply a real, current-HEAD JSONL trace containing one request with a stable six-field lifecycle identity at minimum: `run_id`, `session_id`, `session_generation`, `build_rid`, `node_id`, and final KV hash; retain RID/session/node/build/generation on every HOST_ALLOC, restore, finalization, and READY record.
2. Verify the trace has an explicit positive-hit/full-span allocation failure with `WAIT_CAPACITY/HOST_ALLOC`, pre-transition KV/Mamba capacity snapshots, the actual release/eviction/free transition, per-pool generation changes, and FIFO retry/attempt records. Do not infer transition from elapsed time or a counter-only client hit.
3. Verify both KV and Mamba sidecar requirements are complete and all-or-nothing: full requested KV span, all required Mamba pages/keys, finalizer outcome, and no crop/lower-frontier substitution.
4. Feed only that supplied trace to the existing reducer/vehicle after an authorized compatibility adapter is available; compare its strict barrier ordering with HOST_ALLOC generation/attempt records from the unit oracles. The current V3 vehicle alone will reject HOST_ALLOC records as out-of-scope, so this step identifies the exact missing integration rather than pretending it exists.
5. Accept READY only when the trace has an explicit final READY/product admission record after full restore/finalization and the exact identity remains singular and consistent. Produce a manifest, raw trace copy, reducer output, ordered barrier waits, verdict, and checksums; otherwise report NOT_VERIFIED/BLOCKED.

## Followups

- Fresh implementation/integration dispatch is required to add a read-only HOST_ALLOC event adapter/reducer or to define a canonical trace schema that joins the existing vehicle with HOST_ALLOC generation/FIFO records; this is outside scout scope.
- Fresh test dispatch is required to run `test_hicache_host_allocability.py` and `test_hicache_restore_scheduler_feed.py` in an environment with their missing dependencies, while preserving first-failure evidence.
- Fresh live/runtime dispatch is required for any real capacity transition, full restore, or READY claim; it must be separately authorized and must not use 3090/production under this task.

## Open issues

1. No R32 raw artifacts were discoverable by filename or targeted content search in the inspected local scope; their location/format is unknown.
2. The current V3 vehicle identity omits `run_id` and `session_generation`, while the residency design gate requires the six-field identity; authority for a P0-B canonical identity is unresolved here.
3. Current local HOST_ALLOC registered tests have an environment dependency block (`orjson`, and related registered suites also require `torch`); no test commands were run in this read-only scout invocation.
4. The existing vehicles can produce synthetic/dry-run PASS-shaped rows only as parser/reducer evidence; they cannot establish physical capacity transition or full KV+Mamba restoration.

## Search limits

- Inspected only `/home/dev-codex/workspaces/.memory/phase2-hicache-design`, the two named SGLang worktrees, their relevant `3090-dev`, `test`, `review/gates`, and `storage/review/gates` paths, plus applicable AGENTS instructions.
- Used targeted filename/content searches for `HOST_ALLOC`, `host_alloc`, `R32`, `RID`, `session`, `node`, `build`, `generation`, `Mamba`, `restore`, `READY`, `harness`, and `raw`; unrelated repositories, remote hosts, `/mnt/data`, production, and private memory outside the named phase2 directory were not recursively scanned.
- No experiments, test executions, imports, compilation, remote commands, or edits to product/test files were performed.

## Summary

`p0_session_barrier_vehicle.py` is the best existing auditable P0 barrier vehicle, while `test_hicache_host_allocability.py` and `test_hicache_restore_scheduler_feed.py` are the best HOST_ALLOC unit oracles. They are not joined into a real liveness driver, and `rh_durability_driver.py` is explicitly synthetic/dry-run-only. With no R32 raw artifact found, the requested full P0-B demonstration is genuinely **BLOCKED** without a fresh integration/trace and separately authorized runtime evidence.
