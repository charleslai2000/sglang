# COD-20260908-P0-RESIDENCY-R17-TIMING-FIX5

status: done

## Artifacts

- Source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
- Report: this file

## Exact diff

```diff
@@
     namespace["_t38c_note_detach"](
         cache, "node-a", "mamba", "host", "component-host"
     )
+    _seal(
+        cache,
+        namespace,
+        ("kv", "device"),
+        ("mamba", "host"),
+    )
     namespace["_t38c_note_completion"](
```

This is the minimum explicit seal wiring after both detach registrations and before either completion. The existing live-component blocker assertions and later clear-value/reconcile publication assertion remain unchanged.

## Verification evidence

Command: `python3 3090-dev/test_p0_residency_barrier_emitter.py`

Result: exit 1. The requested component contract passes, and the next full-fixture failure is:

```text
Six-field leaf/parent sidecar and no-last-write-wins checks: PASS
Exact NodeId/string lookup, missing, and ambiguity checks: PASS
Final-node-only eligibility and bounded parent diagnostic: PASS
Async durability readiness and exact-free retry: PASS
Required component snapshot and live blocker proof: PASS
Traceback (most recent call last):
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1309, in <module>
    main()
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1035, in main
    check_bounded_outcomes(regression_namespace, regression_records)
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1021, in check_bounded_outcomes
    assert outcomes[0]["reason"] == "no_device_detach"
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
```

Command: `python3 -m py_compile 3090-dev/test_p0_residency_barrier_emitter.py`

Result: exit 0.

Command: `git diff --check -- 3090-dev/test_p0_residency_barrier_emitter.py`

Result: exit 0.

## Summary

The focused component blocker now reaches and proves `live_component_value` under explicit-seal semantics, while retaining the later publication assertion. No production source, B5 behavior, or unrelated fixture assertion was changed.

## Followups

- The full fixture's next failure is owned by `check_bounded_outcomes`; investigate only under a fresh Task ID.

## Open issues

- Full fixture remains red at `check_bounded_outcomes()` line 1021 because `outcomes[0]["reason"]` does not equal `"no_device_detach"`.
- No remote or live-system claim was made; verification was local and fixture-only.
