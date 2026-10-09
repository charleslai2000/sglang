ENTRY: ACCEPT

Task: D3060-CODER-099, orchestration epoch 2026-09-09
Role: coder
Target branch: 3060-12g-qwen35-4b
Commit: a53e8adb98 (fix: guard remaining FLA Triton GDC sites)

summary:
Fixed the two remaining directly affected FLA GDC launch sites. Both now enable
GDC only when `is_arch_support_pdl()` is true and both Triton CUDA intrinsics
(`gdc_wait` and `gdc_launch_dependents`) are available. SM90+ behavior is
preserved; SM86/older or incomplete Triton installations use the non-GDC path.

changed_files:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/kernels/ops/attention/fla/layernorm_gated.py`
  Added the existing `_is_gdc_supported()` capability pattern and used it for
  the `_layer_norm_fwd_1pass_kernel` launch.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/kernels/ops/attention/fla/fused_kda_conv_recurrent_verify.py`
  Added the same capability guard and used it for the fused KDA verify launch.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/test/registered/kernels/test_gdc_guard.py`
  Extended the focused guard regression parametrization to both affected files.

evidence:
- `python3 -m py_compile` passed for both changed kernel sources and the focused test.
- `git diff --check` passed before and after commit.
- Equivalent AST guard check passed for all five guarded kernels, including the
  two new sites; the unsupported-architecture path returned false.
- Commit contains exactly the three authorized product/test files and reports
  `34 insertions(+), 2 deletions(-)`.
- Final target worktree is on `3060-12g-qwen35-4b` at `a53e8adb98`.
- Existing untracked `review/gates/P0-3060-RUNTIME-COMPAT.md` and `storage/`
  were preserved and not included in the commit.

open_issues:
- The focused pytest invocation was unavailable because neither `python` nor
  `pytest` is installed on PATH in this environment. No CUDA/Triton runtime was
  available for an SM86 compile test.

followups:
- Run `pytest -q test/registered/kernels/test_gdc_guard.py` in the project test
  environment and perform the SM86 CUDA Graph compile smoke test when available.

status: done
