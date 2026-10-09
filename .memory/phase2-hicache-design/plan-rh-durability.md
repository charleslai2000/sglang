# Plan: PLAN-20260908-RH-DURABILITY

## Control-plane status

- Task ID: `PLAN-20260908-RH-DURABILITY`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `task-manager`
- Invocation status: `done` (the requested DAG and gate contract are written)
- Scheduler status: `pending` (downstream child tasks are not dispatched by this invocation)
- Admission: `ACCEPT`
- Authorized writes for this invocation: this file and
  `work/PLAN-20260908-RH-DURABILITY.md` only.
- Product files, ledger, and context are read-only for this invocation.

## Goal and completion contract

Convert the combined P0/P1/P2 request for the 3090/Qwen3.5-9B/HiCache parked-session line into an executable sequence:

```text
P0 durable-session instrumentation/vehicle
  -> P0 focused S=25 RH-off retest
  -> P0 independent gate decision
  -> P1 deterministic RH-on queue-horizon driver/run
  -> P2 exact same-trace RH-off/RH-on comparison
  -> scale authorization only after P0+P1+P2 PASS
```

The goal is not complete until:

1. every eligible S=25 full warm session has an observed, keyed KV+Mamba durability chain;
2. the T38C `s00002` failure is classified into one causal branch with evidence, or the gate is FAIL/BLOCKED;
3. RH-on staging is measured from engine events before admission, not inferred from a client label;
4. P2 replays one immutable request trace with the only intended arm difference being the engine RH toggle; and
5. an independent reviewer records the final gate verdict before any scale task is admitted.

## Confirmed baseline and constraints

### Evidence already observed

- `work/DBG-20260908-T38C.md` and `work/DBG-20260908-T38C-S25-MAMBA-OMISSION.md` establish that raw KV around 55,145 pages can exist while the Mamba trailing boundary is zero; the all-state `min` fold is behaving as designed.
- `work/EXP-20260908-T38C-PAIRED-TRACE-S25.md` and `work/TEST-20260908-T38C-PAIRED-TRACE-INDEPENDENT.md` establish six successful full KV+Mamba restores and one failed full sample, `s00002`; the failed query key is absent from the 25 observed successful write keys.
- `work/ORCH-20260908-T38C-METRICS-ADDENDUM.md` records all eight HTTP requests as successful, but also records two Mamba writes during the warm window. Therefore a 300-second settle is not a durability proof and late-write timing remains open.
- `work/COD-20260908-T38C-PAIRED-MAMBA-TRACE.md` records the existing gated diagnostic trace and its limitation: no keyed removal/recycle hook was added.
- The active `3090-24g-opt` worktree contains pre-existing uncommitted T38C product changes and parked-driver files. Downstream coders must preserve and review them; they must not reset or overwrite unrelated work.

### Frozen parameters to preserve

#### P0 causal vehicle

| Parameter | Frozen value |
|---|---|
| Sessions/builds | `S=25`, `25/25` expected |
| History | Qwen3.5-9B, approximately `55K` tokens; record exact tokenizer length per session |
| Active/build workers | `active=8`, `build_workers=8` |
| RH | engine RH **OFF** |
| GPU/config | FP8 KV, CUDA Graph max batch 8 |
| memory/storage | `r=0.42`, `hicache_ratio=1.3`, extent `file_size=120G`, existing fit namespace discipline |
| restore threshold | `256` tokens; short suffixes are excluded from the full-restore denominator |
| trace mode | diagnostic-only; no KV-only acceptance and no change to all-or-nothing KV/Mamba fold |

The prior `300s` settle may be retained as a diagnostic observation, but it is not a PASS condition and must not be the durability barrier.

#### P1/P2 parked comparison

| Parameter | Frozen value |
|---|---|
| Model/history | same Qwen3.5-9B vehicle and `H0≈55K`; exact prompt lengths recorded |
| Active width | `8` |
| engine | FP8 KV, CUDA Graph max batch 8, `max-running-requests=8` |
| Ready Horizon | `ready_horizon_frontier_n=8`; token watermarks `43,513/87,026` unless the engine log proves an existing explicit override |
| request semantics | natural queueing and parked-session rotation only; no `/pause_generation`, `WAIT_CAPACITY`, or synthetic scheduler pause |
| comparison | one immutable trace manifest replayed for RH-off and RH-on; only the engine `--enable-ready-horizon` arm differs |
| ordinary correctness | HTTP 200, finished, non-empty correctness digest, zero OOM/BackendError/Scheduler exception/zero-progress |

