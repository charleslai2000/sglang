# COD-20260908-P0-RESIDENCY-R17-TIMING-FIX7

status: done

## Artifacts

- Source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
- Report: this file

## Exact changes

In `check_bounded_outcomes()`:

- Kept an explicit bounded assertion for the pre-seal `detach_not_sealed` record.
- Filtered the target records by `reason == "no_device_detach"` and asserted exactly one target record.
- Preserved/checked the target accounting snapshot: `reconcile_attempt_count == 3`,
  `reason_attempt_counts == {"detach_not_sealed": 2, "no_device_detach": 1}`, and
  `suppressed_diagnostic_count == 1`, plus the lifecycle suppression assertion.

In the first original sequence in `main()`:

- Added `_seal(cache, namespace, ("kv", "device"), ("mamba", "host"))` after both
  detach registrations and before the existing barrier/completion assertions.
- The existing publish assertions were retained.

In the `no_next_request` sequence in `main()`:

- Added `_seal(no_next_request, namespace, ("kv", "device"), ("mamba", "host"))`
  after its three detach registrations and before completion.
- All existing publish and at-most-once assertions were retained.

In the queue loop in `main()`:

- Added `_seal(queued, namespace, ("kv", "device"), ("mamba", "host"))` after
  both detach registrations and before token lookup.
- Queue nonempty, after-drain, and at-most-once assertions were retained.

In the `cache_a` isolation sequence in `main()`:

- Added `_seal(cache_a, namespace, ("kv", "device"), ("mamba", "host"))` after
  the KV-device `_detach_and_complete` and before cache B operations.
- The line-1200 isolation assertion was retained.

In the concurrent sequence in `main()`:

- Added `_seal(concurrent, namespace, ("kv", "device"), ("mamba", "host"))`
  after the KV-device `_detach_and_complete` and before thread startup.
- Concurrent and final single-publication assertions were retained.

In `_run_real_scheduler_checkpoint_probe.run_case()`:

- Added `_seal(cache, namespace, ("kv", "device"), ("mamba", "device"),
  (host_pool, "host"))` after the three detach registrations and before device
  completions.
- Production drain and queue assertions were retained.

No product source, remote file, ledger, gate, or unrelated file was modified.

## Verification evidence

- `python3 3090-dev/test_p0_residency_barrier_emitter.py`: exit 0.
  All focused checks passed, including the real TP=1 scheduler checkpoint
  primary/extra queue probe and the production drain/queue assertions.

- `python3 -m py_compile 3090-dev/test_p0_residency_barrier_emitter.py`: exit 0.
- `git diff --check -- 3090-dev/test_p0_residency_barrier_emitter.py`: exit 0.

## Summary

The requested FIX7 fixture-cardinality correction and explicit manifest seals are
applied. The target cases, all original sequences, concurrent case, scheduler
checkpoint probe, and focused fixture pass.

## Followups

- No follow-up is required within this FIX7 scope.

## Open issues

- No open issues remain within the authorized FIX7 scope.
- No remote/live-system claim was made; all evidence is local fixture execution.
