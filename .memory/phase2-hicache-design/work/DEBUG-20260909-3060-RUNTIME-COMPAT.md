# DEBUG-20260909-3060-RUNTIME-COMPAT

Status: done (causal diagnosis only; no product, remote, 3090, ledger, context, or plan changes made).

## Scope and baselines

- Inspected source tree: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, branch `3060-12g-qwen35-4b`, clean at `032bbe7e38f2b06c0efb01bdfb5baa79532974e3`.
- The 3060 branch is five SM86/AOT loader commits ahead of its parent `d49214e592` (`3090-24g-opt`); neither runtime blocker is in those five files. The help string and allocator are inherited from the frozen 3090 lineage. The recommended edits must be committed only on the 3060 branch.
- Prior operational evidence (`OPS-20260909-3060-RUNTIME-SMOKE-DEPS.md`): remote runtime is Python 3.11.11, `torch 2.5.1+cu124`, CUDA 12.4, RTX 3060 (SM86), TP=1; launch help fails with `TypeError: %o format: an integer is required, not dict`, and bounded startup fails before model load with an import error for `_cuda_beginAllocateCurrentThreadToPool`.
- Missing evidence: the remote full traceback and exact smoke command were not included in the prior report, and this task did not access the remote host. The source-level and isolated reproductions below establish both causes independently of that missing trace.

## Blocker A — `launch_server --help`

### Causal chain and reproduction

1. `parse_args()` constructs `argparse.ArgumentParser(prog="sglang serve")` and calls `ServerArgs.add_cli_args()` at `python/sglang/srt/server_args.py:11372-11373`.
2. `ServerArgs.add_cli_args()` delegates annotated flags to `add_cli_args_from_dataclass()` (`:9982-9985`). That helper passes `Arg.help` unchanged to `parser.add_argument()` (`python/sglang/srt/arg_groups/arg_utils.py:265-275`, `:321-345`).
3. The `--hicache-writeback-reserve-gb` help text contains `67% of` at `python/sglang/srt/server_args.py:2983-3002`, specifically line 2998: `track the hicache-size split (67% of the kv pool at 8G/1.5G).`
4. During help rendering, stdlib argparse does `help_string % params`, where `params` is a dictionary. The literal substring `% o` is interpreted as old-style octal formatting, so a dict is invalid and it raises the reported `TypeError`.

Minimal independent reproduction run locally under Python 3.12:

```text
import argparse
p = argparse.ArgumentParser()
p.add_argument('--hicache-storage-reserve-bytes', default=0,
               help='Byte reserve tracks the hicache-size split (67% of the kv pool at 8G/1.5G).')
p.format_help()

... argparse.py, in _expand_help
    return self._get_help_string(action) % params
TypeError: %o format: an integer is required, not dict
```

### Competing hypotheses

- **H1: an argparse/Python version regression. Rejected.** The isolated standard-library parser reproduces the exact exception with only this literal; no SGLang imports, CUDA, or runtime options are involved.
- **H2: a different remote-only help string. Unlikely, but remote full traceback is missing.** The checked branch contains the only relevant literal `67% of` in `server_args.py`, and the exact `%o` error follows from it. The remote file revision was not independently hash-compared under this read-only task.
- **H3: a model/AWQ/kernel failure. Rejected.** Argument help rendering precedes model loading and the minimal reproduction contains none of those components.

### Smallest 3060-only fix

Change only the literal `67%` to `67%%` at `server_args.py:2998`. This preserves the rendered text (`67%`) while satisfying argparse interpolation. Add a narrow help-format regression test that builds the complete parser and calls `format_help()` (or invokes `python -m sglang.launch_server --help` in the established runtime environment). This is a behavior-preserving documentation-string escape, not a HiCache policy change.

## Blocker B — Torch 2.5.1 allocator import

### Exact API mismatch

`python/sglang/srt/distributed/device_communicators/pynccl_allocator.py:8-14` imports all of these at module import time:

```python
from torch.cuda.memory import (
    CUDAPluggableAllocator,
    _cuda_beginAllocateCurrentThreadToPool,
    _cuda_endAllocateToPool,
    _cuda_releasePool,
)
```

