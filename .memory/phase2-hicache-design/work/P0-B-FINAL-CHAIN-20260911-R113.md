# P0-B-FINAL-CHAIN-20260911-R113 — bounded two-waiter live P0-B chain on the running local 3090 SGLang server

- Task ID: `P0-B-FINAL-CHAIN-20260911-R113`
- Invocation: `ses-p0b-final-chain-r113-20260911` (fresh)
- Role: `tester`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only, not modified): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
  (HEAD `4f41f5bab562b99562f30c67540eb05344d13637`)
- Server (read-only, never started/stopped/restarted/killed/reconfigured): PID `48746`
  (`launch_server`, holds GPU flock), scheduler child PID `48806`, port `30000`.

## status

**done** (bounded workload executed, raw evidence frozen, best frozen reducer run
complete). The **hard gate is NOT_VERIFIED (10/11 predicates pass)**, so the
acceptance target “one chain satisfying all 11 frozen predicates” is **NOT met**.
Exactly one leg is missing: `positive_full_hit`’s durable half — no
`durability_barrier` was emitted for the target’s `session_generation` inside the
captured window. No PASS is claimed.

The R109 defects are fixed as requested: (1) requests are session-bearing
(`session_id` → non-null `session_generation`); (2) the durable trace is enabled
and captured; (3) a **real two-waiter FIFO shape** exists and the second waiter’s
grant names the first waiter’s release terminal as predecessor. The R111
reducer’s relaxed predicates 6/7/8 all pass on this real run; only predicate 4’s
durable-barrier join fails.

## 0. Constraint compliance and baselines

- Only public HTTP (`GET /health`, `GET /v1/models`, `POST /v1/completions`) and
  reads of the existing server log and pinned `/tmp/t38c-probe.log` were used.
- No server start/stop/restart/kill/reconfigure, no GPU use, no `flock`, no repo
  edits, no product imports, no instrumentation, no synthetic events, no child
  agents.
- Baseline recorded before any request (`R113-bundle/baseline-offsets.txt`,
  `run-offsets.txt`):
  - server log `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log`
    start line `198786`;
  - `/tmp/t38c-probe.log` start byte offset `4414286`.
- Two bounded runs were driven (the first exposed the capacity/evidence gap, the
  second captured the chain). Total public HTTP: 8 POSTs (run 1) + 8 POSTs
  (run 2) + 2 GETs (preflight) = **18 requests** (limit 250). Wall clock from
  first preflight to chain capture ≈ **23 min** (limit 30). The server was left
  running and healthy.

## 1. Exact workload (run 2, `R113-bundle/requests.jsonl`)

All requests: `POST /v1/completions`, `model=/mnt/data/models/qwen35-gptq`,
`temperature=0`, `max_tokens=1`, top-level `session_id`, HTTP **200**.

| tag | session_id | prompt_tokens (usage) | rid (HTTP response) | elapsed_s |
|---|---|---|---|---|
| target-build | `r113-t` | 27375 | `59b446cfece041a19338e50e7917f6ba` | 6.099 |
| pressure-p1 | `r113-p1` | 46730 | `da519b22367b46698e2c7519b8d5d8bc` | 0.862 |
| pressure-p2 | `r113-p2` | 46796 | `9ec3754711a6431c8986bdb822b14a25` | 55.540 |
| pressure-p3 | `r113-p3` | 46703 | `ff4811e64c1041319feff3b41fb43848` | 145.362 |
| pressure-p4 | `r113-p4` | 46777 | `6b85a939a4df44d79b1fdce645381ca8` | 77.674 |
| pressure-p5 | `r113-p5` | 46629 | `58469fc3820949e48e4ad95faf07f1fa` | 77.296 |
| waiter-B (target session replay) | `r113-t` | 27375 | `7ebdd58d55e84112a05b73cbf6f9ab47` | 4.980 |
| waiter-A (replay of `r113-p1`) | `r113-p1` | 46730 (same prompt as p1) | `040529f6a0104a8ab0406478f411438e` (scheduler rid, see §2) | not recorded by client |

`waiter-A` was submitted as the two-waiter first replay; its HTTP response was
not written to the transcript because the driver process exited as soon as the
target chain was detected (daemon replay thread). Its scheduler-side identity
and complete chain are fully present in `raw.log` (§2–§4). This is a transcript
completeness gap only, not a missing chain leg (see open issues).

The pressure phase under a pre-saturated host was slow (p2–p5 took 55–145 s
because fresh prefills had to reclaim/evict), but every pressure request
returned HTTP 200.

