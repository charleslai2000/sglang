# G3-IQ3-LIVE-PATH-CHECK-20260908

Status: done

## Scope and limits

Read-only check of the local checkout and the explicitly authorized host
`175.155.64.171:22109`. The live inspection was limited to deployed source and
service PID `503601` on port `8035`; no workload, downloads, process changes,
instrumentation, or source edits were performed. Raw command output is in
`raw/g3-iq3-live-path-check-20260908/`.

## Identity

- Local checkout commit: `dac6db1ebabdb80209b757fd063cf53e05c091e7`.
- Local checkout is dirty, but the six tracked modifications are in benchmark,
  OpenAI serving/protocol, sampling, and its unit test; no GGUF source or GGUF
  CUDA kernel modification is present in `git status`.
- `/data/sglang-qwen35` has no `.git` metadata, so a deployed Git commit cannot
  be recovered from that directory. Its source-file SHA-256 exactly matches the
  local files checked here:
  - `python/sglang/srt/layers/quantization/gguf.py`:
    `9f7b6cb77c64401517d1580b82503de02a7c5c90b6effcc867607abc72a5518d`
  - `python/sglang/kernels/aot/csrc/quantization/gguf/gguf_kernel.cu`:
    `9905943cd6987a139bf75753b0d2480bcfc5396f8cc9f0fe08d224451f098f32`
- Live process command is the frozen v1 launch at PID 503601, using
  `/data/sglang-qwen35-env/bin/python`, model IQ3_S GGUF, port 8035, and the
  frozen parser/KV/Mamba/template flags. Its RSS was 1,620,008 kB at inspection.

## Source path findings

The deployed `gguf.py` is byte-identical to the local copy. In
`fused_mul_mat_gguf` (lines 192--220):

- `IMATRIX_QUANT_TYPES` includes IQ3_S (enum listing lines 165--173).
- `MMVQ_QUANT_TYPES` includes the imatrix types; `MMQ_QUANT_TYPES` is only
  standard plus K-quants (lines 148--180).
- For imatrix types, `mmvq_safe` is 8 when `qweight.shape[0] > 5120`, otherwise
  16. For an output-row batch at or below that limit, the selected call is
  `ggml_mul_mat_vec_a8`; above it, IQ3_S is not in MMQ and reaches the
  `DEQUANT_TYPES` fallback (`ggml_dequantize` followed by `x @ weight.T`). The
  exact threshold depends on the actual qweight output-row shape.

In `GGUFLinearMethod._create_padded_weight_param` (lines 417--453), multiple
shards are materialized once into one padded tensor during loading; the source
then clears `qweight.data_container`. In `GGUFLinearMethod.apply` (lines
455--481), each sharded forward iteration passes:

```python
qweight[start:end, :offset].contiguous()
```

to `fused_mul_mat_gguf`. Thus the claimed per-forward contiguous operation is
present in this checkout for sharded merged weights. Whether it allocates a
new tensor for every particular slice depends on that slice's contiguity and
shape; the source alone does not establish allocation frequency.

The CUDA wrapper `ggml_mul_mat_vec_a8` in `gguf_kernel.cu` lines 94--180
allocates `quant_X = torch::empty(...)` on every call, then immediately invokes
`quantize_row_q8_1_cuda(...)` before dispatching the type-specific MMVQ kernel.
Therefore the wrapper has a per-call temporary activation quantization buffer
and quantization operation. The source establishes this per wrapper invocation;
it does not by itself prove how many wrapper invocations a complete model
forward makes or whether a higher layer shares inputs.

## Loaded kernel identity

Process maps show the live service has loaded:

`/data/sglang-qwen35-env/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so`

The imported package reports `sgl_kernel 0.4.6.post1`; `nm -D` on that loaded
library exposes both `ggml_dequantize` and `ggml_mul_mat_vec_a8`. Hashes:

- `sgl_kernel/quantization/gguf.py`:
  `6c924e2261309dd8ebf92bdbef4b71a00a2d716faf7fb23656011dbca7f35fce`
- `sgl_kernel/sm100/common_ops.abi3.so`:
  `7107039cd6d78c62cbb96bfa677cfdbbd4ae355c50e1ce9481590e033f61feff`

The loaded Python runtime reports `sglang 0.5.10.dev0`, with the source module
resolved from `/data/sglang-qwen35/python/sglang/__init__.py`.

## Conclusion

The requested source/runtime identity check is complete. The two concrete
mechanisms are confirmed in the deployed/local source: per-sharded-forward
`.contiguous()` at `gguf.py:473`, and per-wrapper-call Q8_1 activation
quantization at `gguf_kernel.cu:107--109`. The IQ3_S dispatch is conditionally
MMVQ for small enough `x.shape[0]`, with the exact source threshold determined
by qweight output rows; larger shapes use the dequantize fallback. No claim is
made here about measured allocation rate, end-to-end bottleneck share, or
performance improvement.

## Open issues

1. Deployed Git commit/dirty state is unavailable because `/data/sglang-qwen35`
   is a source export without `.git` metadata.
2. Runtime shard shapes and per-forward allocation counts were not obtained
   without loading/altering the model or adding instrumentation; the report
   intentionally does not infer them.
