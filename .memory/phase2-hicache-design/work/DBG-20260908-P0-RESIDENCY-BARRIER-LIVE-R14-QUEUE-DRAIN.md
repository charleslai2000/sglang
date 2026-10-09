STATUS: done

# DBG-20260908-P0-RESIDENCY-BARRIER-LIVE-R14-QUEUE-DRAIN

- Task ID: `DBG-20260908-P0-RESIDENCY-BARRIER-LIVE-R14-QUEUE-DRAIN`
- Epoch: `phase2-hicache-design / 2026-09-08`
- Role/admission: `debugger-deep`, accepted.  The assigned work is a hard
  causal diagnosis; the read-only source, remote evidence, and report-only
  write scope are valid.

## Finding

There is **no r14 evidence that a host-release queue remained undrained once
the vehicle waited**.  The opposite is directly observed in the immutable
post-stop trace: every one of the 34 release enqueues has exactly one matching
`queued_release_drain_returned` completion (25 target + 9 churn), with no
unmatched enqueue or completion.  The last enqueue at
`1788851491728543863 ns` was freed at `1788851491787041548 ns`, 58,497,685 ns
later.  Consequently, a completion-triggered direct queue drain is neither a
supported causal fix nor safe to add.  r14's persistent zero-barrier outcome
must be diagnosed at a different strict-barrier predicate.

This corrects, rather than relaxes, the working hypothesis.  The strict queue
predicate remains required and must remain fail-closed.

## Observed facts

### Queue producer, queues, and consumer

1. `HybridCacheController.append_host_mem_release()` routes primary KV pages to
   `host_mem_release_queue` and non-anchor component pages to
   `extra_host_mem_release_queues[pool]` in
   `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:434-477`.
   `_append_host_mem_release_pages()` pairs each real page with its trace token
   under `_t38c_release_handoff_lock` at `:391-420`; it then emits
   `residency_release_enqueued` at `:421-432`.
2. The product queue consumer is not a controller worker.  It is
   `UnifiedRadixCache._drain_storage_control_queues_impl()`:
   `_drain_release()` pops paired primary pages, calls the actual allocator
   `cc.mem_pool_host.free(...)`, marks the exact token complete, and logs
   `queued_release_drain_returned` at
   `unified_radix_cache.py:5451-5484`.  `_drain_extra_release()` does the same
   for every extra pool at `:5486-5530`.
3. That drain runs from `check_hicache_events()` on a scheduler step.  The
   single-rank path obtains synchronized counts and invokes the drain at
   `unified_radix_cache.py:5961-6023`; TP/PP uses the collective-count path at
   `:5539-5572`.  Scheduler prefill selection calls
   `tree_cache.check_hicache_events()` before it returns early for an empty
   waiting queue (`managers/scheduler.py:4576-4616`).
4. After both release drains, the same scheduler path polls all pending
   residency identities (`unified_radix_cache.py:5532-5537`).  Exact token
   completion itself also re-enters the strict barrier fold under the cache
   `RLock` (`:358-397`).

### r14 completion evidence

Remote artifact inspected:
`root@175.155.64.171:24052:/data/evidence-gate3-parked/p0-s25-v43-emitter-fix5-live-r14/raw/trace-post-stop.jsonl`.

Read-only counter/multiset analysis over `(pool, tier, slot_digest,
session_id, session_generation, build_rid)` found:

| Evidence | Count/result |
| --- | ---: |
| `residency_release_enqueued` | 34 |
| `residency_free_complete` with `reason=queued_release_drain_returned` | 34 |
| unmatched enqueues / unmatched queue-drain completions | 0 / 0 |
| target enqueued / target drained | 25 / 25 |
| churn enqueued / churn drained | 9 / 9 |
| final enqueue -> final queue-drain completion | 58.497685 ms |
| strict `residency_barrier` | 0 |

The enqueue records are emitted by the controller and the matching completion
records by the radix consumer.  Both have the same r14 process/thread identity
in the inspected records (`process_id=1045886`, `thread_id=125448705087296`).
They are evidence of actual host-pool allocator return, not merely device
free-complete instrumentation.

Device and host completion are distinct:

- `_drain_device_frees()` immediately returns device slots and logs
  `allocator_free_returned` (`unified_radix_cache.py:2573-2605`).
- `_drain_host_frees()` immediately returns only direct component-owned host
  values (`:2607-2637`).
- Queued controller pages do not become free at enqueue; they become free only
  at the consumer's `mem_pool_host.free` calls above.  r14 has direct evidence
  that this final step happened for all 34 queued pages.

The r14 trace also has all 25 target build and durability records.  Each target
build's final node has at least KV-device and Mamba-device detach evidence;
14/25 additionally have Mamba-host detach evidence.  This makes the absence
of all 25 barriers real, but does not prove which remaining barrier predicate
returned.

## Causal chain and competing hypotheses

```
tree/component free action
  -> append_host_mem_release (handoff lock; page + exact token)
  -> scheduler check_hicache_events
  -> TP/PP-safe drain count + paired pop
  -> mem_pool_host.free + exact completion
  -> strict fold / pending-identity poll
  -> residency_barrier OR another strict predicate returns
```

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| H1: last-churn release pages stayed queued because no later client request arrived | **Refuted** | r14's 34/34 exact enqueue/drain multiset and the final 58.5 ms drain prove the scheduler consumer did run after the final enqueue. |
| H2: no scheduler callback exists outside a later request | **Refuted as stated** | `check_hicache_events()` is the product-owned scheduler hook, including before the empty-waiting-queue return; the trace proves it ran. |
| H3: the 1,992 free-complete records establish host queue completion | **Too broad** | Most are device/direct allocator frees.  Only the 34 `queued_release_drain_returned` records establish queued host-page completion; those 34 are all complete. |
| H4: FIX5's queue guard persistently suppressed all target barriers | **Refuted for r14** | A transient suppression is intended, but after every queue is emptied the completion retry and post-drain poll run.  A persistent queue-nonempty condition is incompatible with the exact 34/34 evidence. |
| H5: another strict fold predicate returns after queues empty | **Supported, not localized** | Zero barriers remains after the demonstrated drains.  Candidate predicates are node lookup/root/tombstone, identity equality, build/durability membership, expected-token completion, live component values, or a transient/concurrent extra queue. |