## 2. The two waiters (both `restore_host_alloc_wait`, same blocked-domain set)

Two distinct FIFO HOST_ALLOC waiters with consecutive sequences 8 and 9 exist in
the frozen `raw.log`:

| role | rid | session | fifo_sequence | wait_id | park raw ref |
|---|---|---|---|---|---|
| **first waiter** (released before the target grant) | `58469fc3820949e48e4ad95faf07f1fa` | `r113-p5`, lifecycle `…:6` | 8 | `58469fc3820949e48e4ad95faf07f1fa:wait:8` | `raw.log:440094` |
| **second waiter = target** | `040529f6a0104a8ab0406478f411438e` | `r113-p1`, lifecycle `…:2` | 9 | `040529f6a0104a8ab0406478f411438e:wait:9` | `raw.log:556834` |

Target park (`raw.log:556834`, excerpt):

```
[HAE] {"evt":"restore_host_alloc_wait","rid":"040529f6…","state":"WAIT_CAPACITY",
 "reason":"HOST_ALLOC","wait_id":"040529f6…:wait:9","fifo_sequence":9,
 "positive_hit_tokens":46720,"requested_primary_tokens":46720,
 "blocked_domains":["kv","mamba"],"captured_generations":{"kv":183,"mamba":313},
 "cache_instance_id":1,"lifecycle_key":"040529f6…:2"}
```

Honest timing note: the first waiter parked at 22:22:32 and was released at
22:23:32; the target parked at 22:23:44. The two waits did not overlap in time
(`max_running_requests=1` and the pre-saturated host made that rare). The
producer’s `HostAllocWakeArbiter.predecessor_for` resolves predecessors from the
**released-waiter terminal history**, so what the frozen oracle requires — and
what was produced — is a consecutive FIFO waiter whose release terminal precedes
the later grant. Both park records exist; the linking join is real (below).

## 3. Release + wake grant with predecessor lineage

First waiter’s release terminal (`raw.log:556072`):

```
[HAE] {"evt":"restore_host_alloc_wake_decision","decision":"release",
 "rid":"58469fc3…","wait_id":"58469fc3…:wait:8","fifo_sequence":8,
 "event_id":"run-48806-4187756182262:host-alloc:142",
 "terminal_event_id":"run-48806-4187756182262:host-alloc:142",
 "terminal_state":"TIMEOUT","attempt_origin":"HOST_ALLOC_RELEASE",
 "retry_grant":false,"retry_skip":true}
```

Target wake grant (`raw.log:556864`):

```
[HAE] {"evt":"restore_host_alloc_wake_decision","decision":"grant",
 "rid":"040529f6…","wait_id":"040529f6…:wait:9","fifo_sequence":9,
 "event_id":"run-48806-4187756182262:host-alloc:148",
 "wake_event_id":"run-48806-4187756182262:host-alloc:148",
 "captured_generations":{"kv":183,"mamba":313},
 "current_generations":{"kv":184,"mamba":315},
 "blocked_domains":["kv","mamba"],"retry_grant":true,"retry_skip":false,
 "predecessor_wait_id":"58469fc3…:wait:8",
 "predecessor_terminal_event_id":"run-48806-4187756182262:host-alloc:142",
 "predecessor_terminal_state":"TIMEOUT",
 "predecessor_lineage_reason":null}
```

The predecessor terminal (`host-alloc:142`, `raw.log:556072`) **strictly precedes**
the grant (`host-alloc:148`, `raw.log:556864`) and its `wait_id`/`event_id`/state
exactly match the grant’s predecessor fields. Immediately after the grant the
target’s own release terminal is emitted (`raw.log:556865`,
`terminal_state:"RELEASED"`, `event_id host-alloc:149`).

Pre-wake retry (`raw.log:556830`): `attempt_id=null`, `retry_outcome="revoked_alloc_failed"`,
`retry_grant=false`, `genuine_miss=false`, `crop_attempted=false`,
`lower_checkpoint_queried=false`, `lifecycle_key="040529f6…:2"`.

Interleaved hold decisions for the target (`raw.log:556835`,
`hold_no_generation`; `raw.log:556858`, `hold_no_generation`) carry
`retry_grant=false` and are not grants.

## 4. Accepted all-or-nothing finalize + READY

Finalize (`raw.log:622646`):

