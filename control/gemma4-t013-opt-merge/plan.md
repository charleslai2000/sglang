# gemma4-t013-opt-merge — plan

Status: DONE. Report `runs/T013-MERGE-ACCEPTANCE.md`.

## Steps

1. **Restore, do not develop.** Install the archived T011 candidate
   (`control/gemma4-t011-full-extend/runs/archive/bf16_ragged_forward_plan_candidate.py`)
   verbatim as `python/sglang/srt/layers/attention/bf16_ragged_extend.py`, add the
   independent switch `SGLANG_FA2_RAGGED_EXTEND` (default off), and connect it with a
   minimal glue layer in `triton_backend.py`: one plan per prefill Forward on the first
   statically eligible Full layer, per-layer run, and every unsupported case falling back
   to the unchanged Triton kernel.
2. **Verify the glue on real backend code** before any load test
   (`runs/t013_fa2_glue_check.py`): plan identity across the seven Full layers, one
   conversion per KV owner reused by shared consumers, per-layer agreement with the
   production Triton kernel, and every fallback gate.
3. **Prove the path actually runs in a service** (`runs/20261127T-engage/`): the module's
   own coverage counters (plans, budget skips, owner conversions, shared reuses, maximum
   requested prefix) read from a real server that serves cache-hit prefills. This step is
   what caught the first glue defect (see the report).
4. **Score the two combinations** (`runs/20261127T-combo/`): C-8 L1-only, three-tier and
   T010 long-context cells, identical argv, the flag as the only difference; every cell
   keeps an official summary, request-hash log, GPU samples and, for the FA2 arm, its
   coverage counters. Compare TPS, extend/decode device time, TTFT, ITL, duty, KV
   capacity, peak memory, decode-graph replay counter and payload multiset.
5. **Correctness and real L3 restore** (`runs/20261127T-restore2/`): prime a fresh extent
   tier with a 10k-token prefix using `write_through`, then start a new process on the same
   extent with empty device and host tiers and require a full `disposition=RESTORE`, the
   restored prefix length, and identical greedy completions in both combinations.
6. **Decide and record**: retain both opt-ins, recommend combination B for the deployment,
   keep every default conservative, and commit with the evidence.

## Non-goals in this round

Re-running T011's C-8-only gate, changing the FA2 prefix ceiling, enabling the prefill CUDA
graph, or touching decode/SWA/cache configuration. Those stay as they were.