The installed `torch 2.5.1+cu124` does provide `CUDAPluggableAllocator`, but its `torch.cuda.memory` imports only the older pool control surface `_cuda_beginAllocateToPool` and `_cuda_endAllocateCurrentStreamToPool`; its `use_mem_pool()` uses those older calls. It does not export `_cuda_beginAllocateCurrentThreadToPool`, `_cuda_endAllocateToPool`, or `_cuda_releasePool`. PyTorch v2.8's source exports all three newer symbols and `use_mem_pool()` itself uses the same begin/end/release sequence as this SGLang allocator. Sources: [PyTorch v2.5.1 memory.py](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/cuda/memory.py) (lines 63-75 and 931-951) and [PyTorch v2.8.0 memory.py](https://raw.githubusercontent.com/pytorch/pytorch/v2.8.0/torch/cuda/memory.py) (lines 70-87 and 1107-1131).

The source history makes the reason material: commit `d48095ba537` replaced `torch.cuda.use_mem_pool()` with the new private calls to bypass the generator context manager. Thus replacing only the failed import with a use of Torch 2.5's old functions is not an equivalent compatibility repair; it restores the behavior the source explicitly abandoned and has no evidence for multi-rank symmetric memory.

### Causal chain

1. Distributed group construction lazy-imports `pynccl_allocator` unconditionally at `python/sglang/srt/distributed/parallel_state.py:423-446`, before it decides whether a group needs a PyNCCL communicator (`:453-459`). CUDA-graph setup also imports `prealloc_symmetric_memory_pool` at module scope.
2. Python resolves the `torch.cuda.memory` import before invoking `use_symmetric_memory()` or any CUDA/NCCL allocation. On Torch 2.5.1 it cannot resolve `_cuda_beginAllocateCurrentThreadToPool`, so startup stops before model load, GPU allocation, NCCL, or the SM86 AOT loader.
3. The existing operational guard is later: `use_symmetric_memory()` returns `nullcontext()` when symmetric memory is disabled, explicitly disabled by a caller, **or** `group_coordinator.world_size == 1` (`pynccl_allocator.py:325-331`). This is unreachable while the import itself fails.

### TP=1 Qwen3.5-4B result

For the recorded TP=1 smoke, symmetric-memory allocation is not needed: every symmetric-memory call is designed to short-circuit to `nullcontext()` for a group of one. Qwen3.5 itself does not alter that group-size invariant. Therefore it is safe to bypass the unavailable private APIs for this TP=1 smoke **only when no multi-rank/attention-CP/DCP/DP group uses symmetric memory**. This is a control-flow conclusion, not a claim that the model has been successfully loaded or served.

This does not make symmetric memory available on Torch 2.5.1. Any future multi-rank run with `--enable-symm-mem` must fail before attempting allocations; silently falling back to the old API is not justified.

### Smallest compatibility boundary

Keep `CUDAPluggableAllocator` as its own import (it exists in Torch 2.5.1). Resolve the three newer private controls guardedly, retaining their unavailable names and the installed `torch.__version__` rather than failing at module import. Add one internal `_require_current_thread_mempool_api()` and call it only on the path that creates/enters `SymmetricMemoryContext` (defense-in-depth: both constructor and `__enter__` are acceptable; one authoritative guard is required).

Required behavior:

| Condition | Required result |
| --- | --- |
| Torch 2.5.1; symmetric memory disabled | Module imports; ordinary TP=1 startup is unaffected by this allocator feature. |
| Torch 2.5.1; `world_size == 1`, including a truthy symmetric-memory config | `use_symmetric_memory()` remains `nullcontext()` as it does today; no private allocator API is touched. |
| Torch 2.5.1; a multi-rank operation actually enters `SymmetricMemoryContext` | Raise a deterministic `RuntimeError` naming Torch version and all missing controls, e.g. `_cuda_beginAllocateCurrentThreadToPool, _cuda_endAllocateToPool, _cuda_releasePool`; say that NCCL symmetric memory requires the current-thread MemPool API. |
| Torch with all three controls | Preserve the existing current-thread begin/end/release behavior exactly. |

Do not substitute `_cuda_beginAllocateToPool`/`_cuda_endAllocateCurrentStreamToPool`, fabricate dummy symbols, or broadly disable PyNCCL. Those alternatives either change the allocator concurrency/lifetime contract or mask an explicitly requested symmetric-memory feature.

## Upgrade-versus-patch assessment

Recommendation: **use the compatibility boundary for the 3060 TP=1 smoke; do not upgrade Torch as the first remediation.**