If an existing launcher has a different resolved value, record it and stop the gate; do not silently alter the frozen design.

## Hard no-go rules

1. **No `S=100`, `S=500`, or `S=1000` run may start before P0, P1, and P2 are all independently PASS.** A build, smoke, or exploratory run at those scales is not authorized by this plan.
2. A fixed sleep, including `sleep 300`, is never a durability criterion. A session is durable only after the per-session submit/ACK/frontier evidence barrier is observed. A watchdog timeout is an abort/FAIL signal, never a PASS signal.
3. Do not weaken or bypass the KV/Mamba intersection: no KV-only restore, no `min`-fold change, no threshold reduction, and no acceptance of a missing Mamba checkpoint.
4. The `s00002` branch must be classified as exactly one of:
   - `A_omitted_transfer`: expected Mamba transfer absent or `host_value` unavailable before submit;
   - `B_write_failure`: transfer submitted but keyed write/ACK is false or failed;
   - `C_key_mismatch`: successful write exists under a different key/hash identity than the warm query;
   - `D_recycle_or_remove`: keyed write succeeded, then the key was recycled/removed before lookup;
   - `E_late_write_or_barrier`: expected write/ACK becomes durable only after the lookup or the barrier was not actually reached;
   - `F_unresolved`: evidence does not distinguish A-E; this is P0 FAIL/BLOCKED, not a PASS.
5. P1 cannot be called PASS from `rh_synced`, `host_hit`, or a driver-side `RH-staged` label alone. Admission ordering must be joined to engine `restore_ready`/`restore_state=READY` and `admission` events by `rid`.
6. Any fatal remote condition (OOM, process crash, HTTP error, scheduler exception, zero progress, corrupted/empty digest, unexpected storage corruption) stops the run. Preserve logs, stop the exact process tree, and verify GPU/driver cleanup before any rerun.
7. No child may expand scope. Extra instrumentation, product fixes, scale runs, or new evidence questions require a fresh Task ID and dispatch.

## DAG and scheduler frontier

```text
RH-DUR-P0-01 (product durability trace)
             |
             v
RH-DUR-P0-02 (S=25 vehicle/collector)
             |
             v
RH-DUR-P0-03 (focused RH-off retest)
             |
             v
RH-DUR-P0-04 (independent P0 gate)
             |
             v
RH-DUR-P1-01 (deterministic queue-horizon driver)
             |
             v
RH-DUR-P1-02 (launcher/toggle smoke + RH-on run)
             |
             v
RH-DUR-P2-01 (same-trace RH-off/RH-on comparison)
             |
             v
RH-DUR-P2-02 (independent final review)
             |
             v
RH-DUR-SCALE-AUTH (orchestrator decision; PASS prerequisites mandatory)
```

All nodes are intentionally serialized. The serialization is required by the user’s ordered gate contract, the single 24052 GPU, the shared active worktree, and the fact that P1/P2 must not exercise RH on top of unresolved P0 durability. No safe parallel frontier remains after accounting for these constraints.

## Atomic task ledger

