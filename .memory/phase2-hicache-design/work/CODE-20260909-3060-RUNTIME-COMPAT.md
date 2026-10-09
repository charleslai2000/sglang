# CODE-20260909-3060-RUNTIME-COMPAT

Status: done

## Dispatch

- Task ID: `D3060-CODE-086`
- Orchestration epoch: `2026-09-09`
- Role: `coder`
- Branch: `3060-12g-qwen35-4b`
- Commit: `ac1a869e6d` (`fix 3060 Torch runtime compatibility`)
- Scope: 3060-local compatibility repair only; no remote smoke was run or claimed.

## Changes

- Escaped the single HiCache help literal from `67%` to `67%%` in
  `python/sglang/srt/server_args.py`; argparse renders it as `67%`.
- Kept `CUDAPluggableAllocator` as a direct import while resolving each of the
  three current-thread MemPool controls independently with `getattr(..., None)`.
- Added a single compatibility guard used before construction/entry/exit of
  `SymmetricMemoryContext`. It raises a deterministic `RuntimeError` with the
  installed Torch version and every missing control, without falling back to
  the older stream MemPool APIs.
- Preserved the existing `use_symmetric_memory()` nullcontext behavior for
  explicitly disabled symmetric memory and `world_size == 1`.
- Added focused tests for help formatting, both nullcontext bypasses, the
  missing-control failure before pool creation, and the all-controls
  begin/end/release behavior.

## Artifacts

- `python/sglang/srt/server_args.py`
- `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py`
- `test/registered/core/test_runtime_compat.py`
- Commit `ac1a869e6d`

## Verification evidence

- `python3 -m py_compile python/sglang/srt/distributed/device_communicators/pynccl_allocator.py python/sglang/srt/server_args.py test/registered/core/test_runtime_compat.py`: passed.
- `git diff --check`: passed before commit.
- `git show --format= --check HEAD`: passed after commit.
- Focused command `python3 -m pytest -q test/registered/core/test_runtime_compat.py`: not runnable in this local environment because `/usr/bin/python3` has no `pytest` module; the same environment also has no `torch` module.
- Final `git status --short --branch`: clean on `3060-12g-qwen35-4b`.

## Summary

The requested local source repair and focused regression test were committed on
the authorized 3060 branch. The allocator now remains importable on Torch
2.5.1-style namespaces lacking the newer private controls, bypasses the
feature for disabled/TP1 paths, and fails explicitly before symmetric-memory
pool creation when a multi-rank path requires unavailable controls.

## Followups

- A tester should run the focused tests in the approved Torch 2.5.1+cu124
  environment and perform the separately authorized bounded 3060 smoke.
- Independent gate/review ownership should verify the implementation and any
  required Pattern Intake or EXEMPT artifact under the project gate process.

## Open issues

- The local environment could not execute pytest or import the runtime stack;
  no local unit-test pass is claimed.
- No remote server launch, readiness check, request, or Qwen3.5 smoke success
  is claimed. The previously recorded SM100/libnvrtc and model/runtime risks
  remain outside this implementation task.
