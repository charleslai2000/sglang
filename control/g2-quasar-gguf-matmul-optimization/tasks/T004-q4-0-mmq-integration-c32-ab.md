Status: READY
Work area: experiments

## Objective
Investigate an opt-in pinned llama.cpp Q4_0 MMQ for the frozen M32 c32 decode workload, retaining AOT as default and preserving unrelated dirty work.

## Inputs
T001–T003 evidence and pinned `ce8caa6e60a03093351d6016a818720e0d46f0fb`; frozen Run4 workload; GPU lock `/tmp/f1-r16b-gpu-exclusive.lock`.

## Completion
Either validated supported-shape Graph dispatch, full matched correctness and three paired unprofiled performance runs, or a concrete implementation blocker and disposition.

## Result
The hand-reconstructed donor TU is rejected and is not exposed in SGLang service. Pinned `ce8caa6e60a03093351d6016a818720e0d46f0fb` source review confirms Q4_0 uses Q8_1 DS4 staging, M32 J=32 config (I=128, K_vram=256, stream-K), and matching main/fixup specialization. The recent compile failure came from reduced vendor headers: `mmq.cuh` requires `ggml_cuda_mmq_load_tiles_*` from `mmq-load-tiles.cuh` and `ggml_cuda_mmq_vec_dot_*` from `mmq-vec-dot.cuh`; the attempted layout-dispatch assertion is absent from the reduced subset. Do not repair/ship this path.

Changed strategy to a thin PyTorch binding against the exact pinned `libggml-cuda.so`; source `experiments/g2-quasar-gguf-matmul-optimization/t004_backend_binding.cpp`, build outside checkout under `/data/sglang-hicache/g2-quasar-runs/t004-backend-binding-build`. Real GPU graph tests on exact T002 M32 gate/O/Q weights and inputs pass capture/replay and in-place input update. Rel-L2 vs independent Q4_0 dequantized FP32 GEMM: gate 0.53576%, O 0.53753%, Q 0.53225%; O uses corrected T003 input SHA `38b42e7f…de6a9700`. New direct pointer assertions prove `ggml_tensor::data == qweight.data_ptr()` for all shapes; weights are neither duplicated nor copied per replay. Full captured graph-node/Nsight evidence is in `experiments/g2-quasar-gguf-matmul-optimization/RESULTS-T004-GRAPH-STAGE-DIAGNOSTIC-20261113.md`. This still does not prove SGLang model graph dispatch. Service dispatch remains AOT default; Run4 c32 correctness and service A/B have not run.

The rejected hand-reconstructed donor TU remains prohibited; T004 uses the upstream pinned GGML backend rather than that kernel. No SGLang model execution/integration, Run4 correctness, or service performance validation has yet been done.

Investigation established that pinned donor Q4_0 M32 uses J=32, I=128, K_vram=256, 8-warps DP4A, stream-K. Correct launch policy must derive `ntiles_dst`, choose `nblocks = ntiles_dst` only when donor tile efficiency is >=90%, otherwise nblocks=SM count, allocate `nblocks*J*I` temporary only when fixup is needed, and invoke fixup with exact pinned dimensions. The local scaffold instead used SM count unconditionally and omitted `stride_col_dst` in its fixup call. Its hand-built Q8_1 block layout was not validated against the pinned producer. The source copy is an incomplete, locally amended vendor subset, not yet approved for shipping.

The user has explicitly authorized completion of the experimental integration, GPU correctness validation and Run4 service A/B. Exact upstream `ce8caa6e60a03093351d6016a818720e0d46f0fb` was fetched and built in the existing T002 experiment directory with CUDA 12.9, SM86, forced MMQ, and internal CUDA graphs disabled. New artifact identity and the narrowly scoped borrowed-stream patch are recorded in `experiments/g2-quasar-gguf-matmul-optimization/RESULTS-T004-GRAPH-STAGE-DIAGNOSTIC-20261113.md`. Historical T002/T003 numerical and timing measurements remain valid for their measured objects/fixtures, but their backend library was built from checkout HEAD `b49650adb31f2e49a0d76113aeb1792134fd8413`, not the required pin; do not attribute those results to ce8caa6e.

## Remaining
User directive on 2026-11-14: T004 is paused; do not further edit, build, or run GPU tests for this candidate. Preserve all current dirty implementation, logs and evidence. It has not passed numerical tests (latest independent AOT run returned large incorrect values/non-finite entries; a larger shape also hit illegal memory access). It is not a W4A16 dependency. Resume only on explicit user authorization. No service/Run4/A-B/GO or commit/push has occurred.