## Lock/topology assessment

A direct call to `drain_storage_control_queues()` from an arbitrary completion
or controller callback is unsafe and is rejected as a FIX6 direction:

- The drain performs TP/PP count synchronization and must consume the same
  queue count on all ranks (`unified_radix_cache.py:4883-4901, 5539-5572,
  5660-5713`).  A local controller/background-thread drain can diverge ranks
  or collide with the scheduler-owned collective order.
- The handoff lock protects page/token pairing, not the full controller drain.
  The strict fold takes the cache `RLock` and then the handoff lock
  (`:404-477`); the pair-pop takes the handoff lock and invokes completion only
  after it releases it (`hybrid_cache_controller.py:495-505`,
  `unified_radix_cache.py:5465-5471`).  Re-entering the collective drain while
  either lock is held changes that proven ordering and risks deadlock or double
  consumption.

The correct asynchronous hook already is the scheduler-owned
`check_hicache_events()` / `drain_storage_control_queues()` checkpoint.  No
new worker or client-request dependency should be introduced for queue drain.

## Minimal recommended FIX6 scope

Do **not** implement a direct drain, a queue-guard relaxation, or a vehicle
change.  The minimal next product task should be owned by `coder` with an
independent `tester` acceptance task:

1. In the strict barrier-fold code only, add marker-gated, one-record-per-
   `(identity, retry_epoch)` diagnostic outcome telemetry that records the
   precise returning predicate and a handoff-locked snapshot of primary/extra
   queue emptiness.  It must not mutate queue state, acquire a distributed
   collective, or publish a barrier.
2. Preserve the current scheduler drain and strict predicate unchanged.
3. Run the deterministic reproducer below and one S=25 r15 live run; select a
   functional fix only after the first failing predicate is observed.  If it is
   not a queue predicate, FIX6 must be re-scoped to that predicate rather than
   labelled a queue-drain fix.

This is a diagnostic FIX6, not a claim that a functional lifecycle fix has
been established.  The current evidence does not authorize a narrower
functional change.

## Deterministic focused reproducer

Use the real `UnifiedRadixCache` controller/scheduler checkpoint (not a fake
queue and not a vehicle):

1. Create one six-field target identity and mark its exact build and durability
   membership ready.
2. Detach KV-device and Mamba-device; for the second case also detach
   Mamba-host.  Queue the host page through `append_host_mem_release()` so the
   real page/token handoff is used.
3. Invoke the ordinary scheduler-owned `check_hicache_events()` exactly once
   after the producer completes, with TP=1.  Assert: the relevant primary or
   extra queue is empty, `mem_pool_host.free` was called once per page, each
   exact token completed once, and one barrier publishes.  Invoke the
   checkpoint again and assert no second barrier.
4. Repeat under a controlled non-empty extra queue: assert zero barriers before
   its scheduler drain and exactly one only after it drains.  Repeat TP=2/PP=2
   in the existing collective test harness to assert equal counts and no
   deadlock.
5. Add a variant that mirrors r14's final target node state.  The diagnostic
   outcome must name the first failed predicate; this distinguishes a stale or
   deleted node/identity/live-value problem from a queue problem without
   changing vehicle admission.

## Evidence gaps

- r14 did not record a strict-fold return reason, pending-identity count, node
  lookup status, exact completed-vs-expected token sets, or the queue snapshot
  at each return.  The broad `except Exception` at
  `unified_radix_cache.py:500-503` additionally hides a deleted-node failure.
- Engine/runtime was stopped under the authorized early-stop rule, so its
  in-memory cache/controller state cannot now be queried.  No remote runtime
  was mutated for this diagnosis.
- The preserved trace proves queue drainage but cannot identify which of the
  non-queue strict predicates rejected each target barrier.

## Artifacts and evidence

- Accepted FIX5 gate:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-RESIDENCY-BARRIER-EMITTER-FIX5.md`.
- r14 report and raw evidence above; `event-stream-stability.txt` records
  `stable=1`, `stable_after_seconds=5`, and 9,697 lines.
- r13 comparison report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-20260908-P0-S25-LIVE-EMITTER-FIX3.md`.
- Source locations cited throughout this report.  No product, test, vehicle,
  gate, ledger, or remote-runtime modification was made.

## Status packet

- Status: `done`.
- Summary: queue drain is not the r14 root cause; all r14 queued host-release
  items are already truly free/completed.  Direct completion-triggered draining
  is topology/lock unsafe and redundant with the scheduler hook.
- Followups: dispatch the narrowly scoped diagnostic FIX6 to `coder`, then an
  independent focused verification to `tester`; run a fresh live r15 only after
  the fold emits its first-failure reason.
- Open issues: the surviving strict-barrier predicate is unobserved.
- NEEDS_REASONING: a new diagnostic method (predicate-outcome telemetry plus
  focused real-scheduler reproduction) is required before selecting a
  functional product fix.  No reroute is needed; this remains hard causal
  debugging.