```
[HAE] {"evt":"restore_hybrid_finalize","result":"accepted","all_or_nothing":true,
 "rid":"040529f6…","attempt_id":"040529f6…:4","attempt_origin":"HOST_ALLOC_WAKE",
 "wake_event_id":"run-48806-4187756182262:host-alloc:148",
 "kv_expected":46720,"kv_fetched":46720,
 "sidecars":{"mamba":{"expected":1,"fetched":1}},
 "restore_state_after":"READY","lifecycle_key":"040529f6…:2"}
```

READY (`raw.log:622651`):

```
[P3] ts_ns=5663018153699 evt=ready_host schema=rh_ready_host.v1
 rid=040529f6a0104a8ab0406478f411438e attempt_id=040529f6…:prefetch:2
 issue_origin=DEMAND_RETRY completed_kv_tokens=46720 required_aux_pools=['mamba']
 completed_aux_units={'mamba': 1} restore_state_before=RESTORING
 restore_state_after=READY finalize_result=accepted
 wake_event_id=run-48806-4187756182262:host-alloc:148
 lifecycle_key=040529f6a0104a8ab0406478f411438e:2
 run_id=run-48806-4187756182262 process_id=48806
 profile_id=profile-97ee3d5d3bfdca6237dc746e
 source_build=4f41f5bab5…:03750d85…>
```

## 5. Missing leg — durability_barrier for the target session generation

The target `lifecycle_key` is `040529f6a0104a8ab0406478f411438e:2`, so predicate 4
needs a `p0_durable`/`durability_barrier` with `session_generation = 2` (and
`kv_completed_tokens == kv_requested_tokens`, positive mamba pages, complete
trace context) inside the frozen `probe.log`.

**No such barrier exists.** The frozen `probe.log` (bytes beyond offset 4414286,
2145 lines; sha256 below) contains:

```
trace=p0_durable: 1928 records
evt histogram: backup_submit×97, backup_ack_enqueue×97, backup_ack_drain×97,
 backup_host_commit×97, batch_set_result×194, build_complete×1,
 residency_*×1345, pc_*×218, …
evt=durability_barrier: 0
evt=storage_persisted: 0
```

The **only** `durability_barrier` anywhere in `/tmp/t38c-probe.log` is the
pre-window R112 smoke record (`probe.log:26` in the full file; written before the
R113 start offset), `session_id="r112-smoke"`, `session_generation=1`,
`kv_completed_tokens==kv_requested_tokens==1664`, `mamba_expected_pages==mamba_succeeded_pages==1`.
It cannot join a generation-2 target, and the frozen slice must not include
pre-offset bytes (attribution rule), so it is not admissible evidence for this
target.

The one in-window `build_complete` (`probe.log:163`) is for `session_id="r113-t"`,
`session_generation=8`, `build_rid="59b446cfece041a19338e50e7917f6ba"`; it has no
paired `storage_persisted`/`durability_barrier` in the window. Observed fact:
for these large sessions the durable write path reached
`backup_submit`/`backup_ack_drain` but never produced the promoted
`storage_persisted`/`durability_barrier` records that the 1690-token smoke
produced. Causal ownership is left to the producer/telemetry owner.

## 6. Frozen reducer verdict

Reducer: **`work/R111-reducer/p0b_reducer.py`** (R111 preferred over R107; R111
amends predicates 6 and 8 against real emission). Command:

```
cd .memory/phase2-hicache-design/work/R111-reducer
source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
python p0b_reducer.py --events <abs>/R113-bundle/raw.log <abs>/R113-bundle/probe.log \
    --manifest <abs>/R113-bundle/manifest.json
```

**Exit code: 1. Status: `NOT_VERIFIED`. `raw_event_count: 1970`.** stderr empty.
Full 11-predicate list:

| # | predicate | passed | reason |
|---|---|---|---|
| 1 | provenance | ✅ true | |
| 2 | singular_identity | ✅ true | |
| 3 | pid_profile_source_binding | ✅ true | |
| 4 | positive_full_hit | ❌ false | `no complete positive KV+Mamba durability_barrier for the target` |
| 5 | host_alloc_park | ✅ true | |
| 6 | generation_transition | ✅ true | sampled edges seen `{kv:1, mamba:0}`; absence tolerated, no contradiction |
| 7 | fifo_predecessor | ✅ true | |
| 8 | attempt_lineage | ✅ true | |
| 9 | accepted_finalization | ✅ true | |
| 10 | ready_after_finalize | ✅ true | |
| 11 | negative_safety | ✅ true | |

10/11. The `raw_provenance` input gate passed (all hashes matched, no
caller-authored summary keys). Full output: `R113-bundle/reducer.out.json`.

## 7. Producer identity (from the captured records)

