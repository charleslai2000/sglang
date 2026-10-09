ENTRY: ACCEPT

# DBG-20260908-P0-RESIDENCY-R17-OUTCOME-TRIGGER

- Task ID: `DBG-20260908-P0-RESIDENCY-R17-OUTCOME-TRIGGER`
- Epoch: `phase2-hicache-design/2026-09-08`
- Role: `debugger-deep`
- Invocation status: `done`
- Scope: read-only source, accepted gates/reports, and remote r17 evidence.
  This report is the sole task write; no product, remote process, or evidence
  artifact was altered.

## Conclusion

The typed `NodeId` repair worked: r17 has **zero** `node_lookup` outcomes.
The remaining flood is a different causal chain with two populations:

1. `_t38c_record_node_context()` gives every ancestor its own valid sidecar,
   and `_t38c_note_detach()` registers every detached ancestor as pending.
   `build_complete`, however, registers only the final result node. Therefore
   460 detached ancestor identities have no possible matching build identity.
   Every scheduler storage-control drain polls them and emits
   `build_not_ready` again. This accounts for 471,464 outcomes (98.93%).
2. The ten identities that do correspond to both `build_complete` and
   `durability_barrier` initially emit `durability_not_ready`, then correctly
   advance to `live_component_value`. None passed that strict predicate before
   the authorized stop; there is consequently no later strict publication.

This is not a `NodeId` lookup, marker, queue, or logger failure. It is an
unbounded retry/diagnostic amplification caused by a mismatch between
parent-sidecar/detach eligibility and final-node build eligibility, plus a
separate, still-fail-closed live-component predicate for the ten real target
identities.

## Immutable evidence

- Remote evidence root:
  `/data/evidence-gate3-parked/p0-s25-v43-residency-node-lookup-fix1-live-r17`.
- Final trace: `raw/trace-post-stop.jsonl`, SHA-256
  `da99dfacd885573ab7736d1229e8ec54c766d1cda2f98620d9d8f870116d59ea`.
- Local and deployed `unified_radix_cache.py` agree at SHA-256
  `3dce9fe5f6551d586ea858301075ac75b5487181b9f36fe03d7b0fca87619c69`.
- Both required markers were absent before setup and present before engine
  launch. The remote final trace contains 476,553 outcome records, so this is
  neither marker absence nor global durable-log failure.
- The accepted typed-lookup gate requires a real integer `NodeId` or its exact
  decimal form and fail-closes wrong/ambiguous nodes. r17's zero lookup
  outcomes is the live confirmation that this branch no longer fails.

## Exact r17 reduction

All times are `+08:00`, from the final immutable trace.

| Event/reason | Count | First | Last | Identity population |
|---|---:|---|---|---|
| `build_complete` | 18 | 17:08:32.245869 | 17:12:11.764154 | 18 exact identities |
| `durability_barrier` | 10 | 17:09:07.481093 | 17:11:56.444361 | 10 exact identities |
| strict `residency_barrier` | 0 | — | — | none |
| `residency_barrier_outcome` | 476,553 | 17:06:52.965545 | 17:12:17.951544 | false only |
| `build_not_ready` | 471,464 | 17:06:52.965545 | 17:12:17.951544 | 460 identities; 0 build, 0 durable |
| `durability_not_ready` | 40 | 17:09:05.667404 | 17:11:56.032228 | 10 identities; all build+durable; four each |
| `live_component_value` | 5,049 | 17:09:07.496927 | 17:12:17.949862 | 10 identities; all build+durable |
| `node_lookup` | 0 | — | — | none |
| `residency_detach` / `residency_free_complete` | 744 / 768 | 17:06:52.243413 / 17:06:20.443918 | 17:12:08.382787 / 17:12:08.384646 | lifecycle-only |

The retry epoch increased from 0 to 200,923 in 325 seconds (about 618 drain
polls/s). The final poll enumerated 470 pending identities. Because outcome
deduplication is keyed by `(identity, retry_epoch, poll_attempt)`, each new
epoch authorizes another diagnostic record for every still-pending identity;
it is not a one-per-identity bound.

### Representative real target timeline

`p0-s25-s00006`, final node 56, is representative of all ten actual target
identities:

1. `build_complete`: 17:08:32.245869.
2. First `durability_not_ready`: 17:09:05.667404; device Mamba/KV detach and
   exact free-complete follow at 17:09:05.680360--.682190.
3. Three more poll outcomes remain `durability_not_ready` through
   17:09:06.992271.
4. `durability_barrier` with KV+Mamba complete: 17:09:07.481093.
5. First `live_component_value`: 15.834 ms later, at 17:09:07.496927.
   Thereafter this target emitted 756 such outcomes; its last was
   17:12:17.929082. No strict barrier was written.

The same exact pattern occurs for all ten durability identities: four
pre-durability outcomes each, then only `live_component_value` until stop.
The trace proves that at least one of `FULL` or `MAMBA`, device or host value,
was non-`None` at each fold. It does **not** identify which component/tier
remained live, because this predicate has no component-level payload.

## Source-level causal chain

1. The accepted FIX1 recorder intentionally walks the current node and all
   parents, binding each to a distinct node/hash sidecar
   (`_t38c_record_node_context`, `unified_radix_cache.py:1412-1455`).
2. Any detachable sidecar is registered in `_t38c_residency_detached`, without
   requiring membership in `_t38c_build_identities`
   (`_t38c_note_detach`, `:332-355`).
3. Only the final `result.last_device_node` gets build registration
   (`_t38c_emit_build_complete`, `:1660-1739`). Parent identities therefore
   cannot pass barrier predicate one at `:574-583`.
