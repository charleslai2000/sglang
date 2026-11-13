# T004 pinned Graph diagnostic — 2026-11-13

## Exact build and runtime identity
- Official `ggml-org/llama.cpp` source commit: `ce8caa6e60a03093351d6016a818720e0d46f0fb`. Commit objects were fetched into the existing blobless donor checkout without switching or modifying its HEAD; complete `ggml` subtree extracted to the existing experiment directory. No new worktree.
- Build: CUDA 12.9.86, GNU 13.3, RTX 3090 SM86, Release, shared libs, `GGML_CUDA=ON`, `GGML_CUDA_FORCE_MMQ=ON`, `GGML_CUDA_GRAPHS=OFF`, `GGML_CUDA_FA=OFF`, NCCL/tests/examples OFF, `GGML_NATIVE=OFF`. The upstream-ignored `ggml.pc.in` packaging template was supplied locally for configure only.
- Minimal diagnostic patch in that external build adds `ggml_backend_cuda_set_external_stream()`. It stores a **borrowed** external stream on the backend context and never destroys it. No hand-reconstructed/reduced MMQ kernel is used.
- Runtime `ldd` confirms extension resolves `libggml-cuda.so.0` from `.../pinned-backend-build/src/ggml-cuda/`, not the historical `bin/` library. Backend SHA-256: `20222a9c975641b9baf4a08ca8258fe4b588e3552b6e98130bb3c7d714ba03bf`; binding SHA-256: `6ed7d6e8aaa3394aebf22c2bdf667dff884d5ff1d28379e9b52107bcb1a756cd`. Upstream `quantize.cu` matches official pinned source SHA `71cd7baab62ee1f457d23ae648c381d18b9b1327ec34832f31463b14b81895b3`.

## Stage-by-stage, same checkpoint weights and retained fixture inputs
GPU is RTX 3090. Gate and Q use recorded input SHA `062e5aa50bfe655bba777f6b26fa4b1271c266fd39cabb5fc776c6b9a39ed750`; O uses corrected recorded input SHA `38b42e7fce84f01a5b2571bd63326d8a69600b3ae8bd385df9ebd7c5de6a9700`. Weight bytes are hash-checked against the checkpoint/raw fixture. Full machine output is `/data/sglang-hicache/g2-quasar-runs/20261113T-t004-stage-diagnostic.json`.

| Shape | Eager rel-L2 vs dequant FP32 | Capture vs eager | Same-input replay | In-place updated-input rel-L2 vs new reference |
|---|---:|---:|---:|---:|
| gate `[M32,N10240,K2560]` | 0.5357637% | exact | exact | 0.5396422% |
| attention O `[M32,N2560,K2048]` | 0.5375300% | exact | exact | 0.5321988% |
| attention Q `[M32,N2048,K2560]` | 0.5322450% | exact | exact | 0.5288144% |

Outputs are finite. Capture output and each subsequent same-input replay are bitwise equal. Updating the original fixed BF16 tensor in place changes replay output and the result matches the corresponding updated-input FP32 reference to the same error scale as eager. GGML input/output allocation pointers and backend handle remain fixed during capture/replay. A direct borrowed-pointer binding check now additionally asserts the GGML Q4_0 tensor address equals the exact PyTorch loaded-weight `data_ptr()` for gate/O/Q; it passes for all three shapes. No full weight copy or per-replay weight copy occurs. An owned-copy mode remains only for harness comparison.

### Capture stream and direct CUDA Graph node evidence
The test captures on non-default PyTorch CUDA stream; inside capture, C++ queries `at::cuda::getCurrentCUDAStream()` and asserts `cudaStreamIsCapturing == Active`. `cudaStreamGetCaptureInfo` reports capture status Active (1), and the stream pointer equals the Python capture stream pointer. Each graph is created with direct async `ggml_backend_graph_compute_async` on that borrowed stream; internal GGML CUDA graphs are OFF.