- The project metadata demands `torch==2.13.0` and multiple CUDA-13-side packages (`cuda-python>=13.0`, `flashinfer_python[cu13]`, `humming-kernels[cu13]`, and `nvidia-cutlass-dsl[cu13]`) at `python/pyproject.toml:26,36,38,49,82`. The remote deliberately holds `torch 2.5.1+cu124` and has an SM86 staging workaround because the installed kernel otherwise attempts an SM100 binary requiring `libnvrtc.so.13`. A Torch upgrade therefore changes much more than the three allocator controls and crosses the existing CUDA-13 prohibition.
- Official PyTorch records show 2.5.1 and 2.6.0 have CUDA-12.4 wheels ([previous versions](https://docs.pytorch.org/get-started/previous-versions/)); the newer current-thread API is present in the v2.8 source cited above. This task did **not** establish an acceptable CUDA-12.4 wheel for a release that has that API, so upgrade feasibility remains unproven.
- The remote's `sglang-kernel 0.4.6.post1` is an existing native/AOT wheel and the 3060 branch adds a native SM86 path. The source registers C++ Torch operators (`torch::` / `TORCH_LIBRARY`-style bindings), so its filename's CPython `abi3` marker is not proof of PyTorch binary compatibility. A Torch upgrade can introduce unresolved symbols, dispatch changes, or require rebuilding/revalidating the staging artifact. No remote binary inspection or rebuild was authorized here.
- The local compatibility patch is limited to an import/feature boundary and a help escape. It preserves current Torch, CUDA 12.4, the staged AOT artifact, and all 3090 files. It intentionally leaves multi-GPU symmetric memory unsupported with a clear error.

## Required follow-up ownership

`NEEDS_REROUTE: coder` under a fresh Task ID, explicitly scoped to the **3060 branch only**:

1. Escape the single argparse percent literal and add the parser-help regression test.
2. Implement the guarded current-thread MemPool API boundary in `pynccl_allocator.py`, including the four behavior cases above and a precise multi-rank error.
3. Supply the required maintenance/EXEMPT or Pattern Intake artifact under the project gate rules before implementation acceptance. This is a behavior-preserving help correction plus a runtime compatibility boundary; gate ownership decides the appropriate declaration.

Then `NEEDS_REROUTE: tester` under a separate fresh Task ID to run, on the approved 3060 environment, at least:

1. `python -m sglang.launch_server --help` (exit 0; rendered `67%` visible).
2. Import/feature tests against Torch 2.5.1 proving disabled/TP=1 paths do not touch unavailable symbols.
3. A synthetic multi-rank-enabled entry test proving the precise `RuntimeError` before allocation (no unsafe fallback).
4. The existing bounded TP=1 Qwen3.5-4B AWQ smoke, with the original CUDA 12.4 and staged SM86 setup, followed by the normal readiness/request evidence only if startup reaches it.

## Risks and open issues

- The two diagnosed blockers are necessary but not sufficient for the smoke. The prior report has already recorded a separate SM100/libnvrtc.so.13 kernel-resolution hazard when the staging override is absent; do not interpret the allocator patch as resolving it.
- The TP=1 conclusion excludes all hidden multi-rank features only if the smoke retains TP=1 and no additional CP/DP/DCP multi-rank configuration is introduced. The full prior command was unavailable, so the tester must verify those effective sizes.
- The remote's source revision, installed `torch.cuda.memory` namespace, and staged AOT binary have not been directly re-inspected in this task. The implementer/tester must capture them as immutable evidence before declaring the remote smoke unblocked.
- No claim is made about Qwen3.5 model compatibility, AWQ loading, VRAM sufficiency, HTTP readiness, generated output, or TTFT; each occurs later in the timeline and remains untested.

## Artifacts and evidence

- Prior runtime evidence: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS-20260909-3060-RUNTIME-SMOKE-DEPS.md`.
- Source evidence: `python/sglang/srt/server_args.py:2983-3002`, `python/sglang/srt/arg_groups/arg_utils.py:226-345`, `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py:8-21,185-331`, `python/sglang/srt/distributed/parallel_state.py:413-459` in the inspected branch.
- Reproduction command and standard-library traceback are recorded in the Blocker A section above.
- External API comparison: [PyTorch v2.5.1](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/cuda/memory.py), [PyTorch v2.8.0](https://raw.githubusercontent.com/pytorch/pytorch/v2.8.0/torch/cuda/memory.py), [official prior-version wheel matrix](https://docs.pytorch.org/get-started/previous-versions/).
