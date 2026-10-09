# TEST-20260908-T38C-PAIRED-TRACE-INDEPENDENT

## status

done

## invocation

- Task / epoch: `TEST-20260908-T38C-PAIRED-TRACE-INDEPENDENT` / `E20260908-T38C`.
- Role: independent tester.
- Scope respected: read-only product/evidence verification; no product files,
  control-plane files, remote data, or new experiment were changed.
- No S=100 or RH-on run was started.

## artifacts and method

- Local experiment report: `work/EXP-20260908-T38C-PAIRED-TRACE-S25.md`.
- Ledger entry: `.memory/phase2-hicache-design/ledger.md`, T38C paired trace
  entry near lines 2869-2887.
- Remote trace:
  `/root/evidence-gate3-parked/s25-t38c-paired-trace-fix1/t38c-probe.log`.
- Remote join log used for this verification:
  `/root/evidence-gate3-parked/s25-t38c-paired-trace-fix1/run-20260908-013025/join.log`.
  The requested directory-root `join.log` does not exist; the run-local path
  above is the actual artifact referenced by `driver.log`.
- Remote driver log:
  `/root/evidence-gate3-parked/s25-t38c-paired-trace-fix1/driver.log`.

I independently parsed every JSON line in the two logs and recomputed event
counts, warm-session mapping, Mamba key sets, presence/boundary/fold fields,
and timestamp ordering.

## acceptance checks

### 1. Mamba write count and write result

PASS for the observed writes:

- Trace: 1,286 JSON events.
- `pc_mamba_write`: exactly 25.
- All 25 have `mamba_transfer_exists=true`.
- All 25 have `batch_set_v2=true`.
- All 25 Mamba keys are non-empty, unique, and equal their event's
  `final_kv_hash`.

This rules out `batch_set_v2` returning false for the 25 observed Mamba write
events. It does not prove that an expected transfer was never omitted before a
`pc_mamba_write` event could exist.

### 2. Warm-session mapping and short-suffix exclusion

PASS. `join.log` contains eight round-1 warm rows, sessions `s00000` through
`s00007`; all have `rc=0`.

- `s00000`: warm RID `f1ec5c48...`; Mamba query at trace line 844; present,
  boundary/final pages `55145/55145`.
- `s00001`: warm RID `b78bca17...`; gate lines 904-906 show
  `matched_len=55097`, `suffix_len=84`, threshold `256`, and
  `declined_too_short`. There is no extent storage query for this RID. It is
  correctly excluded.
- `s00002`: warm RID `3cdae98f...`; Mamba query lines 912-914; the failure
  described below.
- `s00003`: warm RID `087f3942...`; query line 949; present,
  boundary/final pages `55125/55125`.
- `s00004`: warm RID `889da50e...`; query line 1011; present,
  boundary/final pages `55102/55102`.
- `s00005`: warm RID `6ee82330...`; query line 1074; present,
  boundary/final pages `55124/55124`.
- `s00006`: warm RID `d917983e...`; query line 1137; present,
  boundary/final pages `55103/55103`.
- `s00007`: warm RID `1f54ff79...`; query line 1227; present,
  boundary/final pages `55104/55104`.

Therefore there are seven full warm samples: six full KV+Mamba restores and
one failed full restore. The join rows agree with the trace-side mapping and
show the six successful samples receiving approximately 55K storage tokens;
the `s00002` row has zero storage prefill.

### 3. Exact write-key/query-key relation and missing key

PASS for the stated set relation:

- Write-key set: 25 unique keys.
- Full-warm query-key set: 7 unique tested keys.
- Intersection: 6 keys.
- Query keys absent from the write set: exactly one:
  `3bb6ca491db0290ff050cd7f4f8e4110d57b290523c7c15569006e357f2ad8de`.
- Write keys not queried by these seven warm sessions: 19.

The sole query-only key is `s00002`'s key. Its query record has
`raw_kv_frontier=55145`, `tested_present=false`, `boundary=0`, and
`final_pages=0`. The paired storage record has `sidecar_hits={"kv":55145}`
but folded `kv_hit_pages=0` and `storage_hit_count=0`, consistent with the
all-or-nothing KV/Mamba result rather than a generic KV storage outage.

### 4. Causal classification

The experiment report's main classification is supported, with one material
qualification:

- Six adjacent full samples prove the frontier/fold common path can restore
  both KV and Mamba, so a generic extent folding defect is not supported.
- The 25 observed write acknowledgements are all successful, so a false
  `batch_set_v2` result is not supported for those writes.
- The missing `s00002` key is an exact, session-specific write/query mismatch;
  omission, key/lifecycle mismatch, or later sidecar removal remain the
  plausible product-side classes.
- The evidence does **not** fully rule out incomplete asynchronous settling as
  an alternative for the missing transfer. The trace contains a late
  `pc_mamba_write` at line 1222 (`node_id=688`, timestamp
  `1788803160.825`), after the first warm began at `1788803023.746` and after
  the last build row ended at `1788802706.443`. Thus the fixed 300-second
  settle excludes an early query for the already-observed `s00002` key only in
  the sense that the key is absent from the eventual trace; it does not prove
  that every expected asynchronous build write had completed before that
  query. This is a limitation of the evidence, not a contradiction of the
  observed key-set result.

The precise independent verdict is therefore: **common-path frontier fix
effective; `s00002` is a real session-specific missing-key/full-fold failure;
the leading classification is build-to-warm key/lifecycle mismatch or
omission, but the supplied logs do not isolate that from a delayed/unobserved
expected write.** This remains causal-probe evidence, not Gate A/B/C evidence.

## summary

The completed S=25 paired trace supports the stated 6/7 full-warm result and
the `s00002` missing-key classification. The exact key-set relation and all
requested counts reproduce independently. The only correction required to the
causal wording is that a late observed Mamba write leaves asynchronous
completion as an unclosed alternative; no generic backend or observed-write
failure is indicated.

## followups

- Fresh tester Task ID: repeat the same S=25 RH-off vehicle after the minimal
  fix; require every full warm query key to have an observed successful paired
  write before scaling.
- Add a session/node-correlated expected-transfer record and an explicit
  backup-drain/completion barrier or per-key completion timestamp. This is
  needed to distinguish omitted transfer, failed write, delayed write, key
  mismatch, and post-write recycle/removal.
- Preserve all-or-nothing KV/Mamba folding and the 256-token exclusion rule.

## open_issues

1. The trace proves absence of the `s00002` key from the eventual 25 observed
   writes, but does not record whether the build expected that exact transfer
   and, if so, whether it was queued but delayed beyond the warm query.
2. No authorized event records Mamba sidecar removal/recycle for the missing
   key.
3. The root-level `join.log` path named in the dispatch is absent; the
   run-local join log is complete and was used instead.
