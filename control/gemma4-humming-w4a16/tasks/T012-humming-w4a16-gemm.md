# T012 — Humming W4A16 GEMM qualification

Status: ACTIVE — weight/correctness gate PASS; original C-8 L1-only A/B pending

## Work area
`python/sglang/srt/layers/quantization/`, existing SGLang/vLLM Humming sources and installed package, `control/gemma4-humming-w4a16/`, C-8/T010 Nsight artifacts under `/data/sglang-hicache/gemma4/runs/`.

## Objective
Use upstream `HummingLinearMethod` and the unchanged checkpoint for full-model Humming loading, then verify real fused and Double-wide projections, logits, greedy tokens, CUDA Graph replay, and original C-8 L1-only Marlin/Humming performance and memory. Preserve FP32 accumulation, checkpoint quantization/scales, BF16 activations, workload, configuration, and KV capacity. Revert unless stable net benefit is shown.

## Inputs
Frozen commit `c4f6b50da7940ff28fefae2eb3fb0b71eb1014cc`; Gemma4 checkpoint `/data/sglang-hicache/gemma4/model`; Humming upstream dependency 0.1.12; stored C-8 and T010 Nsight SQLite traces; `control/gemma4-t011-full-extend/` closed result for preservation of T011's decision.

## Completion
Full-model correctness and original C-8 L1-only A/B establish whether Humming has a stable net benefit without capacity or correctness regression. Keep the scoped implementation only if it does; otherwise restore production. Three-tier cache verification is conditional on clearing those gates.

## Result
Prior shape compatibility and actual-weight benchmark evidence is retained in `runs/T012-SHAPE-COMPATIBILITY-AND-BENCHMARK.md`. Explicit Humming selection and Decode Graph capture work, but the current Gemma4 loader does not map checkpoint `weight_packed` tensor keys into Humming's packed-weight parameters: its full-model loader reported 271 uninitialized Text Core weights. Marlin reported no corresponding missing Text Core tensors (its 18 unloaded entries are shared K-norm parameters). Thus identical greedy tokens and graph replay do not establish Humming correctness. Evidence and artifacts are in `runs/20261127T-full-model-probes/`; paired wrapper exited 0 and released the GPU lock/port.

## User-directed continuation (2026-11-27)
Keep the CT loader, `Gemma4.load_weights` and the fused shard mapping byte-identical. Hash every Text Core CT packed weight and scale in the post-load hook *before* Marlin repack, using the working Marlin path as the reference; verify checkpoint load coverage; run the Humming arm with identical argv and an independent opt-in flag only; require item-by-item SHA256 equality; then verify the converted GEMM output and whole-model correctness, and confirm both Forward and Graph actually execute Humming. Audit code lives outside `python/` and never touches the production hot path.

## Qualification result (PASS)
Report: `runs/T012-CTLOADER-HUMMING-QUALIFICATION.md`; artifacts `runs/20261127T-ctloader-postload/`.
- 253/253 Text Core layers identical per-parameter SHA256 (`weight_packed`, `weight_scale`) between Marlin and Humming arms; same names, shapes, dtypes, element counts.
- Coverage reconciles with the checkpoint: 235 exact layers, plus 18 shared-KV `qkv_proj` layers whose checkpoint stores only `q_proj` (+6,881,280 packed words = the K/V slots; scale deltas 1:4). No Text Core WNA16 tensor in the missing-weight report in either arm.
- Humming keeps only `weight`/`weight_scale` resident; no duplicate packed matrix.
- Converted GEMM vs FP32 dequantized reference: 2.4–3.7% of output mean (Marlin 1.4–3.6%) on six real layers.
- Humming arm: 8,608 Humming GEMMs, 2,024 during decode-graph capture (253×8 buckets), 0 Marlin dispatches; separate replay check shows a `void humming<...>` kernel on replayed graph.
- Greedy: 1-token and 32-token graph probes identical; 3/4 128-token graph decodes identical (511/512 tokens). The single divergence sits where the model's own prefill and decode paths prefer different tokens in both backends; same prompt with `return_logprob` gave identical 23-token sequences in both arms.

## Remaining
Original C-8 L1-only Marlin/Humming A/B (identical frozen argv, FA2 disabled, no audit instrumentation), then three-tier validation only if there is a stable net benefit. Keep the opt-in branch only if those pass; otherwise revert it.
