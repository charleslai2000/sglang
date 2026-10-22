# G1 proportional RoPE repair and real-service retest — 2026-10-22

## Summary
- G1 remains ACTIVE / NOT ACCEPTED.
- Identified and repaired the proportional Global RoPE cache-layout defect while retaining SGLang's existing specialized `Gemma4RotaryEmbedding` and standard factory scaling. Global now has 64 active + 192 identity angle frequencies (256 total), 512-wide NeoX cache/apply. SWA is unchanged.
- HF Global/SWA CPU operator test: **2 passed**, bitwise-equal BF16 Q/K after apply at representative positions.
- Real locked BF16/E5M2 services ran exact frozen N=512/514 prompts. Full logits, all 42 layer outputs, Forward manifests and correct target N514 component snapshots were captured. The RoPE operator repair does not remove the N512/514 BF16-vs-HF top-token mismatches or the large logits errors. Continue diagnosis; do not treat this as end-to-end acceptance.
- Narrow RoPE code/test/report commit pushed as `93704a1c5efd145d50d0d316e6b2aa81795c21e0`; direct `git ls-remote` confirmed the Gemma branch resolves to the same SHA. This does not mark G1 accepted.

## Actual call chain and upstream comparison
Current fork was compared line-by-line with sibling upstream SGLang checkout `/home/ubuntu/workspaces/3rdparty/sglang` (SHA `3dc03616d9661a54dd74dc100883140184417440`). `factory.py` and the pre-existing `Gemma4RotaryEmbedding` class match that checkout. The model constructor previously had `rope_parameters.get("rope_type", "default")`; it now passes the actual per-layer rope type and retains the config's partial factor. The substantive numerical repair is in the specialized class's inverse-frequency layout.

Real Global construction is `head_size=512`, `rotary_dim argument=512`, `partial_rotary_factor=.25`, `rope_type=proportional`; `get_rope` scales effective rotary dimension to 128 before constructing `Gemma4RotaryEmbedding`. The class then deliberately has full `rotary_dim=512` for complete-head cache/apply, while `rope_angles=128//2=64` and `nope_angles=512//2-64=192`.

HF `_compute_proportional_rope_parameters`, using `global_head_dim=512`, emits 256 inverse frequencies: 64 entries `1 / 1_000_000 ** (arange(0,128,2)/512)` and 192 zeros. SGLang's old Gemma4 override emitted only 128 entries (64 active + 64 zeros), so the base class cache was 256 wide and `rotate_half` apply could not cover a 512-wide head. Repair: pad to the half-head count and return that 256-vector; base NeoX logic creates a `[position,512]` cos/sin cache. This precisely matches HF, including the two halves consumed by `rotate_half`. Earlier partial-factor=1 CPU evidence used a non-production parameter path and is discarded.

## Operator verification
Test file: `control/gemma4-e4b-rtx3090-hicache/runs/test_gemma4_proportional_rope.py`; `pytest` result **2 passed**. Test creates operator via the exact production factory call, compares actual HF `Gemma4TextRotaryEmbedding` and text-path `apply_rotary_pos_emb`, and asserts Q/K equality with `rtol=atol=0`.

| pathway | head / effective rotary | inv_freq entries | active / identity slots | cache | BF16 Q/K vs HF |
|---|---|---:|---:|---|---|
| Global proportional | 512 / 128 effective, full 512 NeoX apply | 256 | 64 / 192 | `[1024,512]` | bitwise, max abs 0 |
| SWA default | 256 / 256 | 128 | 128 / 0 | `[1024,256]` | bitwise, max abs 0 |

Positions include 0,1,2,17,255,511,512,513,514; Q has four heads and K two heads.

