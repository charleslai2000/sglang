# T012 — CT-loader + Humming post-load qualification

**Gate: PASS.** The unchanged compressed-tensors loader and `Gemma4.load_weights` place
byte-identical packed INT4 weights and BF16 group scales on all 253 Text Core WNA16
layers in both arms; the opt-in branch converts exactly those tensors to Humming and
the model then runs Humming for real forwards and inside the replayed decode CUDA graph.
This report covers the weight/correctness gate only. Performance (original C-8 L1-only
A/B) and the conditional three-tier validation are recorded separately.

Performance gates: `T012-C8-AB-AND-TIERS.md` (C-8 L1-only +12.71%, three-tier +8.90%).

## Scope and method

Production code change is limited to an opt-in branch in
`CompressedTensorsWNA16.process_weights_after_loading` (before Marlin repack), the
dispatch in `apply_weights`, and the `SGLANG_CTWNA16_HUMMING` flag. `create_weights`,
the fused/sharded weight loader, `Gemma4.load_weights`, Marlin's default path, the
model structure and the kernels are unchanged. No `--quantization humming` override is
used anywhere in this gate; both arms run identical argv and differ only by that flag.

Audit instrumentation is qualification-only and lives outside the server:
`runs/20261127T-ctloader-postload/auditlib/sitecustomize.py` is put on `PYTHONPATH` for
the paired run. It hooks `_initialize_model`/`load_weights_and_postprocess` to map
parameter objects to their `named_parameters()` names, wraps
`CompressedTensorsWNA16.process_weights_after_loading` to hash the loaded tensors before
any conversion, and counts dispatch. Nothing in `python/` records or hashes weights.

## Weight-identity gate

Both arms, same checkpoint, same argv, 253 Text Core WNA16 layers each
(`runs/20261127T-ctloader-postload/{marlin,humming}/audit/ct-wna16-audit.jsonl`):

| check | result |
|---|---|
| layers audited (Marlin / Humming) | 253 / 253, same names |
| per-layer `weight_packed` SHA256 equal | 253 / 253 |
| per-layer `weight_scale` SHA256 equal | 253 / 253 |
| packed/scale shapes, dtypes, element counts equal | 253 / 253 |
| Text Core WNA16 tensors in "not initialized" report | none in either arm |
| parameters resident after conversion (Humming) | `weight`, `weight_scale` only |

Coverage reconciliation against the checkpoint
(`checkpoint-textcore.json`: 343 packed tensors → 253 consumed layers):
235 layers match the checkpoint's packed element count exactly. The remaining 18 are the
shared-KV attention layers 24–41, whose checkpoint carries only `q_proj` while the fused
`qkv_proj` allocates the K/V slots too: 16 layers +327,680 words and layers 29, 35, 41
+655,360 words, total +6,881,280 packed words, exactly the observed aggregate delta.
Scale deltas match the packed deltas at 1:4 (group 32 over packed INT4), no layer is
missing data, and no loaded layer is absent from the checkpoint grouping. Marlin has
identical numbers, so this is pre-existing model structure, not a Humming difference.

## Converted-GEMM gate

Six real layers, measured inside the model process after conversion against an FP32
reference dequantized from the same checkpoint words and scales, `m=8`:

| layer | Marlin max-abs | Humming max-abs | Humming rel. of output mean |
|---|---:|---:|---:|
| layers.0.self_attn.qkv_proj | 0.01476 | 0.02262 | 2.80% |
| layers.0.self_attn.o_proj | 0.01613 | 0.02238 | 2.93% |
| layers.0.mlp.gate_up_proj | 0.01410 | 0.01890 | 2.43% |
| layers.0.mlp.down_proj | 0.02196 | 0.03012 | 3.65% |
| layers.24.per_layer_projection | 0.01828 | 0.01828 | 2.62% |
| per_layer_model_projection | 0.00029 | 0.00051 | 3.27% |

Humming's error is 1.0–1.9× Marlin's on the identical reference and input; both are the
expected bf16 reduction-order envelope for a K=2560 INT4 dot product. Humming's
interleaved scale layout is therefore correct, and no requantization or scale loss is
present.

## Execution-path gate

| counter | Marlin arm | Humming arm |
|---|---:|---:|
| Humming GEMM dispatches | 0 | 8,608 |
| ... during CUDA-graph capture | 0 | 2,024 = 253 layers × 8 decode buckets |
| Marlin linear dispatches | 8,608 | 0 |
| decode graph replays | 548 | 548 |

`runs/20261127T-ctloader-postload/graph-replay-kernel-check.json` (bounded, out of the
serving path) captures a graph around a converted Humming layer and replays it under
`torch.profiler`: the replay's device kernels include `void humming<...>` (1 hit) and the
converted GEMM is 2.8% from the FP32 reference. In-run replay profiling was removed
after it triggered a CUDA launch failure in one attempt; the depth of evidence above is
what is reproducible.

## Correctness gate

| probe | result |
|---|---|
| 1-token greedy after 1024-token prefill | identical (`2009`) |
| 32-token greedy decode through the CUDA graph | identical |
| four 128-token greedy decodes (graph path) | 3/4 byte-identical, 511/512 tokens |
| next-token logits at the probe position | top-1 equal, top-10 10/10, L2 10.8%, cosine 0.9943 |

The single long-generation divergence is at token index 22 of `long-300`. It is a
decision-boundary artifact, not a conversion error: on the decode path both backends
rank the same token first (1283; Marlin top-2 = 1282 at −2.68, Humming ranks 1282 third
at −5.11), while the model's own prefill path ranks 1282 first in *both* backends
(`divergence/verdict.json`, `divergence/comparison.json`). The same prompt decoded with
`return_logprob` produced identical 23-token sequences in both backends. The model's two
execution paths disagree at this position, so a one-token difference between two INT4
kernels there is not attributable to the Humming conversion.

## Artifacts

`runs/20261127T-ctloader-postload/`: `intent.txt`, `run_pair.sh`, `probe.py`,
`compare_arms.py`, `compare.log`, `verdict.json`, `checkpoint_coverage.py`,
`checkpoint-textcore.json`, `replay_kernel_check.py`, `graph-replay-kernel-check.json`,
`divergence*`, `divergence/verdict.json`, and per-arm `server.log`, `probes.json`,
`model-info.json`, `launch-argv.txt`, `audit/ct-wna16-audit.jsonl`,
`audit/dispatch-*.json`. Raw logits vectors (1 MB per arm) were deleted after the
comparison metrics were extracted into `verdict.json`.

Run: `run_start=2026-11-27T11:06:53Z`, `run_end=2026-11-27T11:10:06Z`, wrapper exit 0.
GPU returned to idle, port 31412 released, exclusive lock free after each stage.
