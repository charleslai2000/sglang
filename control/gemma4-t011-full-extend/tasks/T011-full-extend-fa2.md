# T011 — Full Extend FA2 qualification and conditional integration

Status: DONE

## Work area
`python/sglang/srt/layers/attention/`, `python/sglang/kernels/ops/attention/`, `control/gemma4-t011-full-extend/`, durable run artifacts under `/data/sglang-hicache/gemma4/runs/`.

## Objective
At frozen baseline `c102ccbc5cfd17b510f896b23107204daf5ed0d7` / production source `a76206a5fb`, qualify and, only if effective, integrate the user-specified FlashInfer FA2 Paged Prefix + Ragged Extend + MergeState path for Full Attention Extend with head_dim=512. No substitute algorithm.

## Inputs
- Existing trace: `/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof/nsys/gemma4.sqlite`.
- Prior evidence/report: `control/gemma4-rtx3090-throughput-scheduling/runs/T010-GPU-HARDWARE-PROFILING-20261127.md`, `runs/T011-ATTENTION-REVIEW.md`.
- Reference path: `python/sglang/srt/layers/attention/flashinfer_backend.py`; FlashInfer FA2 `attention/prefill.cuh`, paged/ragged wrappers and `cascade.merge_state`.
- Fixed shapes: (new,prefix) = (1024,7168), (4096,12288), (4096,28672); SM86, BF16 Q, FP8 E5M2 prefix KV, head_dim512, page_size1, actual GQA geometry.

## Completion
First correlate trace grid `(1,8,128)` to actual layer/type and source-derived head_dim/BLOCK_M/BLOCK_N/context, without full recapture. Then isolate supported FlashInfer APIs and measure complete plan + Attention + merge cost against current complete Triton Extend for all three shapes, including memory overhead. If unsupported or no clear net benefit, stop the candidate with evidence and no production edit. If it passes, integrate only the Full Extend route using existing pool/metadata/owner mapping; preserve FP8 prefix+descale, original-precision new K/V+causal mask, Shared-KV semantics, LSE log-base and empty Prefix. Verify outputs/LSE against FP32 oracle, then one original C-8 L1-only acceptance and full three-tier restore. Report operator speedup, actual memory cost, end-to-end outcome and source SHA; commit/push authorized T011 changes.

## Result
**Applicability STOP / DONE.** The exact T010 production config uses Full `head_dim=256`, 8 query heads / 2 KV heads; no Full layer has dimension 512. Full layer IDs are `[5,11,17,23,29,35,41]`, with shared Full suffix layers 35/41 mapping to owner 23. On SM86 the frozen Triton code selects `BLOCK_M/N=64/64` at Lq=256 and 8 warps. The existing trace `(1,8,128)` row is 63 calls, 2708.544 ms total; DB has no layer/type/head-dim/context identity. For the known geometry its grid implies 8192 Q rows, but cannot be attributed to a layer or documented controlled phase from SQLite alone. Full evidence and decision: `runs/T011-FULL-EXTEND-FA2-QUALIFICATION.md`.

The fixed 512-dim experiment would be synthetic and would not qualify or optimize this frozen production checkpoint. No GPU experiment, production edit, oracle, C-8 acceptance, or three-tier restore was run; no speedup/memory/end-to-end claim is made. Installed inventory only: FlashInfer 0.6.17, torch 2.13.0+cu129, device SM86. Source remains `c102ccbc5c` / production `a76206a5fb`. Existing unrelated Attention Review remains unstaged.

## Remaining
No work within the stated `head_dim=512` scope. Further optimization of this checkpoint requires a user-directed scope change to actual Full `head_dim=256`, or a different frozen checkpoint with Full `head_dim=512`; no alternative was selected here.