## Real GPU requests, exact IDs and references
Run: `/data/sglang-hicache/gemma4/runs/20261022T151952Z-gemma4-rope-fixed-boundaries/`; source HEAD at run `14fc12ca711e60fb0e10d5bf86588baacabdf28b`; checkpoint SHA `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Exclusive GPU lock held, separate BF16/E5M2 services, graphs explicitly disabled, no radix prefix reuse, identical frozen request token arrays, `max_tokens=1`. All requests have actual RID-bound EXTEND manifests, 42 layer outputs, pre/final norm and full-vocabulary logits. Post-run services were terminated; GPU idle 1 MiB, 0%.

HF references regenerated from same official checkpoint with exact prompt IDs and positions 1..N: `/data/sglang-hicache/gemma4/runs/20261022T140849Z-gemma4-proportional-rope-n514-rerun/hf-oracle/oracle-n{512,514}.pt`. Response RID selects the exact manifest; token IDs/positions match.

| N | KV | service greedy | HF greedy | max abs | mean abs | RMSE | rel-L2 | layer 17 rel-L2 | layer 23 rel-L2 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 512 | BF16 | 107 | 236761 | 3.0655 | .50485 | .63452 | .20965 | .01026 | .01498 |
| 512 | E5M2 | 107 | 236761 | 2.8524 | .48184 | .60034 | .19835 | .01026 | .01498 |
| 514 | BF16 | 236761 | 527 | 2.9221 | 1.35024 | 1.39673 | .25989 | .01457 | .05635 |
| 514 | E5M2 | 236761 | 527 | 4.0161 | 1.69381 | 1.75454 | .32647 | .01457 | .05635 |

N512 service top two are 107/236761 while HF ranks 236761/107; N514 service ranks 236761/527 while HF ranks 527/236761. Thus the fixed operator/cache RoPE repair is verified, but long-context end-to-end divergence is not eliminated. Full layer curves show N514 residual increasing after layer17 and particularly layer23; N512 final-token residual remains low through layer23. Do not infer that RoPE is the sole cause or that 2% residual markers are acceptance criteria.

### Capture-hook verification
The service process loaded the external sitecustomize hook and generated component files. Target N514 BF16 request RID `d8f9e8caadf3429b9e1d01252f59b097`, EXTEND Forward `6f6f98e053c74821ab19562095b56aa8`, is bound to exactly 514 prompt tokens. Its target layer17 files include `attention_norm_input`, Q/K/V, `attention_output`, and `decoder_layer_output`; all have `forward_mode=EXTEND`, `extend_seq_lens=[514]`, and 514 aligned token/position rows. A later Decode is a different UUID and is excluded. Target N512 component capture did not produce a complete set yet.

The HF operation-level capture uses HF's own layer16 input and is not a same-input SGLang comparison. The 271/514 issue was an analysis selection error, not a capture defect: a prior script used an unrestricted `glob(...)[0]` and selected a separate legal 271-token request. That request has its own RID `742856567e6d4d43b9c488c731922f6c`, Forward UUID `67ba76e8c3a94cf2a6f2c2ae994d0ee5`, EXTEND, `extend_seq_lens=[271]`, `extend_prefix_lens=[0]`, positions 1..271; the scheduler log says `#new-token:271`. The target N514 request has distinct RID `d8f9e8caadf3429b9e1d01252f59b097`, Forward UUID `6f6f98e053c74821ab19562095b56aa8`, EXTEND 514, prefix0, range [0,514], and all manifest/layer/component arrays have 514 rows. No chunked prefill is indicated (`chunked_prefill_size=2048`, `enable_dynamic_chunking=False`, request size514); the 271 Forward is not part of that request. Its actual same-Forward layer16 output is exactly equal to layer17 `attention_norm_input` (max diff 0). A new `capture-hf-global-attention-components.py` verifies UUID/RID/model/range and replays the exact input via HF compressed linear modules. The first Q/K/V comparison used mismatched boundaries. Correcting replay to force HF eager attention and use the causal mask yields same-stage post-RoPE comparison: Q rel-L2 0.00138/max 0.0625, K 0.00121/max 0.00195, V 0.000144/max 0.03125. Attention-head outputs agree at rel-L2 0.00345 (max 0.046875), and exact input layernorm agrees at rel-L2 1.21e-5 (max 0.015625). A later direct HF full-layer replay omitted the precise per-layer-input (PLE) state consumed by the service; its final-output rel-L2 .3570 is therefore invalid and withdrawn. Do not infer a downstream model math defect from it. The exact same-Forward PLE input must be captured before comparing post-attention/FFN outputs. An isolated GPU fused QKV RMSNorm test matches HF formula closely but does not resolve full model behavior.

## G1 remaining
1. Capture the exact same-Forward per-layer-input/PLE state for N514; the direct HF full-layer output replay omitted this service input, so its .3570 output comparison is withdrawn as invalid. The matched post-RoPE Q/K/V and attention-head results remain valid. Then compare post-attention/FFN/PLE stages with the exact service input. N512 L23/position504 remains. The 271-row issue was a glob-selected separate legal request, not broken N514 capture. Do not change math without direct evidence; advance independent G1 validation.
2. Run explicit eager-vs-CUDA-Graph logits parity and separately finish long-context E5M2/shared-KV/SWA validation. Historical G32/C16 numbers below are unqualified single-smoke snapshots, not a baseline. The API matrix ran one round each at C1/C2/C4/C8 (16-token completions) and reported aggregate output TPS 55.61/15.41/9.61/60.70, noisy and non-monotonic; it has no G32 prefill-only benchmark, C16 resource ledger, or repeatable throughput baseline. Build and run a locked G32 prefill-only workload with fixed warmups/repetitions, exact tokens/sec and latency samples, then C16 resource/throughput stress and occupancy/memory monitoring without displacing correctness.
3. Continue model serving acceptance: stop/stream/server cancellation, concurrency, KV capacity/OOM and stable performance measurements.
2. Run post-fix CUDA Graph enabled vs eager prefill/decode numerical parity; this run disabled graphs.
3. Complete nonzero-prefix SWA mapping/owner scales, E5M2 shared-KV and long decode drift, stop/stream/server cancellation, concurrency, KV capacity/OOM and stable performance measurements.
4. RoPE fix, focused test and this evidence report are committed/pushed at `93704a1c5efd145d50d0d316e6b2aa81795c21e0` (remote SHA verified). Preserve Falcon dirty state; subsequent commits remain narrow. Keep G1 ACTIVE / NOT ACCEPTED.
