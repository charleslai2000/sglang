# COD-20260908-T38C-MISSING-MAMBA-KEY

- Task / epoch: `COD-20260908-T38C-MISSING-MAMBA-KEY` / `E20260908-T38C`
- Role: coder
- Scope: S=25, RH-off, paired trace only
- Invocation status: **blocked**
- Disposition: **NEEDS_REASONING**

## Result

No new product change was made. The existing worktree changes were preserved:

- `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
  (frontier-aligned sidecar query)
- `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
  (gated paired Mamba query/write trace)
- `python/sglang/srt/mem_cache/unified_radix_cache.py` (gated write-side
  node/key correlation)

Those files were already modified when this invocation started; this
invocation did not alter them. The untracked `3090-dev/*` files were also
left untouched.

## Causal reconstruction

The remote paired trace is sufficient to classify the failure as
session-specific, but not sufficient to select a safe product fix:

1. The failed warm query tested Mamba key
   `3bb6ca491db0290ff050cd7f4f8e4110d57b290523c7c15569006e357f2ad8de` with
   `raw_kv_frontier=55145`, `tested_present=false`, `boundary=0`, and
   `final_pages=0`.
2. The complete trace contains 25 `pc_mamba_write` records, all with
   `batch_set_v2=true`. The failed key is absent from the complete Mamba write
   key set.
3. Each of the six successful full warm queries has an exact corresponding
   successful Mamba write key (`e4799060...`, `05305610...`, `8b26247e...`,
   `30f72bac...`, `53454b89...`, and `cc7d46c2...`). This rules out a generic
   extent trailing-fold or settle-time failure.
4. The current trace records `removal_recycle_hook=not_added` for the failed
   query and does not contain a keyed removal/recycle event. Therefore a
   post-write recycle is not evidenced, but it cannot be conclusively ruled
   out by this trace alone.

The remaining causal alternatives are:

- the Mamba transfer for the queried node/key was omitted before
  `batch_set_v2` (for example, no host checkpoint was available); or
- the build-side node/hash identity and the warm query's KV-chain identity
  disagreed, so the Mamba write succeeded under a different key.

Aliasing another Mamba key, weakening the all-state intersection, or treating
the KV-only prefix as Mamba-durable would be unsound and outside the frozen
Phase-2 semantics. Consequently no safe product fix is justified yet.

## Verification

- `git diff --check` — passed.
- `python3 -m py_compile` on the three authorized modified Python files —
  passed.
- Remote focused extent suite, from `/root/sglang-b1-continuity`:
  `source /root/miniconda3/bin/activate sglang-patch && python -m pytest
  test/registered/unit/mem_cache/test_extent_file_backend_unit.py -q` —
  **77 passed**, 15 environment/deprecation warnings.
- No runtime Gate A/B/C evidence is claimed.

## Exact next diagnostic

Before changing restore semantics, run one fresh S=25/RH-off retest with
paired records that correlate the failed warm request to its build node:

1. At `build_storage_backup_spec` / Mamba transfer construction, record the
   node id, final KV hash, `host_value` availability, whether a Mamba transfer
   was returned, and its exact key.
2. At the warm query, record the request/session correlation, query node/anchor
   identity, raw KV frontier, and tested Mamba key.
3. Add a keyed extent allocator recycle/removal record for Mamba component
   entries, without recording token text or state bytes.

Interpretation: no transfer for the node means a Mamba host-state lifecycle
owner must repair checkpoint availability; a transfer/write under a different
key means the hash-chain owner must repair identity; a prior successful write
under the queried key followed by removal means the extent lifecycle owner
must repair retention. Do not start S=100, RH-on, or Gate merge until this
correlation is resolved.

## Followups and open issues

- A fresh S=25 retest is warranted after the diagnostic correlation is added.
- The current trace instrumentation should remain in place.
- Root cause is not yet proven between build omission and key-chain
  disagreement; removal/recycle evidence is also incomplete.
