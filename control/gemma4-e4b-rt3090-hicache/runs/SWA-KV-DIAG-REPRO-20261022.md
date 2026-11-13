# SWA/Shared-KV retry diagnosis status — 2026-10-22

This record replaces overconfident attribution of the N=513 difference as a uniquely legal E5M2 event. The N=513 E5M2 flip is a narrow ranking perturbation, but independent lengths reveal BF16-vs-HF greedy disagreements too. No implementation defect or acceptance-level pass is proven.

## Matched service evidence

A locked RTX3090 run executed matched BF16/E5M2 full-prefix forwards at N=510..514 with all 42 residual outputs captured. The independent pinned HF BF16 oracle uses the exact same input IDs and positions 1..N. Artifacts and request identities are in `/data/sglang-hicache/gemma4/runs/20261022T065916Z-e5m2-swa-boundary/`. E5M2 is physically `torch.float8_e5m2` in full and SWA pools. At N=513, HF and service BF16 tie candidates 204064/238247 and select 204064; E5M2 selects 238247 with only .04995 global top-two margin. At N=512 service BF16 chooses 107 vs HF 236761; at N=514 service chooses 236761 vs HF 527. These facts establish unresolved numerical mismatch, not cause.

A further locked N=513 E5M2 real-service request was run at `/data/sglang-hicache/gemma4/runs/20261022T082131Z-swa-runtime-map/`. Its response RID `d0e75b0ca31b4defbd63c9ff73255026` matches manifest `forward.781bf6152b4a48e5bd3a2cf27c8dc898.manifest`: exact 513 IDs equal the frozen request, positions 1..513, EXTEND, pinned revision/hash. It successfully reproduced a real service forward, but the opt-in runtime metadata hook **did not install**: server stderr records `ModuleNotFoundError: No module named 'runtime_swa_slot_capture'`; no `runtime-state.json` exists. Therefore this run provides no slot/window/KV evidence. The failure was the external hook import path/sitecustomize setup, not a service or GPU failure. GPU returned to 0% / 1 MiB and no server remains.

## Exact-position residual localization

Detailed figures are in `SWA-BF16-LAYER-LOCALIZATION-20261022.md`. At N=512, last-token residual rel-L2 is ~.013 through layer22 and .0394 at full-attention layer23; an all-sequence localized max error appears at layer20, token index503 (max abs9.5), and layer21 (16.75). At N=514, last-token error grows from .0206 at layer17 to .0806 at layer23, then remains elevated through shared layers; service reverses HF's 527-vs-236761 order. Residual taps do not determine whether arithmetic, RoPE, attention, shared cache, MLP, or PLE is responsible. Capture normalized/RoPE Q/K/V, attention output and residual/feed-forward/PLE boundaries at layers17–23 before attribution.

## RoPE check — initial suspicion disconfirmed

The raw checkpoint text config has SWA `head_dim=256`, full `global_head_dim=512`, full RoPE partial factor .25/theta 1,000,000, and SWA default theta 10,000. SGLang's `_apply_gemma4_text_attention_overrides` preserves SWA dims and sets `head_dim=512`; runtime `ModelConfig` derives `(head_dim,swa_head_dim,v_head_dim,swa_v_head_dim)=(512,256,512,256)`. `Gemma4DecoderLayer` passes 512 for full and 256 for SWA; `get_rope` applies the full factor to yield rotary_dim128 and keeps SWA rotary_dim256. This agrees with pinned Transformers. The apparent mismatch came from comparing unnormalized HF config to runtime construction; no RoPE change is justified.

## Source contract and owners

Pinned config: 42 layers, 18 shared layers start at index24, SWA window512. HF and local owner lookup agree: shared full layers29/35/41 use owner23; shared SWA layers24–28 and30–34 use owner18. `get_attention_sliding_window_size` adapts inclusive HF distance 512 to SGLang exclusive 511. `update_sliding_window_buffer` translates prefix slots through full→SWA mapping. These remain source-derived, not measured runtime mappings.

FP8 writes route through `MHATokenToKVPool._set_quantized_kv_buffer`, and Triton extend consumes cached-prefix K/V using configured layer scale factors. Shared-KV `forward_extend` reads owner cache buffers and preserves FP8 representation for kernel scale application. This is plausible source contract only; actual owner values and index identity remain uncaptured.

## Decisive next actions

1. Fix hook bootstrapping by explicitly placing the diagnostic directory in the child interpreter's import path (the current generated bootstrap only imports installer; its hook directory did not survive the server's PYTHONPATH setup). Add an import self-test before GPU launch. Ensure capture callback runs after owner write, selects the exact N=513 EXTEND (not graph replay), and records request RID, actual Gemma forward ID, raw IDs/positions, req_to_token slots, virtual and translated full/SWA slots, complete out_cache_loc, actual `window_kv_indices/indptr/offsets`, owner18/23 cache locs, raw K/V dtype/samples and scale buffers. After teardown, require exact match with the ordinary Forward manifest before claiming evidence.
2. Capture layer17–23 operation boundaries on the exact N=512 and N=514 inputs; compare against pinned HF at identical positions. Identify earliest component discrepancy. Only patch after direct semantic defect proof.
3. Freeze tolerances prospectively; continue long-context/decode, E5M2-vs-BF16, graph numerical parity, server-side cancellation, concurrency, physical/logical/occupied capacity, OOM boundary and latency/TPS.

G1 remains NOT ACCEPTED. No model math has changed. Local HEAD `14b3b505b33e8d2682f673944d4c56c74949e47c` matches live `git ls-remote` for `origin/3090-gemma4-e4b-hicache`; no commit/push was made. Existing Falcon/worktree changes remain untouched.
