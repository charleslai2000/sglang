# SCOUT-20260908-3060-CODE-SURVEY

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: D3060-CODE-SURVEY-003
orchestration_epoch: 20260908-3060
role: scout

## Scope and baseline

- Surveyed repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- Branch observed: `3060-12g-qwen35-4b`.
- HEAD observed: `d49214e59228a555dc9f878426928a8a628d8848`.
- `git status --short --branch` reported only the branch line; no worktree changes were observed.
- Repository-local guidance found and read: `docs/AGENTS.md`. No runtime-specific `AGENTS.md` exists in this checkout.
- Task memory read: phase-2 `context.md`, `plan.md`, `ledger.md`, and the prior 3060 source/runtime survey reports relevant to this dispatch.
- No remote command, GPU/runtime command, model download, benchmark run, branch operation, or source modification was performed.

## P0-P5 source/CLI surfaces

The memory/checkout does not contain one authoritative document defining the labels “P0-P5” for this 3060 plan. The mapping below therefore names the observed implementation/test surfaces by their repository symbols and filenames; it does not infer acceptance criteria or propose fixes.

### P0 — trace, build/durability, residency barrier evidence

Confirmed product surfaces:

- `python/sglang/srt/mem_cache/trace_context.py`: trace-context data and event emission support added in the HEAD commit.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`: unified cache lifecycle, build-complete/durability/residency integration, HiCache event checks, and trace emission call sites. The file is a large HEAD-commit change (`2748` added lines).
- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`: hybrid cache controller and component/tier readiness integration.
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`: Mamba component durability/transfer participation.

Confirmed focused vehicles/tests:

- `3090-dev/p0_session_barrier_vehicle.py`: client/evidence vehicle for session build, durability barrier, residency barrier, warm request, and exact identity joins.
- `3090-dev/test_p0_residency_barrier_emitter.py`: focused emitter tests, including KV/Mamba component and device/host tier cases, queue/barrier checks, final-token/no-next-request cases, and invalid trace-context cases.
- `3090-dev/test_p0_trace_context_v4.py`: focused trace-context V4.3 fixture/checks.

The P0 helper files and product cache/trace files were introduced or materially changed by HEAD; their presence is confirmed, but this survey did not execute them.

### P1 — HiCache storage, restore, and scheduling path

Confirmed CLI definitions in `python/sglang/srt/server_args.py`:

- `--enable-hierarchical-cache` (lines 2739-2740).
- `--hicache-host-memory-mode {cache,buffer_only}` (2742-2749).
- `--hicache-ratio` and `--hicache-size` (2750-2759).
- `--hicache-write-policy {write_back,write_through,write_through_selective}` (2760-2767).
- `--hicache-io-backend {direct,kernel,kernel_ascend}` and `--hicache-mem-layout` (2768-2789).
- `--hicache-storage-backend` with built-in choices including `file`, `extent`, `sim`, `mooncake`, `hf3fs`, `nixl`, `aibrix`, `dynamic`, `simm`, `mori`, and `shm` (2790-2810).
- `--hicache-storage-prefetch-policy {best_effort,wait_complete,timeout}`, backend extra config, retry poll/max attempts, and restore wait timeout (2811-2852).
- `--hicache-restore-backup-park` and adjacent restore controls (2853 onward).

Confirmed runtime surfaces:

- `python/sglang/srt/mem_cache/hicache_storage.py`: `HiCacheStorageConfig`, storage configuration/attachment, transfer and storage backend interfaces.
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: extent L3 backend present in this checkout.
- `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`: extent allocation/recycle path.
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`: restore state/wait-capacity machinery.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`: prefetch/load-back, storage transfer, and unified cache admission path.
- `python/sglang/srt/managers/schedule_policy.py`, `scheduler.py`, and `scheduler_components/metrics_reporter.py`: scheduling/checking and observable restore-related call paths referenced by the phase-2 plan.

Confirmed HTTP management surfaces in `python/sglang/srt/entrypoints/http_server.py`:

- `POST /hicache/storage-backend/clear`.
- `PUT /hicache/storage-backend` with `hicache_storage_backend`, extra config, prefetch policy, and write policy fields.
- `DELETE /hicache/storage-backend`.
- `GET /hicache/storage-backend`.

### P2 — Mamba/linear-attention cache and checkpoint hooks

Confirmed CLI definitions in `python/sglang/srt/server_args.py`:

- `--max-mamba-cache-size` (2604-2606).
- `--mamba-ssm-dtype {float32,bfloat16,float16}` (2607-2614).
- `--mamba-max-states-per-path` (2615-2622).
- `--mamba-radix-cache-strategy {auto,no_buffer,extra_buffer,extra_buffer_lazy}` (2641-2649).
- `--mamba-track-interval` (2661-2663).
- `--enable-int8-mamba-checkpoint` and `--int8-mamba-ckpt-size` (2664-2673).
- Linear-attention backend selectors and ReplaySSM flags are in the same section (2674-2734).

Confirmed validation/normalization hooks:

- `ServerArgs._handle_mamba_backend` validates Mamba backend and stochastic-rounding constraints (around lines 6992 onward).
- `ServerArgs._handle_int8_mamba_checkpoint` validates the built-in Mamba checkpoint mode (around lines 7047 onward).
- `ServerArgs._handle_mamba_radix_cache` and related validators are around lines 6599 onward.

Confirmed implementation files:

- `python/sglang/srt/mem_cache/mamba_checkpoint_pool.py`: checkpoint-pool implementation.
- `python/sglang/srt/mem_cache/mamba_radix_cache.py`, `allocator/mamba.py`, `pool_host/mamba.py`, and `mamba_slot_fused.py`: Mamba cache allocation/radix/host-pool surfaces.
- `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`: unified-cache Mamba component and HiCache transfer construction.
- `python/sglang/srt/configs/mamba_utils.py`, `srt/layers/attention/mamba/*`, and `kernels/ops/mamba/*`: model/config and kernel hooks.
- `python/sglang/kernels/jit/csrc/kvcacheio/transfer_mamba.cuh`, `python/sglang/kernels/aot/python/sgl_kernel/mamba.py`, and `python/sglang/kernels/ops/mamba/transfer_mamba.py`: transfer/kernel integration points.

### P3 — capacity, warm/branch pressure, and analysis helpers

Confirmed helpers:

- `3090-dev/gate3_capacity.py`: threaded multi-agent cold-history plus warm-turn driver; CLI includes `--agents`, `--tier`, `--warm-repeats`, `--cold-max-new`, `--warm-max-new`, `--stagger`, `--client-max-time`, `--snapshot-interval`, `--evidence-dir`, `--dry-run`, and `--served` (around lines 325-344). It samples `/metrics` before/after requests and writes per-agent turn rows.
- `3090-dev/gate3_parked.py`: parked-session fleet vehicle.
- `3090-dev/gate3_parked_analyze.py`: parked-run metrics/reducer.
- `3090-dev/test_capacity_model_unit.py`: capacity-model focused tests.
- `3090-dev/test_p3_warmtree_hol.py`: P3 warm-tree/head-of-line focused test.
- `3090-dev/rh_durability_driver.py` and `rh_durability_analyze.py`: Ready-Horizon durability driver/reducer.

The capacity driver’s documented example uses `SGLANG_PORT=8024`, `MODEL_PATH=/root/models/Qwen3.5-9B-w4a16`, and a 55K tier; these are reference defaults to avoid carrying over unchanged to 3060.

### P4 — quantization and backend selection

Confirmed server CLI surface:

- `python/sglang/srt/server_args.py` defines `quantization` with `QUANTIZATION_CHOICES` (614-622), `dtype` (596-613), `quantization_param_path` (623-635), and `kv_cache_dtype` beginning at 636.
- The server args file also contains backend validation and platform/SM checks, including Marlin-related validation (`_validate_experimental_sgl_marlin`) and KV/quantization compatibility checks.

Confirmed quantization registry/hooks:

- `python/sglang/srt/layers/quantization/__init__.py`: `BASE_QUANTIZATION_METHODS` at line 79, with `awq` at 90, `gptq` at 94, `gptq_marlin` at 95; `QUANTIZATION_METHODS` at 159 and `get_quantization_config` at 162.
- `python/sglang/srt/layers/quantization/awq/awq.py`: `AWQConfig`, `AWQMarlinConfig`, `get_quant_method`, and AWQ linear/MoE methods.
- `python/sglang/srt/layers/quantization/gptq/*`: GPTQ schemes, including `gptq_marlin.py` and `gptq_moe.py`.
- `python/sglang/srt/layers/quantization/marlin_utils.py`: `MarlinConfig` at 626, Marlin method at 731, and user-quant conversion logic around 706-718.
- `python/sglang/srt/layers/linear.py`: quant method selection, weight creation, and `apply` call path; it explicitly contains Marlin special cases.
- `python/sglang/srt/model_loader/utils.py`: model-loader quantization format handling includes `gptq_marlin` (line 211).
- Kernel implementations/tests are present under `python/sglang/kernels/jit/csrc/gemm/marlin`, `python/sglang/kernels/aot/csrc/gemm/gptq`, `python/sglang/kernels/aot/tests/test_gptq_kernel.py`, and `python/sglang/kernels/aot/tests/test_awq_dequant.py`.

No runtime proof was collected here that a particular Qwen3.5-4B checkpoint selects a particular backend on RTX 3060; that requires an authorized environment/model check.

### P5 — benchmark and measurement helpers

Confirmed general HiCache benchmark entrypoints:

- `benchmark/hicache/README.md`: documented server forms for ordinary radix cache and `--enable-hierarchical-cache`, plus benchmark commands.
- `benchmark/hicache/bench_multiturn.py`: concurrent multi-turn request driver; accepts model path, host/port, client/request controls, and reports TTFT, latency, ITL, prompt/output lengths, cached tokens, and per-round metrics.
- `benchmark/hicache/bench_warm_cache.py`: warm-cache request helper.
- `benchmark/hicache/bench_hicache_write_back.py`: write-back benchmark helper.
- `benchmark/hicache/bench_long_context.py` and `bench_mix.py`: long-context/mixed workload helpers.
- `benchmark/hicache/bench_serving.py`: dataset-serving driver with model/tokenizer, host/port, request-rate, concurrency, multiturn/shared-prefix, and output-file controls.
- `benchmark/hicache/perf.py` and `data_processing.py`: performance/data support.

The 3090-specific experiment helpers are separate from the general benchmark directory:

- `3090-dev/gate2-run.sh`: launch/health/metrics/driver/cleanup wrapper; accepts `--tag`, `--agents`, `--turns`, and `--smoke`.
- `3090-dev/gate2-run2.sh`: two-phase write/read wrapper; accepts `--tag`, `--agents`, `--write-turns`, and `--read-turns`.
- `3090-dev/direct-launch-gate3-parked.sh`: direct `python3 -m sglang.launch_server` command with model path, served name, TP, KV dtype, Mamba settings, HiCache extent settings, metrics, port, and optional Ready Horizon.

## 3090-only assumptions to avoid

These are explicit repository/helper assumptions, not 3060 measurements:

- `3090-dev/direct-launch-gate3-parked.sh` defaults to `/root/models/Qwen3.5-9B-w4a16`, served name `qwen3.5-9b-gptq`, `--tp-size 1`, `--kv-cache-dtype fp8_e4m3`, `--mamba-radix-cache-strategy extra_buffer`, `--mamba-ssm-dtype float32`, `--mem-fraction-static 0.92`, `--max-running-requests 8`, `--cuda-graph-max-bs 8`, Mamba ratio `0.42`, extent backend, 120G default L3 size, 10G minimum free space, HiCache ratio `1.3`, and `--max-total-tokens 600000` (lines 29-60).
- `3090-dev/gate2-run.sh` documents a 3090 baseline of max total 65,536 tokens, auto-fit Mamba cache, extra-buffer strategy, and a full host pool (lines 8-12); it hardcodes `/root`, `/data/l3`, port 8024, the `sglang-patch` environment, and 3090-era helper paths.
- `3090-dev/gate2-run2.sh` repeats the `/root`, `/data/l3`, port 8024, `sglang-patch`, `direct-launch-gate1.sh`, and 3090 evidence-path assumptions.
- `3090-dev/gate3_capacity.py` documents 4/6/8-agent and 50K/55K/80K history tiers, with the example using Qwen3.5-9B-w4a16. These are not evidence that the same workload fits a 12G card.
- The general benchmark README examples use unrelated larger models (for example Qwen2.5-14B and Mistral-7B); they document interfaces, not 3060 compatibility.
- `--kv-cache-dtype fp8_e4m3`, CUDA-graph batch limits, Mamba `extra_buffer`, and Marlin/GPTQ fast paths have platform/backend validation in `server_args.py`; presence of a flag or source file does not establish RTX 3060 runtime support.
- The HEAD commit is a 3090 experimental snapshot: its changed files include P0 vehicles/tests plus `unified_radix_cache.py`, extent backend files, trace context, and Mamba component changes. Do not treat its 3090 evidence files or review gates as fresh 3060 evidence.

## Confirmed command forms (not executed)

The following command forms are present in tracked files or documentation and were recorded only as survey evidence:

```bash
python -m sglang.launch_server --model-path MODEL_PATH --enable-hierarchical-cache
python benchmark/hicache/bench_multiturn.py --model-path MODEL_PATH
python benchmark/hicache/bench_serving.py --model MODEL --backend sglang --port PORT ...
python 3090-dev/gate3_capacity.py --dry-run --agents 4 --tier 55k
SGLANG_PORT=8024 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 python 3090-dev/gate3_capacity.py --agents 6 --tier 55k --evidence-dir /root/evidence-capacity-64k-c6
```

The last two forms are 3090/reference forms and must not be treated as 3060 launch instructions without a fresh authorized plan.

## Search limits and unknowns

- Search was limited to the specified checkout’s tracked source/helpers and the designated phase-2 memory files. Unrelated workspaces, remote hosts, installed packages, model directories, live processes, and private data were not scanned.
- No model config/checkpoint was inspected and no import, build, server, GPU, or benchmark command was run.
- The exact P0-P5 phase contract for the 3060 plan is not present in the inspected repository/memory inputs; the report therefore groups observed surfaces by function and preserves the naming ambiguity.
- Actual RTX 3060 SM86 compatibility, available VRAM, CUDA/Triton/FlashInfer/Marlin availability, Qwen3.5-4B checkpoint format, and runtime backend selection remain unknown from this read-only source survey.
- The branch points to the same HEAD as `3090-24g-opt` and the snapshot branch; branch identity alone does not prove a 3060-specific source delta.

## Artifacts and evidence

- Report artifact: this file.
- Baseline evidence: `git status --short --branch`, `git branch --show-current`, `git log -1 --oneline`, and `git show --stat HEAD`.
- Source evidence: line-targeted `rg` searches in `python/sglang/srt/server_args.py`, quantization registry/loader files, HiCache/Mamba files, `3090-dev` helpers, and `benchmark/hicache` files.

## Summary

The checkout has complete source-level launch argument plumbing for quantization, HiCache, Mamba, storage backends, and metrics, plus both general HiCache benchmarks and 3090-specific P0-P3 experiment vehicles. The most important 3060 planning constraint visible in code is that the available launch/driver defaults are 3090/24G/9B assumptions; they must be treated as reference surfaces only. The exact P0-P5 phase labels remain an open coordination input.

## Followups

- A planning/architecture owner can use the paths and line anchors above to compare 3060 runtime prerequisites against the 3090 helper defaults.
- Any runtime compatibility, model-load, benchmark, or branch-change work requires a fresh Task ID and explicit dispatch.

## Open issues

- Exact 3060 P0-P5 contract not present in the surveyed inputs.
- Runtime availability/compatibility of quantization and Mamba backends on RTX 3060 is unverified.
- 3090 hardcoded paths, model, memory sizes, and concurrency values require target-specific replacement/validation before use.

Extra work requires a new Task ID.