- `process_id` (scheduler): **48806**
- `run_id`: **run-48806-4187756182262**
- `profile_id`: **profile-97ee3d5d3bfdca6237dc746e**
- `source_build`: **4f41f5bab562b99562f30c67540eb05344d13637:03750d8519fdae277a0d04938c53c73ff2d5400be8c6f9f51a3d2bc7b3338d07**
- target `rid`: **040529f6a0104a8ab0406478f411438e**; `lifecycle_key`:
  **040529f6a0104a8ab0406478f411438e:2**

## 8. Artifacts and sha256

Bundle dir:
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/R113-bundle/`

| file | sha256 |
|---|---|
| `raw.log` (622663-line frozen server-log slice; all `[HAE]`/`[P3]` lines intact) | `1fa7b4d0e2c2ee2109d10324bce09cacec56e0da84b01332dac47e47e61c0829` |
| `probe.log` (2145-line frozen durable-trace slice, bytes beyond 4414286) | `4f8808a25885a62738f3f6a60740760acc5e17bff8483392957e95283ae7139c` |
| `manifest.json` (`p0b.raw-bundle.v3`) | `897864e74ebf285ccc25d5eea5bd745de18f54e6dd639db0b54d49bda06be20f` |
| `requests.jsonl` (recorded HTTP transcript; see §1 gap note) | `8b58e3540532b1b0c6ce26001a5b24b2343d19fa2b528658bc604cdbab28c686` |
| `reducer.out.json` (full R111 output) | `ee0583364c20b91c374112291201ba2e2aea81467724923ad51c303259b4a440` |
| `reducer.err.txt` (empty) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `state.jsonl` (driver state machine trace) | `ef2b6129f0e52560a301dc69b0107671d8e49c13d1e0042afd2e7e9ff109a493` |
| `run-offsets.txt` (attribution baseline) | `202d0bec78e93ac7aa2f78cf68860ae4f6466eebf07b27b78df06c365f117518` |
| `reducer.exit.txt` | see §6 (EXIT=1) |

Manifest `source_files` (producer tree hashes; unchanged from R109/R110):
`scheduler.py` `daf32da4…9dd1d`, `unified_radix_cache.py` `5d3db152…c375b`,
`telemetry_context.py` `d55b057c…f948`, `hicache_restore.py` `1cc9d2b8…b3604`,
`hybrid_cache_controller.py` `a71acb88…d669`.

## 9. Open issues

1. **Hard gate unmet: `positive_full_hit` (predicate 4).** No
   `durability_barrier` for the target’s `session_generation` exists in the
   frozen durable slice; the only barrier in the whole `/tmp/t38c-probe.log` is
   the pre-window `r112-smoke` gen-1 record. A future run can close this by
   either (a) driving the chain inside `session_id="r112-smoke"`
   (`session_generation=1`, barrier already exists) with a park/finalize, or
   (b) getting the producer to emit a complete `storage_persisted` →
   `durability_barrier` for a large session. This is a workload/config +
   producer-evidence gap, not proven absence of the positive hit: predicate 5
   passes (`positive_hit_tokens=46720 == requested_primary_tokens=46720`) and the
   restore actually fetched the full span (`kv_fetched=46720`).
2. **No simultaneous two-waiter overlap.** The first waiter was released
   (`TIMEOUT`) before the second parked; the frozen oracle’s FIFO predecessor
   join (terminal history) is satisfied, but the dispatch’s stronger
   “both parked at once” shape was not observed. If simultaneity is required, a
   future run must hold both requests parked before any allocability change
   (the pre-saturated host permitted only one eligible waiter at a time).
3. **`requests.jsonl` gap:** the `waiter-A` replay HTTP response was not written
   because the driver exited on chain capture; its rid was recovered from the
   server log (`040529f6…`). All server-side evidence for it is present.
4. **Large-session durable telemetry gap:** `backup_submit`/`backup_ack_drain`
   fired but no `storage_persisted`/`durability_barrier` was emitted for
   `r113-*` sessions in-window; owner should confirm whether the durable
   frontier genuinely lagged or the emission is gated off for large nodes.
5. R111 would be expected to supersede R107 for predicate 6/8; on this run R107
   would additionally fail predicate 6 (mamba sampled-edge absence) and possibly
   8, so **R111 is required** to interpret this chain.

## 10. Budget accounting

- HTTP: 18 total (16 POST + 2 GET), limit 250.
- Wall clock: ~23 min to chain capture, limit 30 min.
- Stopped immediately after finalize+READY were detected; no server/GPU action.
