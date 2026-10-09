ENTRY: ACCEPT

# SM86 Triton GDC AST fix

- Task ID: `D3060-CODER-100`
- Orchestration epoch: `2026-09-09`
- Role: `coder`
- Branch: `3060-12g-qwen35-4b`
- Repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Commit: `20fb45eb2a` (`fix: make Triton GDC AST-safe on SM86`)
- Invocation status: `done`

## Summary

Installed missing `tl.extra.cuda.gdc_wait` and
`tl.extra.cuda.gdc_launch_dependents` as `@triton.jit` no-op shims before the
affected kernels are compiled. The dispatch flag is captured before shim
installation, so a missing Triton API cannot enable GDC. Existing real
intrinsics are not replaced. The same guard now covers the exact
`layernorm_gated.py` failure path, the adjacent FLA verify/recurrent paths,
causal conv, and Mamba SSM.

## Changed files

- `python/sglang/kernels/ops/attention/fla/fused_norm_gate.py`
- `python/sglang/kernels/ops/attention/fla/fused_sigmoid_gating_recurrent.py`
- `python/sglang/kernels/ops/attention/fla/layernorm_gated.py`
- `python/sglang/kernels/ops/attention/fla/fused_kda_conv_recurrent_verify.py`
- `python/sglang/kernels/ops/mamba/causal_conv1d_triton.py`
- `python/sglang/kernels/ops/mamba/triton_ops/mamba_ssm.py`
- `test/registered/kernels/test_gdc_guard.py`

No server argument, NCCL allocator, HiCache state-machine, or 3090-branch
files were changed.

## Verification evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over all six changed
  kernel sources and `test/registered/kernels/test_gdc_guard.py`: **PASS**.
- `python3` AST parse over those seven files: **PASS**.
- Dependency-free execution of all focused GDC regression cases with a small
  pytest decorator shim: **PASS**, 6 sources × 3 cases. This covered SM86
  dispatch disabled, missing-intrinsic shim installation, preservation of a
  pre-existing real intrinsic, and SM90 dispatch requiring both real
  intrinsics.
- `git diff HEAD^ HEAD --check`: **PASS**.
- Actual Triton 3.2.0 AST-to-TTIR compilation using the production
  `layernorm_gated.py` kernel AST with the missing GDC attributes shimmed:
  **PASS** for `USE_GDC=False` and `USE_GDC=True`, targeting CUDA SM86
  (`GPUTarget('cuda', 86, 32)`). A minimal two-intrinsic probe also passed
  both constexpr branches.
- Commit scope check: `git diff --name-only HEAD^ HEAD` lists exactly the
  seven authorized files above.

## Open issues

- `python3 -m pytest -q test/registered/kernels/test_gdc_guard.py` could not
  collect because the base interpreter has no `pytest`; the test logic was
  executed directly with a dependency-free harness.
- No RTX3060 remote smoke or SM90 live GPU run was available in this
  environment. The Triton AST→TTIR evidence is local and does not claim
  runtime CUDA execution.
- Existing unrelated untracked files remain in the 3060 worktree:
  `review/gates/*`, `storage/`; they were not staged or modified.

status: done
artifacts: commit `20fb45eb2a`; this report
evidence: py_compile, AST parse, focused static regression harness, Triton 3.2.0 AST→TTIR compilation, diff/scope checks
summary: SM86-safe AST-visible GDC shims with real-intrinsic-preserving dispatch implemented and committed
followups: run the authorized remote RTX3060 smoke and an SM90 live check when the tester environment is available
open_issues: pytest package unavailable locally; no live GPU evidence

done