CUDA Runtime API enumeration (`inspect_cuda_graph.py`) of the actual captured `cudaGraph_t` shows:
- Gate: Q8_1 quantize node grid `[32,5,1]`, block `[128,1,1]`; Q4_0 MMQ node grid `[80,1,1]`, block `[32,8,1]`, dynamic shared memory 44,160 B. No Stream-K fixup is expected for this tile-efficient gate shape.
- O: quantize `[32,4,1]` / block `[128,1,1]`; MMQ `[82,1,1]` / block `[32,8,1]` / 44,160 B; Stream-K fixup `[82,4,1]` / block `[32,4,1]`.
- Q: quantize `[32,5,1]`; MMQ `[82,1,1]` / block `[32,8,1]` / 44,160 B; Stream-K fixup `[82,4,1]` / block `[32,4,1]`.

The graph-node function addresses were cross-matched with this exact process/library’s Nsight Systems symbols. Node-level Nsight trace at `/data/sglang-hicache/g2-quasar-runs/20261113T-t004-node-graph.nsys-rep` and SQLite export `.sqlite` links non-null graphNodeIds to `quantize_mmq_q8_1<(mmq_q8_1_ds_layout)1,(bool)0>`, `mul_mat_q<(ggml_type)2,(int)32,(bool)0>`, and, for O/Q, `mul_mat_q_stream_k_fixup<(ggml_type)2,(int)32,(bool)0>`. Node IDs are grouped per shape and execute on PyTorch graph streams 18 (gate), 26 (O), 34 (Q); Nsight also records eager direct calls on backend-owned setup streams 13/143/145, distinct from the graph replay nodes. Graph-node records have launchType=1 in this Nsight export, so graph membership is established by non-null graphNodeId and matching CUDA_GRAPH_NODE_EVENTS, not by launchType alone.

The Nsight trace verifies graph-contained nodes and their grid/block/shared-memory settings; CUDA Runtime API enumeration verifies captured graph functions/parameters. The kernel pointer arguments are backend graph-captured addresses and were not fully decoded by host-symbol pointer introspection; Q4_0 tensor pointers are additionally verified equal to the caller’s loaded CUDA tensor addresses.

## Historical identity correction
T002/T003 result files and timing/numerical observations remain valid for their actual fixture/build, but the old backend binary came from source checkout HEAD `b49650adb31f2e49a0d76113aeb1792134fd8413`, not the required `ce8caa6e...`. Those historical results must not be represented as measurements from the pinned commit. This new build has a separate, recorded identity.

## Borrowed-weight pointer qualification

A follow-up variant wraps the donor's CUDA weight pointer in a non-owning GGML backend buffer and keeps the PyTorch tensor owner alive. GPU validation asserts the GGML Q4_0 tensor `data` pointer exactly equals the original loaded tensor `data_ptr()` for gate/O/Q; all assertions pass. Real capture, replay, updated-input, finite-output and dequantized-reference relative-L2 checks pass for all three shapes. This establishes the narrow zero-copy packed-weight setup seam, not full model wiring. The updated binding SHA-256 is `f7a92a1c1b335bce320ae0e23b5dea78c698188ea415a0d0b8afb6f26f543196`; updated-input test SHA-256 is `2257433f4c551f942617120fd33a2e06eb9da4f7f9d71988c32efa12994ac700`.

## Current disposition
The original numerical discrepancy is not reproduced: eager, capture, same-input replay and in-place update all pass without relaxing tolerances. Gate-stage checks are complete for gate/O/Q, including graph node membership, Nsight evidence, and direct same-pointer weight borrowing (no duplicate Q4_0 weight allocation). This is operator/backend diagnostic evidence, **not yet SGLang model execution/integration or frozen Run4 qualification**. Next: wire a narrowly opt-in SGLang M32 Q4_0 path reusing existing loaded GGUF GPU weight pointers (no full-weight duplication), keep AOT default/Q6_K unchanged, then perform actual SGLang Graph capture/replay, full frozen Run4 c32 IDs/logits/selected logprobs, and three paired unprofiled service A/B runs. No service benchmark or Run4 was run here.
