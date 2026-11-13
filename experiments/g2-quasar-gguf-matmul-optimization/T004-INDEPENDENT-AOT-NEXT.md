# T004 independent AOT operator — current blocker

## Status

The standalone AOT SM86 extension builds and registers `gguf_q4_0_llama_mmq_m32`. Real GPU smoke testing fails: random packed weights produce NaNs and wildly out-of-range values, so no correctness or graph claim is valid. Model integration, frozen Run4, A/B, commit and push remain prohibited until fixed.

## Evidence

- Build tree: `/data/sglang-hicache/g2-quasar-runs/t004-aot-build`; library: `sm86/common_ops.cpython-312-x86_64-linux-gnu.so`.
- Smoke command: `PYTHONPATH=<build>/sm86:python/sglang/kernels/aot/python python experiments/g2-quasar-gguf-matmul-optimization/test_t004_aot_mmq.py`.
- First 32x128x512 output had only 53.1% finite values. Donor/aot comparison on real fixtures is not yet run.
- Build/registration succeeded; Python syntax and `git diff --check` passed before the last include-order fixes.

## Next

1. Acquire `/tmp/f1-r16b-gpu-exclusive.lock` with `flock` for GPU runs. Compare this output against the existing validated exact-pin standalone donor extension on identical tensors to determine whether the port or test inputs are defective.
2. Audit Q8_1 quantizer layout, MMQ config (`fallback`, SRAM layout), Q4_0 packed-weight layout, and stream-K strides/dispatch against the pinned source. Do not relax finite/parity criteria.
3. Rebuild and repeat random and known-real-weight tests, then graph capture/replay and SGLang opt-in service qualification. Only then attempt frozen Run4 c32 and the preplanned three paired A/B runs.
4. Preserve current dirty tree; do not commit until gates pass.
