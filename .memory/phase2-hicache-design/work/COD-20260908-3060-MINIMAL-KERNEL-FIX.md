# COD-20260908-3060-MINIMAL-KERNEL-FIX

ENTRY: ACCEPT

task_id: D3060-CODE-065
orchestration_epoch: 2026-09-08
role: coder
status: done
invocation_status: done

## Summary

Repaired the opt-in `SGL_KERNEL_MINIMAL_SM86=ON` source/registration boundary. The two
common extension targets now define `SGL_KERNEL_MINIMAL_SM86=1` only when the option is
enabled, and `common_extension.cc` conditionally omits registrations whose definitions
are removed by the minimal source filter. The default `OFF` path retains the existing
source list and registrations.

## Commit

- Branch: `3060-12g-qwen35-4b`
- Commit: `495ea91522` (`build: gate removed SM86 kernel registrations`)

## Changed files

- `python/sglang/kernels/aot/CMakeLists.txt`
  - Adds the minimal-mode compile definition to `common_ops_sm90_build` and
    `common_ops_sm100_build` only when `SGL_KERNEL_MINIMAL_SM86` is enabled.
- `python/sglang/kernels/aot/csrc/common_extension.cc`
  - Guards the 19 registrations tied to the 17 source files removed by the minimal
    source filter: MLA/concat, MoE, fused QK norm/RoPE, W4A8, sparse vertical/slash,
    and expert-specialization registrations.

## Verification evidence

- Static source-list check passed: 50 default source entries; 17 minimal removals; every
  removal is a member of the default source list.
- Static registration check passed: all 19 symbols tied to removed sources are excluded
  from the active ON registration view; no unresolved removed-symbol registration remains.
- Static OFF check passed: the default source block is unchanged and the registration
  guards are inactive unless the option is enabled.
- `git diff --check`: passed.
- Working tree after commit: clean on `3060-12g-qwen35-4b`.

No CUDA configure, compile, link/load, extension import, model load, or runtime success
is claimed. Local `cmake` is unavailable.

## Exact follow-up build command

From the target host/environment:

```bash
cd /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/kernels/aot
CMAKE_ARGS="-DSGL_KERNEL_MINIMAL_SM86=ON" make build
```

## Risks and open issues

- Minimal mode intentionally does not register the removed legacy MLA/MoE/SM90-oriented
  operations; callers that explicitly invoke those operations are outside this opt-in
  contract.
- The follow-up build/import on SM86 remains required to validate generated artifacts and
  package loading. Native SM86 code-generation coverage remains a separate issue noted by
  the independent review and was not changed here.

## Followups

- Run the exact ON build command above on the SM86 target and perform the independently
  owned build/import verification and review.

## Artifacts

- Implementation commit: `495ea91522`
- This report: `COD-20260908-3060-MINIMAL-KERNEL-FIX.md`

