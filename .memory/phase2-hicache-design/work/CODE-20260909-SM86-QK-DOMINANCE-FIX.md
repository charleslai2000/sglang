ENTRY: ACCEPT

# RTX3060 fused QK pointer-dominance fix

- Task ID: `D3060-CODER-103`
- Orchestration epoch: `2026-09-09`
- Role: `coder`
- Branch: `3060-12g-qwen35-4b`
- Parent commit: `7224d14629`
- Commit: `a94c11c100` (`fix: make fused QK pointer selection dominance-safe`)
- Invocation status: `done`

## Summary

Rewrote the fused QK kernel's runtime Q/K pointer selection so both branch
pointers are formed unconditionally and selected with `tl.where` over integer
addresses, followed by a single typed-pointer cast. This removes the dynamic
`if is_k` assignments whose later uses failed Triton 3.2 TTGIR dominance
verification. The `HAS_GATE`, `HAS_PASS`, and `ENABLE_PDL` constexpr behavior
and numerical operations are unchanged.

## Changed files

- `python/sglang/kernels/ops/attention/fused_qk_rmsnorm_rope_gate.py`
  - Selected input, weight, and output pointers through dominance-safe
    integer-address `tl.where` expressions.
- `test/registered/kernels/test_gdc_guard.py`
  - Added a dependency-free source regression asserting no dynamic `if is_k`
    pointer branch remains and all three runtime pointer selections are typed.

No server arguments, NCCL allocator, HiCache state machine, 3090 branch, or
unrelated kernel was changed.

## Verification evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over the kernel and focused
  test: **PASS**.
- Dependency-free focused pointer-dominance assertion: **PASS**.
- Dependency-free AST checks for the runtime branch removal and preservation of
  `HAS_GATE`/`HAS_PASS` constexpr branches: **PASS**.
- `git diff --check` and post-commit `git show --check`: **PASS**.
- Commit scope check: **PASS**; `git diff-tree` lists exactly the two changed
  authorized files.
- `python3 -m pytest -q test/registered/kernels/test_gdc_guard.py`:
  **BLOCKED before collection** because the local interpreter has no `pytest`.
- Triton 3.2 AST/TTIR/TTGIR compile and RTX3060/SM86 smoke: **not available**
  in this environment; no runtime compile or smoke success is claimed.

## Followups

- Run the focused pytest and representative Triton 3.2 SM86 TTIR/TTGIR compile
  in the approved CUDA/Triton environment.
- Re-run the remote `fused_qk_rmsnorm_rope_gate.py` smoke and independently
  check the preserved SM90 path.

## Open issues

- Local pytest, Torch, and Triton packages are unavailable, so runtime compiler
  evidence remains outstanding.
- Pre-existing untracked `review/` and `storage/` artifacts remain in the 3060
  worktree and were not staged or modified.

status: done
artifacts: commit `a94c11c100`; this report
evidence: py_compile, dependency-free focused assertion, AST checks, diff checks, and exact commit-scope verification
summary: fused QK runtime pointer selection is dominance-safe while preserving constexpr gate/pass and SM90 behavior
followups: run focused pytest, Triton 3.2 SM86 compile, remote SM86 smoke, and independent SM90 check
open_issues: local pytest/Torch/Triton unavailable; runtime compiler and GPU evidence outstanding

done
