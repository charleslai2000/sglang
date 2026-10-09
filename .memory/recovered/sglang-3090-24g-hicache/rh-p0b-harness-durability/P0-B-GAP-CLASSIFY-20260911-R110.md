status: done

# P0-B-GAP-CLASSIFY-20260911-R110 - why 4 of 11 frozen predicates failed on the real R109 chain

- Task ID: `P0-B-GAP-CLASSIFY-20260911-R110`
- Invocation: `ses-p0b-gap-classify-r110-20260911` (fresh)
- Role: `debugger-deep`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`,
  HEAD `4f41f5bab562b99562f30c67540eb05344d13637`, intentionally dirty.
- Boundary: analysis only. No product/test/report edits, no children, no
  instrumentation, no server/GPU action. All raw line numbers below were
  re-derived from the frozen `raw.log` with an independent parser.

## 0. Evidence basis and integrity notes

Authoritative raw lines (re-parsed; the reducer's own `raw_references` agree):

| fact | real raw.log line |
|---|---|
| pre-wake `restore_host_alloc_retry_result` (`attempt_id=null`) | 1063 |
| `restore_host_alloc_wait` park (`wait:0`, captured kv48/mamba89) | 1065 |
| hold probes `hold_no_generation` (mamba 98..104) | 1102,1106,1110,1114,1118,1122,1126 |
| kv `host_allocability_change` 48->49 | 1129 |
| grant `restore_host_alloc_wake_decision` (kv49/mamba105) | 1131 |
| release terminal `host-alloc:76` (RELEASED) | 1132 |
| accepted `restore_hybrid_finalize` | 1196 |
| `ready_host` | 1202 |
| last emitted mamba `host_allocability_change` (48->49) | 1012 |

Caveat (evidence hygiene, does not change the verdicts): the R109 bundle's
`key-lines.txt` and `P0-B-LIVE-CHAIN-20260911-R109.md` label the park at
`raw.log:1062` and the grant at `raw.log:1128`. The real lines are **1065** and
**1131** (release **1132**, retry **1063**, finalize **1196**, READY **1202**).
The frozen reducer consumed the correct lines. The off-by-3 labels are a
reporting artifact only.

The captured window covers the process's whole request-serving lifetime: the
first `[HAE]` mutation record is `telemetry_seq=1` and the last emitted mutation
record is `telemetry_seq=167`, and the final per-pool generations are kv=52,
mamba=115 (52+115=167). So the mutation counters are complete inside the
bundle, not a truncated tail.

## 1. Decision table

| predicate | class | root cause | minimal resolution | product change | source evidence |
|---|---|---|---|---|---|
| `positive_full_hit` | **C** workload/config artifact | The positive park half passed (`positive_hit_tokens=46848 >= requested_primary_tokens=46848`, raw 1065). The durable half is absent because the whole `p0_durable.v3` vehicle is marker-gated **off** (`/tmp/t38c-durable-trace` absent) and `T38C_RUN_ID` unset, and the target's `lifecycle_key` is `rid:None` because the server was launched **without** `--enable-session-radix-cache` so `req.session_generation` stayed `None`. Product code can emit it; nothing emitted. | (a) enable existing marker/env/server flag + (d) run the target within a session (build + replay same session). No code change. Requires explicit telemetry-on authorization (AGENTS.md rule 2). | **no** | server cmdline (PID 40544) and `launch-r109.sh` lack the flag; `server_args.py:1471-1476` default `False`; `scheduler.py:2807-2808,2869-2872,2913-2916`; `schedule_batch.py:904`; `session_ref_tracker.py:87-97`; `trace_context.py:10,28-29,59-81`; `unified_radix_cache.py:320-323,1818-1820,7095-7154`; reducer `p0b_reducer.py:738-773` |
| `generation_transition` | **B** oracle/reducer contract mismatch | `host_allocability_change` is **deliberately sampled**: first 16 mutations per `(pool,cause,causal_rid,trace_context)` key, then every 128th, max 64/key, max 256/instance (`unified_radix_cache.py:155-164,3784-3793`). The generation counters are complete, but emitted edges are bounded. Park captured mamba=89 (raw 1065) and grant current mamba=105 (raw 1131); **zero** mamba edges exist in `(1065,1131]` (last emitted mamba edge is raw 1012, gen 48->49). Every mamba advance still ran `_bump_host_allocability` (the only writer of the generation); the sampler suppressed the records. Total 167 mutations, 58 emitted, 109 suppressed. | (c) correct predicate 6 to accept the producer-owned generation counters plus sampled edges (e.g. require `current > captured` and bind via `telemetry_seq`/`telemetry_coalesced_mutations`, not edge-by-edge contiguity). Raising/removing the sampler would be a product change. | **no** (oracle fix) / **yes** (if full-edge audit is required) | `unified_radix_cache.py:155-164,3721-3821,3838-3882`; park `scheduler.py:3859`; grant `scheduler.py:3970-3977,3985-4027`; reducer `p0b_reducer.py:781-833` |
| `fifo_predecessor` | **C** workload shape | Only one HOST_ALLOC waiter ever existed (`fifo_sequence=0`), so the arbiter had no earlier released terminal to name; the grant and its own release correctly carry the fail-closed `predecessor_lineage_reason="no_released_predecessor"` (raw 1131/1132). The producer supports real predecessor lineage when an earlier same-blocked-domain waiter was released first. | (d) stage two HOST_ALLOC waiters where the first is released (terminal event) strictly before the second is granted. No code change. | **no** | `hicache_restore.py:159-197` (`predecessor_for`); release emission `scheduler.py:3642-3714`; grant fields `scheduler.py:3983-4027`; raw 1131/1132; reducer `p0b_reducer.py:835-883` |
| `attempt_lineage` | **B** oracle/reducer contract mismatch (frozen predicate is unsatisfiable against real emission) | `restore_host_alloc_retry_result` is emitted **only on allocation failure** (both call sites), with `attempt_id = operation.host_alloc_attempt_id`. The **initial, pre-wake** failure always emits one with `attempt_id=null` (raw 1063). A post-wake failure would emit a **second** one (with `attempt_id=rid:N`). Predicate 8 demands exactly one retry_result that is post-wake (non-empty `attempt_id` + grant `wake_event_id`), while predicate 11 additionally fails on `len(retries) > 1` (`repeated_retry`). On the real chain the single retry is the pre-wake failure (fails attempt/wake); with a post-wake failure the count becomes 2 (predicate 8 count clause and predicate 11 both fail). The oracle's own canonical fixture omits the mandatory pre-wake retry_result, so the oracle model is not real-shaped. | (c) correct predicate 8 to key on the post-wake retry (`attempt_id` non-empty / `retry_grant is true`, `wake_event_id` naming a captured grant, preserved into a later park), tolerate the pre-wake failure record, and update predicate 11's `repeated_retry` to count only post-wake retries. Also require the later park's `attempt_id` to be non-empty (today `None == None` passes vacuously). | **no** (oracle fix) | retry emission `unified_radix_cache.py:5460-5502,6575-6598`; attempt id namespaces `scheduler.py:3130-3139` (`rid:prefetch:N`) vs `scheduler.py:4251-4254` (`rid:N`); park preservation `scheduler.py:3776-3783,3821-3823,3849`; grant publish `scheduler.py:4036-4063`; finalize `unified_radix_cache.py:5717-5737`; READY `scheduler.py:4361,4409-4457`; reducer `p0b_reducer.py:885-924,1005-1006`; canonical fixture `test_reducer.py:141-347` |

## 2. Per-predicate causal reconstruction

### 2.1 `positive_full_hit` (predicate 4) - class C

Observed halves:

* Park half PASSES: raw 1065 is `WAIT_CAPACITY`/`HOST_ALLOC`,
  `positive_hit_tokens=46848`, `requested_primary_tokens=46848`,
  `sidecar_hit_pages.kv=46848`.
* Durable half ABSENT: no `p0_durable` record exists anywhere in `raw.log`
  (0 matches), and the running server log has 0 `durability_barrier` lines.

Exact gates, from source:

1. `session_generation` is produced only by
   `UnifiedRadixCache.ensure_session_generation`
   (`unified_radix_cache.py:7911-7912` -> `session_ref_tracker.py:93-97`), and
   the scheduler calls it only when `radix_native_session` is true
   (`scheduler.py:2807-2808` = request carries `session_id` **and**
   `self.enable_session_radix_cache`) or when `enable_session_radix_cache`
   (`scheduler.py:2869-2872,2913-2916`). `Req.session_generation` defaults to
   `None` (`schedule_batch.py:904`). The R109 server cmdline and
   `/mnt/data/neuron/sglang-3090-r109-20260911/launch-r109.sh` do **not** pass
   `--enable-session-radix-cache`, and `server_args.py:1471-1476` defaults it to
   `False`. Therefore the scheduler-authoritative key is
   `host_alloc_lifecycle_key(rid, None)` = `f"{rid}:None"`
   (`telemetry_context.py:98-100`, `scheduler.py:3557-3566`), matching the
   manifest `target.lifecycle_key` and raw 1063/1065/1131/1196/1202.
2. The durable vehicle is marker-gated:
   `durable_trace_enabled()`/`_t38c_durable_enabled()` test
   `/tmp/t38c-durable-trace` (`trace_context.py:10,28-29`;
   `unified_radix_cache.py:320-323`; `hybrid_cache_controller.py:74-77`). The
   marker is absent here (`ls` -> ENOENT), so `_t38c_durable_log` returns early
   and `/tmp/t38c-probe.log` is never written.
3. Even with the marker, a complete context is required:
   `make_trace_context` returns `None` unless `session_id`, a non-None
   `session_generation`, and `build_rid` are all present
   (`trace_context.py:59-81`), and `_t38c_trace_context_for_req` additionally
   requires non-empty `T38C_RUN_ID` (`unified_radix_cache.py:1818-1820`), which
   the launcher does not set.
4. `durability_barrier` is emitted only when promoted write evidence has
   `context_complete` and `kv_durable`/`mamba_durable`
   (`unified_radix_cache.py:7095-7154`; evidence `6889-6918`, `6966-7013`).

The reducer fails predicate 4 with `no complete positive KV+Mamba
durability_barrier for the target` (`p0b_reducer.py:739-769`). Note a latent
robustness bug: `_target_session_generation("rid:None")` returns the string
`"None"` (non-empty, `p0b_reducer.py:471-474`), so the predicate looks for a
barrier whose `session_generation == "None"` instead of failing
`target lifecycle_key has no session generation`. That is not the reported
reason but should be fixed with the same change.

Conclusion: the product can emit the barrier; this run disabled the whole
vehicle by configuration and had no session identity. Class **C**.

### 2.2 `generation_transition` (predicate 6) - class B

The reducer computes the deciding park (raw 1065, `fifo_sequence=0`) and the
deciding grant (raw 1131) and demands, per blocked pool, a contiguous chain of
emitted `host_allocability_change` edges from `captured` to `current`
(`p0b_reducer.py:781-833`).

Real data:

* kv: captured 48 -> grant 49; edge raw 1129 (48->49,
  `cause=lock_release_evictable`, mutation #3 of its key). kv has exactly one
  edge in `(1065,1131]` and passes.
* mamba: captured 89 -> grant 105 (raw 1065/1131); **zero** mamba edges in
  `(1065,1131]`. The last emitted mamba edge anywhere is raw 1012 (48->49).
  The hold probes (raw 1102-1126) independently show mamba 98..104 advancing.

Why the generation advanced without emitted edges - exact mechanism:

* `_bump_host_allocability` is the **only** writer of
  `self._host_allocability_generations` (`unified_radix_cache.py:3748-3753`).
  Every mutation increments the generation first, then decides whether to
  emit (`3784-3793`). So there is no silent path: every observed 89->105 advance
  ran `_bump_host_allocability`.
* Emission is deliberately coalesced: `key_emitted < HEAD(16)` OR
  `mutation_count % STRIDE(128) == 0`, capped at 64/key and 256/instance
  (`unified_radix_cache.py:155-164,159-163,3784-3793`). The telemetry key is
  `(pool, cause, causal_rid, trace_context)` (`3761`). The mutation sequence is
  complete and monotonic; only emitted records are bounded (module comment,
  `155-159`). There is no env override of the constants (grep confirms only
  definition + use).
* mamba `lock_release_evictable` and mamba `direct_free` had already emitted
  their first 16 (HEAD) earlier (e.g. raw 963 and 997, `telemetry_sample_index`
  16), so their in-window mutations fall in the suppressed 17..127 band. kv
  `lock_release_evictable` had only 3 mutations in total, so its 48->49 edge
  was emitted - which is why kv passed and mamba did not. This pool asymmetry is
  a workload x sampling interaction, not a product telemetry defect.
* Quantitative proof the counters are complete: final generations kv=52,
  mamba=115 -> 167 total `_bump_host_allocability` calls; max emitted
  `telemetry_seq` is 167; 58 edges emitted, 109 suppressed.

Conclusion: the producer explicitly bounds emitted edges and documents that
joins should use the complete generation sequence; the frozen predicate
requires every edge, so it is a contract mismatch. Class **B**.

### 2.3 `fifo_predecessor` (predicate 7) - class C

The grant at raw 1131 carries
`predecessor_lineage_reason="no_released_predecessor"` with
`predecessor_wait_id=null`; the reducer fails closed on that exact spelling
(`p0b_reducer.py:840-845`).

Source: `HostAllocWakeArbiter.predecessor_for` (`hicache_restore.py:159-197`)
returns the most recently history-recorded released terminal with the **same
blocked-domain set** and a strictly lower FIFO sequence; otherwise it returns
`no_released_predecessor`. Terminals are recorded on release emission
(`scheduler.py:3642-3714`, `record_terminal` at `3704-3713`), and the grant
publishes the resolved fields (`scheduler.py:3983-4027`). In this run only one
waiter existed (`fifo_sequence=0`), and its own release (raw 1132) is after the
grant, so it cannot be a predecessor. The producer mechanism is fully
implemented; the run simply never created a second eligible waiter. Class
**C**.

### 2.4 `attempt_lineage` (predicate 8) - class B (unsatisfiable as frozen)

The reducer (`p0b_reducer.py:885-924`) requires:

1. exactly one target `restore_host_alloc_retry_result`;
2. non-empty `attempt_id`;
3. recognized `retry_outcome`;
4. `wake_event_id` naming a captured grant;
5. that same `attempt_id` preserved into a later park;
6. accepted finalize with non-empty `attempt_id` and `wake_event_id ==
   deciding grant`;
7. single READY carrying the deciding `wake_event_id`.

Real emission facts:

* `restore_host_alloc_retry_result` is emitted **only on allocation failure**,
  at `unified_radix_cache.py:5460` (`forfeited_alloc_failed`) and
  `unified_radix_cache.py:6575-6598` (`revoked_alloc_failed`). Both pass
  `attempt_id=operation.host_alloc_attempt_id` (`5463`, `6578`). There is no
  retry_result on the successful post-wake path.
* The successful post-wake attempt is recorded by the accepted
  `restore_hybrid_finalize` (`unified_radix_cache.py:5717-5737`,
  `attempt_id=operation.host_alloc_attempt_id`) and by READY
  (`scheduler.py:4361,4409-4457`, `attempt_id=hicache_prefetch_active_attempt_id`).
* Attempt namespaces are genuinely different:
  `_claim_prefetch` builds `f"{rid}:prefetch:{seq}"` (`scheduler.py:3130-3139`),
  used for the READY attempt and the prefetch claim; the HOST_ALLOC retry
  builds `f"{rid}:{seq}"` (`scheduler.py:4251-4254`), passed down as
  `host_alloc_attempt_id` (`scheduler.py:3423-3425`) and stored on the operation
  (`unified_radix_cache.py:5540`), which is what finalize/retry_results carry.
  Hence finalize `rid:1` vs READY `rid:prefetch:2` is expected, not a bug.
* Park preservation works as the oracle expects: when a retry attempt exists,
  `_capture_host_alloc_wait` moves `hicache_host_alloc_attempt_id` into
  `hicache_host_alloc_last_attempt_id` and clears it
  (`scheduler.py:3776-3783`), then the wait record and event carry
  `last_attempt_id` (`3821-3823`, `3849`). So a re-park after a post-wake
  failure would carry `attempt_id=rid:N`.

Why the frozen predicate cannot pass on real emission:

* Every HOST_ALLOC park is produced by `RestoreEvent.DENIED_ALLOC`
  (`scheduler.py:4330,4353-4357,4369-4370`), whose failure object is recorded
  by `record_host_alloc_failure` (`unified_radix_cache.py:5503,6599`) - the
  same two failure branches that emit `restore_host_alloc_retry_result`. So a
  real park is coupled with a **pre-wake** retry_result, which necessarily has
  `attempt_id=null` because `hicache_host_alloc_attempt_id` is first assigned
  only on the post-wake `RETRY_PREFETCH` (`scheduler.py:4250-4254`).
* Case A (this run): the post-wake retry succeeds first try -> exactly one
  retry_result, the pre-wake one (raw 1063, `attempt_id=null`,
  `wake_event_id=null`) -> clauses 2 and 4 fail (the reported reason).
* Case B: the post-wake retry also fails -> a second retry_result is emitted
  with `attempt_id=rid:N` and the grant `wake_event_id`, but now
  `len(retries) != 1` (predicate 8 clause 1) and negative_safety's
  `repeated_retry` (`p0b_reducer.py:1005-1006`) both fail.
* The oracle's own canonical fixture (`test_reducer.py:141-347`) models the
  retry_result **after** `grant1` (lines 216-234) and omits any pre-wake
  retry_result; that is not what the real producer emits. So the frozen
  predicate is not real-shaped and is unsatisfiable for any real park -> wake
  -> restore chain, regardless of workload shape.

Two further latent defects in the same predicate: the "preserved into a later
park" clause passes vacuously when both ids are `None` (line 898-902), and
negative_safety counts all retry_results rather than post-wake retries.

Conclusion: class **B**. The earlier R109 classification of "workload-shape
gap" is incomplete; no workload can satisfy predicate 8 as frozen.

## 3. Closability by a follow-up workload run (no product change)

| predicate | closable by follow-up run with no product code change? | required run change |
|---|---|---|
| `positive_full_hit` | yes, but only with an existing-config/marker change plus workload | enable `/tmp/t38c-durable-trace`, set `T38C_RUN_ID`, launch with `--enable-session-radix-cache`, run build + target under one session; needs explicit authorization (AGENTS.md rule 2) |
| `generation_transition` | no (not reliably) | depends on in-window mamba mutations landing on keys below HEAD; the deciding keys are already saturated. Requires oracle correction (or a producer emission change) |
| `fifo_predecessor` | yes | stage two HOST_ALLOC waiters, release the first before granting the second |
| `attempt_lineage` | no | proven contradictory with real emission (pre-wake retry always present; post-wake failure yields two retries). Requires oracle correction (or a producer emission change) |

## 4. Minimal-resolution recommendation

Primary (no product code change; requires a re-freeze decision for the oracle):

1. `positive_full_hit`: option (a)+(d) - enable the existing durable
   marker/env/server flag and run the target within a session. No producer
   change. Gate on explicit telemetry-on authorization.
2. `generation_transition`: option (c) - amend predicate 6 to bind the
   producer-owned park `captured_generations` and grant `current_generations`
   (already non-forgeable, produced by `host_allocability_snapshot`) and treat
   emitted `host_allocability_change` records as a sampled subsequence
   (`telemetry_seq` / `telemetry_coalesced_mutations`), instead of demanding
   every edge. This matches the producer's documented contract
   (`unified_radix_cache.py:155-159`).
3. `fifo_predecessor`: option (d) - two-waiter workload.
4. `attempt_lineage`: option (c) - identify the post-wake retry by
   `retry_grant is true` / non-empty `attempt_id` and `wake_event_id` naming a
   captured grant, tolerate the mandatory pre-wake failure record, require a
   non-empty `attempt_id` on the later park, and scope negative_safety's
   `repeated_retry` to post-wake retries. Also make
   `_target_session_generation` treat literal `None` as absent.

Alternative if the program requires an unsampled, edge-by-edge auditable chain
(this is a real product change, not minimal):

* predicate 6: emit a spanning `host_allocability_change` summary at park/grant
  boundaries (or raise HEAD/stride); and
* predicate 8: emit the successful post-wake attempt as an explicit record
  (the finalize/READY pair already carries it, but the oracle keys on the retry
  event name), and distinguish pre-wake failure retries from post-wake retries.

Do not silently both weaken the oracle and change the producer; pick one under
the orchestrator/user's authority.

## 5. Open questions / decisions needed

1. Is `--enable-session-radix-cache` intended for the P0-B profile, and is
   enabling the `/tmp/t38c-durable-trace` marker + `T38C_RUN_ID` authorized
   (AGENTS.md rule 2)? Without all three, predicate 4 is unreachable.
2. May the R107 frozen oracle be corrected (predicates 6 and 8, plus
   negative_safety's repeated_retry count)? The freeze document declares itself
   authoritative; a re-freeze decision is required.
3. For predicate 4, does the durable barrier actually reach `mamba_durable=True`
   on this model/profile once the marker and session are enabled? Not
   observed; runtime-dependent, requires a gated run.
4. Evidence hygiene: `key-lines.txt` and the R109 report mislabel park/grant as
   raw 1062/1128; authoritative lines are 1065/1131. Recommend correcting the
   bundle artifact in a future run.

## 6. Bindings (sha256)

Inputs (freshly hashed):

| artifact | sha256 |
|---|---|
| `R109-bundle/raw.log` | `e96655c1e0dd5bff442ae9527e9ceaca433889e9aa975bb8ec403613f380c971` |
| `R109-bundle/manifest.json` | `618bd0420461e8fcea5c781987f9dc335a2c71f574fa8f4641062b06b8da3edb` |
| `R109-bundle/reducer.out.json` | `89c9e78104de0d821ea73794030a5206adc15457e907fd3b4bf8f022a801245c` |
| `R107-reducer/p0b_reducer.py` | `11de96819a75dc5b82d0ca1d230c3fef9aab3fb81ecee2f0ec903e0e154c4b08` |
| `R107-reducer/test_reducer.py` | `32b409e0b84222886baabd1a7d56c71ca2939d2866ba9b91405b54318b0599e6` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `5d3db1528638dd1c593b9cd62fc1b380d278cac4cc1b4e1319e6bf89c0ac375b` |
| `python/sglang/srt/managers/scheduler.py` | `daf32da48b2d084976a19280b5b8eff2d232dfc1df2db9b2f4641a8f0ed9dd1d` |
| `python/sglang/srt/mem_cache/telemetry_context.py` | `d55b057c98a4941c307bb138002340c3e8a5a5361f58417f84a3ea176658f948` |
| `python/sglang/srt/managers/scheduler_components/hicache_restore.py` | `1cc9d2b8277039e271ce65a1e4aa7b128781b378367346edd438daee42bb3604` |

This report's sha256 is recorded in the final message after read-back.
