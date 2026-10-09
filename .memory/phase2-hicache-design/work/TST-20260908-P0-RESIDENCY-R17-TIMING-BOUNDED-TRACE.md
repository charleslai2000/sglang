ENTRY: ACCEPT

status: done

# TST-20260908-P0-RESIDENCY-R17-TIMING-BOUNDED-TRACE

## Scope and authorization

Read-only inspection and session-bounded in-memory execution of the two files named
in the dispatch. No files in the product/test tree were modified. No remote/live
system was contacted.

## Commands and exact results

Environment: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, Bash,
Python 3.12. `python` is unavailable (`exit 127`), so the equivalent defined
fixture was run with `python3`.

```text
python 3090-dev/test_p0_residency_barrier_emitter.py
exit 127
/bin/bash: line 1: python: command not found
```

```text
python3 3090-dev/test_p0_residency_barrier_emitter.py
exit 1
Six-field leaf/parent sidecar and no-last-write-wins checks: PASS
Exact NodeId/string lookup, missing, and ambiguity checks: PASS
Final-node-only eligibility and bounded parent diagnostic: PASS
Async durability readiness and exact-free retry: PASS
Required component snapshot and live blocker proof: PASS
Traceback (most recent call last):
  .../3090-dev/test_p0_residency_barrier_emitter.py", line 1024, in check_bounded_outcomes
    assert len(outcomes) == 1
AssertionError
```

The one-off command loaded the fixture's AST-extracted functions in memory, ran
the exact `check_bounded_outcomes` sequence, and printed records/state before
seal, after seal, and after eight reconciles. It did not write a temporary file.

## State evidence

Identity:

```text
('run-a', 'session-bounded', 1, 'build-bounded', 'node-a', 'hash-a')
```

Before seal, one outcome already exists:

```text
reason=detach_not_sealed result=False terminal=False lifecycle_state=BUILD_CREATED
reconcile_attempt_count=1 reason_attempt_counts={'detach_not_sealed': 1}
detach_sealed=False manifest=set() suppressed_diagnostic_count=0
```

The pre-seal reconcile was triggered by the first host-only detach registration.
The second registration did not emit another distinct record, but the first
record remains in the shared `records` list.

After explicit seal, the expected record is emitted:

```text
reason=no_device_detach result=False terminal=False lifecycle_state=BUILD_CREATED
reconcile_attempt_count=3
reason_attempt_counts={'detach_not_sealed': 2, 'no_device_detach': 1}
detach_expectations_registered=True
detach_manifest={('kv', 'host'), ('mamba', 'host')}
detach_sealed=False suppressed_diagnostic_count=1
retired=set() barriers=set()
```

After eight repeated reconciles, no record is removed and no retirement occurs:

```text
outcome reasons=['detach_not_sealed', 'no_device_detach']
reconcile_attempt_count=11
reason_attempt_counts={'detach_not_sealed': 2, 'no_device_detach': 9}
suppressed_diagnostic_count=9
retired=set() barriers=set()
```

The two session-bounded records are therefore the pre-seal `detach_not_sealed`
diagnostic and the desired `no_device_detach` diagnostic. The expected record is
present under its expected reason; it is neither missing nor removed by retirement.

## Root cause

`check_bounded_outcomes()` counts every `residency_barrier_outcome` for the
session, but the sequence intentionally registers detaches before sealing. That
registration synchronously reconciles and publishes a non-terminal
`detach_not_sealed` diagnostic. Explicit seal then emits `no_device_detach`.
The production bounded-diagnostic behavior is consistent with the observed
attempt/suppression counters; the failing cardinality assertion is fixture
assumption/timing-sensitive.

## Minimum fix proposal

Fixture-only: make the assertion select the post-seal terminal reason under test,
for example filter `reason == "no_device_detach"` and assert exactly one such
record (optionally also assert the earlier `detach_not_sealed` record is present).
Do not change production semantics based on this trace.

## Followups and open issues

Followup: tester/reviewer may decide whether the fixture should assert one target
diagnostic or preserve an explicit assertion for the expected pre-seal diagnostic.

Open issues: none for this read-only trace. `python` command availability differs
from the successful `python3` environment invocation.

No remote/live claim: all evidence is from local AST extraction and in-memory
fixture execution only.