| Task ID / scheduler state | Owner | Dependencies | Exact write set | Deliverable and acceptance | Evidence/report path |
|---|---|---|---|---|---|
| `RH-DUR-P0-01` / `ready` | `coder` | T38C reports and active worktree | Only the product trace-hook changes in `python/sglang/srt/mem_cache/unified_radix_cache.py`, `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`, and `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`; no tests/driver/ledger | Extend the existing gated trace so one session/node/key identity can be followed from transfer construction through KV/Mamba submit, ACK, durable/frontier publication, query, boundary/fold, and keyed recycle/removal if it exists. Preserve all-or-nothing semantics. Add no unapproved semantic repair. `py_compile` and `git diff --check` pass; schema is versioned and documented. | `work/RH-DUR-P0-01-CODER-E20260908.md`; product diff reviewed by P0 reviewer |
| `RH-DUR-P0-02` / `blocked` | `executor` | P0-01 | Only new/isolated vehicle and parser files under `3090-dev/` named in its fresh dispatch, preferably `rh_durability_driver.py` and `rh_durability_analyze.py`; do not modify P0-01 product files or `gate3_parked.py` | Consume the frozen trace schema; emit deterministic session IDs, build/warm correlation, barrier status, branch classification fields, and the standard run artifacts. No fixed-sleep success path. Dry-run/schema fixture passes and the vehicle can prove the barrier before issuing warm lookup. | `work/RH-DUR-P0-02-EXECUTOR-E20260908.md`; local fixture output plus schema checksum |
| `RH-DUR-P0-03` / `blocked` | `tester` | P0-01, P0-02 | No product/control-plane writes; remote evidence namespace only | Run exactly one focused S=25 RH-off vehicle with the frozen P0 parameters. Use event completion barriers per session; a watchdog may abort but cannot pass the run. Require 25/25 builds, all eligible full warm sessions, keyed write/query correlation, and exact `s00002` classification. Do not start S=100+. | Remote `/root/evidence-gate3-parked/rh-dur-p0-s25-rh-off-<tag>/`; report `work/RH-DUR-P0-03-TESTER-E20260908.md` |
| `RH-DUR-P0-04` / `blocked` | `reviewer` | P0-03 | Only reviewer acceptance artifact under `review/gates/phase2-rh-durability-p0.md` and its assigned report under `work/`; no product/driver changes | Independently inspect authoritative design, P0 diff, vehicle, raw trace, join log, and cleanup evidence. PASS only if every eligible full warm has KV+Mamba restore and the barrier precedes lookup; `s00002` is A-E with direct evidence; no `F_unresolved`; HTTP/correctness/OOM/zero-progress gates are green. Otherwise FAIL/BLOCKED with branch and rerun requirements. | `review/gates/phase2-rh-durability-p0.md`; `work/RH-DUR-P0-04-REVIEWER-E20260908.md` |
| `RH-DUR-P1-01` / `blocked` | `coder` | P0-04 PASS | Only new deterministic queue-horizon driver/parser files under `3090-dev/` assigned in its dispatch; no product files and no P0 vehicle files | Implement a deterministic queue trace that creates a waiting queue larger than the resolved frontier (`N=8`), records queue position and causal timestamps, and replays the identical manifest. It must not use sleeps as staging proof, scheduler pause endpoints, or random wake timing. It must capture `ready_stage`, `ready_pool`, `restore_ready`, `restore_state`, `admission`, and `restore_success` join keys. | `work/RH-DUR-P1-01-CODER-E20260908.md`; dry-run fixture and immutable trace-manifest checksum |
| `RH-DUR-P1-02` / `blocked` | `devops-executor` plus `tester` for execution evidence | P1-01 | Remote launcher/config/evidence namespace only; no product writes | Verify the 24052 launcher resolves RH OFF/ON distinctly, confirms `frontier_n=8` and watermarks, boots a smoke cell, and proves event/rid joinability. Then run the deterministic RH-on focused cell at the authorized S=25 scale only. PASS requires `Host-ready-before-admission >=95%` over `ready_stage=result=issued` denominator, `restore_ready` or READY state at/before admission, no queue deadlock, and no correctness/health failure. Missing events => NOT_VERIFIED, not PASS. | Remote `/root/evidence-gate3-parked/rh-dur-p1-s25-rh-on-<tag>/`; reports `work/RH-DUR-P1-02-DEVOPS-E20260908.md` and `work/RH-DUR-P1-02-TESTER-E20260908.md` |
| `RH-DUR-P2-01` / `blocked` | `tester` | P0-04 PASS, P1-02 PASS | Remote evidence namespace only; immutable trace manifest is read-only | Replay the exact same request/session/turn manifest for RH-off and RH-on. The only intended arm difference is `--enable-ready-horizon`. Produce paired per-rid joins and compare: ready-before-admission rate, ready lead time, L3→Host restore wait, TTFT p50/p95/p99/max, >30s/>60s counts, storage/host/device hit tokens, recompute fraction, restore success, turns/hour, GPU utilization, ready-pool token watermarks, recycle/GC, errors, and cleanup. Hard PASS: ON ready-before-admission >=95%; `recompute_fraction_ON <= recompute_fraction_OFF + 1 percentage point`; `restore_success_ON >= restore_success_OFF`; no new recycle, host starvation, capacity deadlock, error, or zero-progress. Improvement criterion: paired bootstrap 95% CI for ON-OFF p95 L3→Host wait and TTFT must show a non-positive difference, with the report also exposing the ratio; if the frozen “significantly lower” claim is not met, verdict is FAIL/OPEN rather than silently PASS. | Remote `/root/evidence-gate3-parked/rh-dur-p2-same-trace-<off|on>-<tag>/`; report `work/RH-DUR-P2-01-TESTER-E20260908.md`; `trace-manifest.sha256`, `paired.csv`, `verdict.json` |
| `RH-DUR-P2-02` / `blocked` | `reviewer` | P2-01 | Only `review/gates/phase2-rh-durability-final.md` and assigned report under `work/` | Independently verify P0/P1/P2 artifacts, trace identity, arm diff, exact KPI calculations, health/cleanup, and no-go compliance. Issue PASS only if all hard criteria and evidence completeness hold. A reviewer cannot authorize scale by itself; it records eligibility for orchestrator decision. | `review/gates/phase2-rh-durability-final.md`; `work/RH-DUR-P2-02-REVIEWER-E20260908.md` |
| `RH-DUR-SCALE-AUTH` / `blocked-by-gates` | `orchestrator` control-plane owner | P0-04 PASS, P1-02 PASS, P2-01 PASS, P2-02 PASS | No product writes; control-plane decision only | Explicitly authorize the next scale cell only after all four reports are PASS and all evidence paths verify. Start with the previously frozen S=100 fit protocol; S=500/1000 require a separate resource/semantics authorization and retain their oversubscription caveats. No implicit authorization is granted by a PASS-shaped metric. | New orchestrator decision/ledger entry under a fresh Task ID; not produced by this plan invocation |

