ENTRY: ACCEPT

# Qwen3.5 SM86 Triton GDC follow-up

- Task ID: `D3060-CODER-102`
- Orchestration epoch: `2026-09-09`
- Role: `coder`
- Branch: `3060-12g-qwen35-4b`
- Parent commit: `20fb45eb2a`
- Commit: `7224d14629` (`fix: guard Qwen3.5 Triton GDC sites on SM86`)
- Invocation status: `done`

## Summary

Applied the existing AST-safe GDC shim/capability pattern to the Qwen3.5
fused QK RMSNorm/RoPE/gate Triton module. Missing GDC attributes are installed
as `@triton.jit` no-op shims before kernel compilation, while the capability
flag is captured as false when shims were needed. `_ENABLE_PDL` therefore stays
false on SM86 and retains real GDC dispatch when both real Triton intrinsics
and SM90+ architecture support are present.

The scoped execution-path scan found the same direct GDC references in the
Triton grouped decode kernels used by the Qwen3.5 full-attention backend.
`decode_attention.py` now installs the same AST-visible shims and clamps the
public `use_pdl` request through the capability guard. The MLA-only
`mla_kv_pack_quantize_fp8.py` site was reviewed and left unchanged because it
is not part of Qwen3.5's non-MLA attention path. Existing FLA and Mamba sites
were already guarded on this branch.

## Changed files

- `python/sglang/kernels/ops/attention/fused_qk_rmsnorm_rope_gate.py`
- `python/sglang/kernels/ops/attention/decode_attention.py`
- `test/registered/kernels/test_gdc_guard.py`

No server arguments, NCCL allocator, HiCache state-machine, MoE/LORA kernel,
or 3090-branch files were changed. Pre-existing untracked review and storage
artifacts in the 3060 worktree were not staged.

## Verification evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over both product files
  and the focused test: **PASS**.
- Dependency-free AST parse over the three changed files: **PASS**.
- Focused dependency-free GDC guard harness over all eight guarded
  attention/FLA/Mamba files: **PASS**, 8 files × 4 cases. Covered unsupported
  architecture, missing intrinsic, both real intrinsics, and preservation of
  an existing intrinsic while filling the missing one.
- `git diff --check`: **PASS**.
- Commit scope check: **PASS**; `git diff-tree` for `7224d14629` lists exactly
  the three authorized files above.
- `python3 -m pytest -q test/registered/kernels/test_gdc_guard.py`:
  **BLOCKED before collection** because `/usr/bin/python3` has no `pytest`.
- No CUDA GPU runtime, remote SM86 smoke, or live SM90 run was available in
  this coder environment; no such evidence is claimed.

status: done
artifacts: commit `7224d14629`; this report
evidence: py_compile, AST parse, focused dependency-free guard harness, diff checks, exact commit-scope check
summary: Qwen3.5 fused-QK and immediate full-attention decode GDC sites are AST-safe on SM86 while preserving real-GDC dispatch on supported SM90+ environments
followups: tester should rerun the remote RTX3060 Qwen3.5 smoke and, when available, an SM90 runtime check; pytest should be run in the project test environment
open_issues: local pytest unavailable; no live GPU or remote runtime evidence in this invocation
