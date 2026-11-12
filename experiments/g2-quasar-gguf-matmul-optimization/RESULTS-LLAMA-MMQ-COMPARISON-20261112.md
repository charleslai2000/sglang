# QUASAR Q4_0 AOT vs llama.cpp MMQ — 2026-11-12

## Scope and selected shapes

From the existing c32 node-r2 Nsight trace, top M=32 Q4_0 grid groups by cumulative Kernel elapsed were X=320/Y=8 (3,609.528 ms/21,504 calls), X=80/Y=8 (2,362.773 ms/21,504), and X=64/Y=8 (353.900 ms/8,960). The existing `gguf-dispatch.jsonl` maps representative M32 GEMMs to `blk.0.ffn_gate.weight` [N=10,240,K=2,560], `blk.0.attn_output.weight` [N=2,560,K=2,048], and `blk.0.attn_q.weight` [N=2,048,K=2,560]. Grid rank alone is not used as a tensor-name lookup.

## Method and runtime path

- Same QUASAR GGUF Q4_0 bytes and same fixed seeded BF16 activations in both paths; llama.cpp receives the exact BF16-expanded FP32 values. Model SHA256 is `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`.
- SGLang AOT uses the existing SM86 `common_ops.abi3.so` `ggml_mul_mat_a8` (Q8_1 activation quantization plus direct Q4_0 MMQ). CUDA Events cover the full operator, 10 warmups/50 samples.
- Pinned llama.cpp donor `ce8caa6e60a03093351d6016a818720e0d46f0fb` built isolated under `/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112` with CUDA 12.9, sm86, `GGML_CUDA_FORCE_MMQ=ON`. The minimal backend harness measures graph compute including input quantization, 5 warmups/30 samples.
- Nsight Systems (`llama-mmq-kernel-r1.sqlite`) verified actual donor launches: `quantize_mmq_q8_1`, `mul_mat_q<(ggml_type)2,(int)32,(bool)0>`, and `mul_mat_q_stream_k_fixup<(ggml_type)2,(int)32,(bool)0>`. For `[M=32,N=2560,K=2048]`, MMQ grid 82×1, block 32×8, dynamic shared memory 44,160 B, 116 registers/thread; fixup grid 82×4. Quantize/MMQ/fixup each called 35 times. No tensor-core MMA claim is made. Donor's SM86 Ampere config specifies Q4_0 K tile 256, I=128, J choices 8..128, Q8_0 SRAM layout; measured M=32 chose J=32. Inner Q4_0×Q8_1 dot uses DP4A. AOT Q4_0 uses MMQ_X=4, MMQ_Y=32, 4 warps and DP4A; wrapper also quantizes activations to Q8_1.

## Results

Full call CUDA Event milliseconds, including Q8_1 activation conversion:

| Q4_0 tensor | M,N,K | SGLang AOT median (P10–P90) | llama.cpp median (P10–P90) | AOT/donor | rel-L2 | max abs | row argmax equal |
|---|---:|---:|---:|---:|---:|---:|---|
| `blk.0.ffn_gate.weight` | 32,10240,2560 | 0.20059 (0.19747–0.21798) | 0.05734 (0.05638–0.06784) | 3.50× | 1.669% | 0.11042 | No |
| `blk.0.attn_output.weight` | 32,2560,2048 | 0.06861 (0.06656–0.08090) | 0.03072 (0.02963–0.03910) | 2.23× | 1.365% | 0.16542 | Yes |
| `blk.0.attn_q.weight` | 32,2048,2560 | 0.07318 (0.07066–0.09939) | 0.03155 (0.03072–0.04198) | 2.32× | 1.532% | 0.08769 | Yes |

The numeric differences reflect distinct quantization/tiling/reduction arithmetic. Gate FFN argmax changes; this is not sufficient numerical compatibility for substituting the donor. A second run at `/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r2/` produced directionally consistent timings, but different Q/O activation seeds; only run1 is the source for the paired table. Its exact raw weights/inputs and SHA256s are recorded in `SHA256SUMS-LLAMA-MMQ-COMPARISON.txt`; complete timing/parity data and Nsight trace are under `/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1/`. Do not project isolated-kernel ratios to service performance or c32 wall-time gain.

## Decision: bounded NO-GO

The pinned donor is materially faster in isolated M32 calls, but its output is not a compatible drop-in: the largest FFN shape changes argmax and all measured shapes differ at low-percent relative L2. Integration requires port/ABI/dispatch and a correctness contract that these results do not meet. **No production kernel change, no c32 service A/B, and no Q6_K conversion.** Close this bounded comparison with NO-GO. This does not resolve the separate Q6_K transformed representation proposal, which remains subject to architecture/Owner approval.

GPU was used under `/tmp/f1-r16b-gpu-exclusive.lock`; after work it returned to 1 MiB/0%, port 31382 was clear and the lock was available. No system counter permissions were changed.