### Why the atomic tasks cannot be further decomposed

- `RH-DUR-P0-01` is intrinsically atomic across three product files: the node/session/key schema is only useful if transfer construction, query, and extent ACK/lifecycle records use the same identity and version. Splitting those hooks would permit independently “passing” traces that cannot be joined.
- `RH-DUR-P0-03` is intrinsically atomic at the run level: build completion, per-session barrier, warm lookup, and cleanup are one causal experiment. A partial run cannot establish the missing-key classification.
- `RH-DUR-P2-01` is intrinsically atomic as a paired experiment: splitting arms or running different manifests would destroy the exact-trace counterfactual. Per-rid parsing may be parallel internally, but the acceptance artifact must be one paired report.
- Reviewer tasks remain independent and serialized after evidence because substantive gate acceptance must not be performed by the implementer or runtime tester.

## KPI and evidence schema

### Per-session durability record (P0 required fields)

Every session must produce one JSON object or joinable row with:

```text
schema_version, session_id, build_rid, warm_rid, turn,
build_start_ts, build_end_ts, gpu_release_ts, host_release_ts,
kv_submit_ts, kv_ack_ts, mamba_submit_ts, mamba_ack_ts,
durable_ts, frontier_ts, lookup_ts, restore_ready_ts, admission_ts,
raw_kv_frontier_pages, query_mamba_key, write_mamba_key_set,
tested_present, boundary_pages, final_pages,
storage_hit_tokens, host_hit_tokens, device_hit_tokens,
restore_state, recompute_cause, recycle_remove_ts,
barrier_state, s00002_branch, outcome, evidence_ref
```

`durable_ts` means an observed storage ACK/frontier publication for the same session/node/key; it cannot be inferred from elapsed time. For every eligible full warm sample, require `mamba_ack_ts <= durable_ts <= lookup_ts`, `tested_present=true`, `boundary_pages>0`, `final_pages>0`, and a KV+Mamba restore outcome. The exact ordering may be represented by a same-timestamp sequence number where the runtime clock resolution is insufficient.

### Run-level evidence bundle

Each remote cell must preserve, under its own fresh namespace:

```text
run_manifest.json
config-resolved.txt
trace.jsonl
join.log
runs.csv
engine.log
driver.log
metrics-final.txt
cleanup.log
verdict.json
MD5SUMS
```