4. Each storage-control queue drain calls `_t38c_poll_residency_barriers`
   (`:773-788`, called at `:5850`). It retains all pending identities,
   increments epoch, and folds every one. This is the direct source of the
   460 x 200k-scale `build_not_ready` stream.
5. A valid final identity may be folded before durability because exact
   completion itself re-enters the fold (`_t38c_note_completion`, `:358-397`)
   and detach/eviction paths also call it directly. Predicate order is
   explicitly build then durability then live-component (`:574-638`), hence
   the observed pre-durability outcomes are by current design and fail closed.
6. On durability, the code adds the identity to `_t38c_durability_ready` and
   immediately folds it (`:5707-5718`). Each of the ten then reaches
   `live_component_value` rather than the publication code below `:639`.

## Suppression and liveness assessment

The **strict fold calls must not be blindly suppressed**: exact completion is
an intended product-owned retry trigger, and a later state transition could
make a legitimate final identity publish. Suppressing all pre-build or
pre-durability calls would risk losing that transition and cannot be accepted
without a lifecycle decision.

The **diagnostic emissions are safe to bound/coalesce**: `_t38c_residency_outcome`
explicitly catches failures and cannot affect the fold's return or publication
state (`:443-491`). A first-observation plus predicate-transition emission, or
a time/epoch-capped sample, preserves the fail-closed product behavior while
preventing trace exhaustion. Changing that diagnostic key alone does not
authorize publication.

The 460 impossible ancestor retries must not merely be hidden. They retain
pending tokens indefinitely while no matching build identity can arrive under
the present final-node-only build contract. Whether the correct repair is to
make only a designated terminal target eligible for residency tracking, to
give parent identities their own authoritative build lifecycle, or to retire
them at an explicit terminal condition changes the residency authority and
failure boundary; it requires a design decision.

### Stop-before-completion versus product liveness

- The vehicle was explicitly SIGTERM'd at 17:12:06 and engine SIGTERM was
  requested at 17:12:08 because trace growth drove the root filesystem to
  96%. Before vehicle stop only 16/25 target builds and 10/25 durability
  barriers existed. That incompleteness is **vehicle stop-before-completion**;
  it cannot establish a failure for the nine never-durable targets.
- Before the vehicle stop, the ten actual durable identities had already
  produced 4,399 `live_component_value` outcomes and zero barriers. The first
  durable target remained blocked for about 178.1 seconds while the engine was
  alive. This is real product fail-closed/liveness evidence for those ten
  identities, but the final stop prevents claiming that the predicate could
  never clear with more runtime.
- Thus the run is **NOT_VERIFIED**, not a deadlock or a pass: the safety stop
  prevents vehicle completion, while the persistent live-component predicate
  and unbounded impossible-ancestor retry are the product conditions that made
  completion unattainable within the authorized run.

## Competing hypotheses

| Hypothesis | Result | Evidence |
|---|---|---|
| r16 `NodeId` string/int mismatch persists | Rejected | zero `node_lookup` outcomes; deployed source matches accepted typed lookup. |
| Sidecar identity is again malformed | Rejected for observed targets | 18 exact builds and 10 exact durability identities; no `invalid_identity`. |
| Marker/logger/queue failure caused no barrier | Rejected | marker audit, 476,553 outcome logs, and lifecycle detach/free records are present. |
| All outcomes are target folds | Rejected | 471,464 are 460 identities absent from both build and durability sets. |
| Durability call never reaches the fold | Rejected | each of ten moves from four `durability_not_ready` results to `live_component_value` 15--16 ms after its durability event. |
| Product is deadlocked | Not established | scheduler drains and retries continued at high rate until stop. |
| Target identities were fully cold later | Rejected for observed interval | every post-durability fold remained `live_component_value`; no publish record exists. |

## Narrow next action

**NEEDS_REROUTE — owner: `architect`; fresh Task ID.** Define the residency
eligibility/retry contract that reconciles parent-sidecar capture with
final-node-only build authority. The task must specify: (1) which node
identities may enter pending-detach tracking, (2) their terminal retirement
condition when no build can exist, (3) a bounded/coalesced diagnostic oracle,
and (4) how a valid final identity is retried without weakening build,
durability, token, queue, or live-component predicates. This changes an
authority/failure boundary and should use the required Pattern Intake and,
if no accepted pattern governs it, a Novel Mechanism declaration.

After that contract, a separate coder task can implement the approved narrow
shape and a tester task can require: no unbounded pre-ready trace growth,
retirement/no-retry of impossible ancestors, retained retry to a legitimate
state transition, and component-level evidence for a persistent
`live_component_value` target.

## Open issues

- The trace does not name the component/tier that remains live; source only
  proves the aggregate predicate. A component-level oracle is needed before
  selecting a free/ownership repair.
- Engine teardown added post-stop trace events through 17:12:17.951544; no
  runtime conclusion uses them to claim a later product failure.
- The final trace cannot expose in-memory pending maps after engine exit;
  identity membership is reconstructed from immutable build/durability/outcome
  records and the deterministic source paths above.

## Status packet

- Status: `done`
- Artifacts: this report; r17 remote raw trace, monitor, stop, marker, and
  source-hash artifacts named above.
- Evidence: final trace hash, independent exact reductions, pre-stop cutoff
  reductions, deployed/local source-hash match, accepted node-sidecar and
  typed-lookup gates, and source call-chain inspection.
- Summary: typed lookup is fixed. The absence of strict barriers comes from
  460 never-buildable parent identities retrying unboundedly and ten genuine
  identities remaining live-component blocked; the safety stop prevented
  vehicle completion.
- Followups: fresh architect contract task, then separately authorized coder
  and tester tasks.
- Open issues: component/tier ownership behind `live_component_value` is not
  observable in r17; no claim of permanent liveness failure beyond the
  observed run interval.
