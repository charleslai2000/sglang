# COD-20260908-P0-RESIDENCY-R17-TIMING-FIX6

status: blocked
invocation: NEEDS_REROUTE

## Artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/COD-20260908-P0-RESIDENCY-R17-TIMING-FIX6.md`

## Changes

In `check_bounded_outcomes`, added the MAMBA host detach expectation and sealed the
complete host-only manifest with exactly:

```python
_seal(cache, namespace, ("kv", "host"), ("mamba", "host"))
```

The existing `no_device_detach` and suppressed-diagnostic assertions were preserved.
No product source or remote/live system was modified or claimed.

## Verification evidence

- `python 3090-dev/test_p0_residency_barrier_emitter.py`: exit 127; `python` is not
  available in the workspace.
- `python -m py_compile 3090-dev/test_p0_residency_barrier_emitter.py`: exit 127;
  `python` is not available in the workspace.
- `python3 -m py_compile 3090-dev/test_p0_residency_barrier_emitter.py`: exit 0.
- `git diff --check -- 3090-dev/test_p0_residency_barrier_emitter.py`: exit 0.
- `python3 3090-dev/test_p0_residency_barrier_emitter.py`: exit 1. The fixture
  reached a later failure after the preceding checks passed:

  ```text
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1024, in check_bounded_outcomes
    assert len(outcomes) == 1
  AssertionError
  ```

Per dispatch, execution stopped at that failure and no diagnosis or scope expansion
was performed.

## Summary

The requested explicit detach-seal adaptation is applied and syntax/diff checks pass.
The full focused fixture remains blocked by the exact failure above.

## Followups

Route the line-1024 fixture failure to the appropriate diagnosis/verification owner
under a fresh Task ID.

## Open issues

- Full focused fixture does not complete: `len(outcomes) == 1` fails in
  `check_bounded_outcomes` at line 1024.
