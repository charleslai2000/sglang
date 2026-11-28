# T015 plan

1. **Evidence check (done).** Existing `ragged-coverage.json` counters from the T013
   C-8/three-tier/long runs and the T014 service window, plus a run-scoped diagnostic
   that records each skipped forward's request count, total prefix tokens and largest
   per-request prefix.
2. **Implementation** in `python/sglang/srt/layers/attention/bf16_ragged_extend.py`
   (group partition, per-group plans, group gather, group-major merge) and a dispatch
   branch in `triton_backend.py`. The single-group path stays byte-identical so all
   T013/T014 evidence keeps applying to it.
3. **Equivalence**: module-level check comparing the grouped path against an
   ungrouped reference plan over the same synthetic batch (2, 3 and 4 groups), and a
   real-driver check of the single-group path (must be unchanged).
4. **Net benefit on real over-budget forwards** with the T014 offline driver: the
   same production-shaped forward measured with Triton vs the sub-batched path.
5. **Service acceptance** (only if 4 is positive): C-8 L1-only, three-tier HiCache
   and the T010 long-context load, plus a real L3 restore round trip, with KV
   capacity and payload identity recorded.
