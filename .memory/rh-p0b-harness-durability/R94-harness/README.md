# P0-B R94 fail-closed harness

This is a disposable, evidence-only package for the authorized **RTX 3060
12G** experiment.  It does not modify product code, tests, gates, storage, or
telemetry.  It uses only the public HTTP interface and product-emitted raw
events.  It never launches a server, reads private process state, follows a
redirect, synthesizes an event, or treats a client response as scheduler
evidence.

## Driver state machine and bounds

`p0b_driver.py` enforces this order:

1. **Preflight**: loopback public `/health` must bind the declared PID,
   profile, and source-manifest identity.  A missing infrastructure endpoint is
   `BLOCKED` with an explicit reason; a reachable endpoint that cannot prove the
   binding is `NOT_VERIFIED`.
2. **Holder staging**: one public `/generate` creates the predeclared holder
   RID.  A non-bound or unusable public create response is `NOT_VERIFIED`.
3. **Target create/Gate A**: one public `/generate` creates the target RID.
   Gate A is established only by reducing the raw event file and observing the
   atomic full-KV and full-sidecar hit plus `WAIT_CAPACITY/HOST_ALLOC` park.
4. **Authoritative observation**: the driver makes bounded Gate A observations;
   it does not manufacture or redirect events.  Failure after bounded public
   creates is `NOT_VERIFIED`, never `BLOCKED`.
5. **Release**: only after Gate A may one `/abort_request` be submitted for the
   holder.  Post-abort wake, retry, restore, finalization, and READY evidence
   must still be reduced offline; the driver never reports that as PASS.

The total public request budget is six and the wall-clock budget is 600 seconds.
The endpoint must be loopback HTTP and the target label must be exactly `RTX
3060 12G`; 3090/production-looking endpoints are rejected.  Redirects are
explicitly refused.

## Raw reducer contract

The reducer accepts only raw records with these exact authoritative schemas:
`host_alloc.v1`, `admission.v2`, `restore.v1`, `finalization.v1`, and the
`rh_holder.v1`/`rh_ready_host.v1` schemas.  A normalized `p0b.trace.v1` stream,
unknown schema/version, unknown event, unknown event field, duplicate event ID,
or caller-supplied summary field is `INVALID_INPUT`.

Every record carries the nine-field identity `(rid, session_id,
session_generation, node_id, build_rid, generation, server_pid, profile,
source_manifest_id)`.  The explicit provenance JSON manifest binds the same
PID/profile/source-manifest ID, exact task/epoch/3060 target, absolute source
file paths, SHA256 digests, and bounded elapsed/request counts.  The parser
adds absolute `file:line` references; a hash or line mismatch is invalid.

The positive fixture in `test_reducer.py` is raw records plus that manifest.  It
contains no summary booleans.  The reducer derives the exact eleven R79
predicates from atomic evidence:

1. `provenance` — task, epoch, target, PID/profile, source hash/line binding.
2. `singular_identity` — all lifecycle identity fields are present.
3. `positive_full_hit` — atomic KV and sidecar counts both equal requested
   counts after an accepted target admission.
4. `host_alloc_park` — complete `WAIT_CAPACITY/HOST_ALLOC` blocked-pool cursor.
5. `generation_transition` — both pools have captured-to-next contiguous edges.
6. `fifo_retry` — predecessor terminal ordering, generation-advanced wake, and
   first retry are joined by event IDs and attempt origin.
7. `complete_restore` — complete KV/sidecar restore precedes accepted
   `ALL_OR_NOTHING` finalization.
8. `ready_after_finalize` — `rh_ready_host.v1` uses `READY`/`ACCEPTED` string
   semantics and follows the joined finalization.
9. `raw_provenance` — every derived record has parser-owned absolute source.
10. `negative_safety` — no genuine miss, crop, same-generation wake, repeated
    retry, or over-bound run.
11. `single_lifecycle` — all events share one bound identity tuple.

Missing, partial, or unbound identity/generation/telemetry is
`NOT_VERIFIED`.  Malformed schema, forgery, hash mismatch, wrong binding, or
contradiction is `INVALID_INPUT`.  `BLOCKED` is reserved for the driver's
explicit infrastructure-unavailable result.  `PASS` requires all eleven
predicates from authoritative raw events; caller summaries can never pass.

## Commands

```sh
./run_selftests.sh
python3 p0b_driver.py --target-label 'RTX 3060 12G' \
  --server-pid 251004 --profile PROFILE --source-manifest-id MANIFEST \
  --events /absolute/raw-events.jsonl --provenance /absolute/provenance.json
python3 p0b_reducer.py --events /absolute/raw-events.jsonl \
  --provenance /absolute/provenance.json
```

`manifest.sha256` pins the three Python sources, the self-test script, and this
README.  It intentionally excludes itself, the implementation report, and
runtime evidence.  The self-test runs with bytecode disabled and rejects any
`__pycache__`/`.pyc` artifact.