`verdict.json` must include task ID, epoch, git/product identifiers, resolved parameters, trace schema version, eligible/full denominator, all KPI numerators, causal branch counts, stop reason, and explicit no-go checks. `MD5SUMS` covers all immutable input manifests and evidence files after the run.

### Exact gate KPIs

| Gate | Required KPI | PASS threshold |
|---|---|---|
| P0 | full KV+Mamba restore ratio among eligible full suffixes | `100%`; short suffix `<256` excluded and counted |
| P0 | keyed durability barrier before lookup | `100%` eligible sessions; no lookup before ACK/frontier |
| P0 | `s00002` causal branch | exactly one of A-E, direct keyed evidence; F is not PASS |
| P0 | `revoked_full_miss` caused by missing Mamba / avoidable full-history recompute | `0` eligible cases |
| P0 | runtime health | HTTP/correctness/finished `100%`; OOM, BackendError, Scheduler exception, zero-progress `0` |
| P1 | RH host-ready before admission | `>=95%` of `ready_stage=result=issued` rids, engine-event join |
| P1 | queue progress | no stuck queue/rid; every planned session reaches a terminal result; no deadlock |
| P2 | exact trace identity | same manifest hash, same session/turn ordering, only RH engine flag differs |
| P2 | RH-on correctness/non-regression | recompute fraction no more than OFF +1pp; restore success not lower; no new recycle/starvation/deadlock/errors |
| P2 | RH-on staging | ready-before-admission `>=95%` and `restore_ready/READY <= admission` for counted rids |
| P2 | paired improvement | bootstrap 95% CI for ON-OFF p95 L3→Host wait and TTFT is non-positive; expose p50/p95/p99/max and ratio, with no hidden exclusion |

The prior parked Gate-B targets remain frozen for later scale authorization (`TTFT p50/p95` layer targets GPU `1/2s`, Host-ready `1.5/3s`, RH-staged `2/4s`, L3-on-demand `3/6s`; global `p99<=10s`, `>30s=0`, `>60s=0`). They are not used to bypass the P0/P1/P2 gates.

## Remote operation and cleanup protocol

1. Before boot: verify GPU idle, no stale driver/server, fresh L3 namespace, free space, and resolved config. Record the check in `run_manifest.json`.
2. During run: stream engine and driver logs; stop immediately on any hard stop condition. Do not use `pkill -f`; identify exact PIDs (`pgrep -x`/process-tree inspection), terminate the driver and server, and preserve the evidence directory.
3. After normal or abnormal stop: confirm no child processes, server exit status, GPU memory returning to the established idle baseline (approximately 15 MiB), and no storage namespace reuse before analysis. Write `cleanup.log`.
4. On a failed barrier or missing event: mark the run `FAIL` or `NOT_VERIFIED`, do not convert it with a later sleep, and do not launch the next DAG node until the reviewer records the required rerun or block.
5. Scale runs use new namespaces and fresh Task IDs. Existing T38C directories are immutable historical evidence and are not reused as writable targets.

## Open decisions and explicit followups

### Open decisions

- `OD-01`: If the resolved 24052 launcher values differ from the frozen RH frontier/watermark values, the devops owner must report the mismatch; the orchestrator decides whether to re-freeze or block. No child may change them silently.
- `OD-02`: If the P2 paired bootstrap shows no statistically supported reduction but all safety criteria pass, the reviewer must return `FAIL/OPEN` and the orchestrator decides whether a new effect-size design is warranted. It is not a PASS by safety alone.
- `OD-03`: After final PASS, the orchestrator must separately choose whether to authorize S=100 fit first and whether to authorize S=500/1000 oversubscription. The current plan authorizes neither.

### Followups

- Dispatch `RH-DUR-P0-01` with a fresh Task ID and the current worktree diff as an input; require preservation of the existing T38C trace behavior.
- Dispatch `RH-DUR-P0-02` only after the trace schema is stable; do not let the vehicle invent a second schema.
- Reconcile every child report into the ledger only through a future orchestrator task; this task-manager invocation does not edit the ledger or context.
- If P0 remains `F_unresolved`, route a fresh narrow diagnostic task to the owning product subsystem rather than advancing to RH-on.
