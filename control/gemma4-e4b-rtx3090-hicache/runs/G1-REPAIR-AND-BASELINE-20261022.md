# G1 repair and baseline status — 2026-10-22

## N=512/514 BF16 vs pinned HF (post-RoPE)
PASS: capture association and identity. Actual service artifacts from `/data/sglang-hicache/gemma4/runs/20261022T172926Z-e5m2-swa-boundary/`; checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, weights SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. No Radix prefix reuse; exact frozen request IDs; EXTEND, batch 1, `extend_prefix_lens=[0]`, full 512/514 token rows, positions 1..N. HF oracle logits are from same pinned checkpoint, exact input hash/positions, artifacts `.../20261022T065916Z-e5m2-swa-boundary/oracle-n{N}.pt`. The service request was re-executed on the committed RoPE baseline; the run used only diagnostic PLE capture changes afterward.

Frozen applicable BF16 full-logit guard is max abs <=.5, mean abs <=.1, top-10 ID set exact, greedy exact (`runs/G1-NUMERICAL-EVIDENCE.md`; originally frozen for short-prefill). Long-context extension is informative, not an independently approved new tolerance.

| N | RID / Forward UUID | max abs | mean abs | rel L2 | Top-10 exact | Greedy service/HF | Guard |
|---:|---|---:|---:|---:|:---:|---|---|
| 512 | `bad5a4e44c2a4ca780be065575f9f348` / `e3356f1f3cfd4c45a7f2ed440152c1a9` | 3.06548 | .504850 | .209645 | No | 107 / 236761 | FAILED |
| 514 | `9fc02e7ae2d14f6cba14b48362a875dd` / `e154f270660c4b83a79dfbf467aa9d0a` | 2.92209 | 1.350244 | .259888 | No | 236761 / 527 | FAILED |

The complete 262144-vocabulary comparisons are direct measured outputs. N512/514 differ materially; the earlier anomaly does not disappear. Do not keep expanding PLE diagnostics: no model math change is justified yet because the attempted HF PLE full-layer replay did not produce a valid same-boundary operation comparison (see below).

## PLE capture status and exact selection correction
N514 Forward `e154f270660c4b83a79dfbf467aa9d0a`, RID above, now has `forward.<UUID>.ple.17` with shape `[514,256]`, EXTEND, seq len 514, prefix0, IDs/positions and model identity bound to the manifest. N512 Forward `e3356f1f3cfd4c45a7f2ed440152c1a9`, RID above, similarly has `[512,256]`. The unrelated 271 rows were a different valid request/Forward selected by an unbounded glob; Scheduler did not split N514. The attempted HF PLE replay tools are **NOT VERIFIED**: an execution failed on input tensor shape/record-field handling; no numerical conclusion from that attempted replay. RoPE operator test remains PASS (2 tests).

The capture implementation itself works in the locked real service; compile and source-level checks pass. One startup capture attempt failed because it ran during graph warmup without request UUID; fixed by restricting capture to UUID-bound EXTEND. That failed startup is not numerical evidence.

## E5M2, API, G32/C16
Post-RoPE service E5M2 vs same-prompt BF16 at N=510..514 completed, artifacts in the same run. `comparison.json` includes full-logit max/mean/RMSE/relL2 and greedy. At N513 greedy differs (E5M2 238247, BF16 204064); N512 and N514 E5M2 and BF16 share greedy but **both BF16 results fail HF guard above**. E5M2 acceptance: FAILED/NOT ACCEPTED; no frozen long-context E5M2 tolerance, no claimed Shared-KV/SWA correctness pass.

G32 prefill 1K/4K/16K/32K and C16 throughput/capacity: NOT_RUN in this session. Prior C1/C4/C8 one-shot values are not stable qualification. Decode continuation, eager/Graph numerical parity, API cancellation at GPU-resource boundary, stable concurrency, OOM/usable Full/SWA KV capacity remain NOT_RUN or previously smoke-tested only; see `G1-STATUS-20261022.md`.

## Changes and commit eligibility
- Existing committed fix remains `93704a1c5efd145d50d0d316e6b2aa81795c21e0`, pushed/remote SHA previously verified; focused RoPE test PASS.
- New opt-in PLE tensor capture in `python/sglang/srt/models/gemma4_causal.py`, PLE-aware replay changes in `capture-hf-global-attention-components.py`, runner wiring, and boundary report updates are **UNCOMMITTED / NOT ACCEPTED**. Capture works; replay comparison is not valid yet. Do not submit as validated numerical fix.
- Local tree has numerous unrelated/Falcon dirty and untracked files. No broad stage, reset, cleanup, or mixed commit was made. LSP requests timed out; fallback `py_compile`, the focused pytest (2 passed), and `git diff --check` were used. This section records the exact run and limitations rather than upgrading diagnostics to PASS.
