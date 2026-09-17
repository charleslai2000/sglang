# Runbook — executing the Option-C durability review

Everything here is **CPU-only** and read-only with respect to the frozen tree
and the candidate tree. The harness writes only under
`/tmp/opencode/f1-optionC-review-scaffold-20260917/` and its `--out` paths.

## 0. Hard environment rules

```sh
export CUDA_VISIBLE_DEVICES=999      # CPU only; never a GPU
# DO NOT acquire or touch /tmp/opencode/gpu-3090.lock
# no server, no port binding; ports 30000 and 30164 are off limits
# do NOT write to /opt/**, /data/l3/**, /data/models/**, the workspace,
# or existing /var/log/** evidence
```

Python: `/home/ubuntu/venvs/sglang-3090/bin/python` (3.12, torch 2.13 CPU).
Every oracle takes `--tree <path>` (default
`/opt/sglang/local-prod-v1.1-candidate`) and resolves `<tree>/src/python`,
`<tree>/python`, or `<tree>` for the `sglang` package; it records the resolved
`sglang.__file__` in the result JSON and refuses to run against a tree it did
not import from.

Directory layout:

```
/tmp/opencode/f1-optionC-review-scaffold-20260917/
  REVIEW-PROTOCOL.md     contract -> falsification questions -> oracle map
  THREAT-MODEL.md        plausible-but-wrong implementations -> catching oracle
  RUNBOOK.md             this file
  oracles/               _harness.py, 6 oracles, selftest, run_all.py
  results/               frozen-control baseline + candidate results + SUMMARY
```

## 1. Compile check (every script)

```sh
cd /tmp/opencode/f1-optionC-review-scaffold-20260917/oracles
CUDA_VISIBLE_DEVICES=999 /home/ubuntu/venvs/sglang-3090/bin/python -m py_compile \
  _harness.py oracle_payload_bytes.py oracle_generation.py oracle_live_dead.py \
  oracle_no_capacity.py oracle_crash_matrix.py oracle_restart_replay.py \
  selftest_oracle_logic.py run_all.py
echo "py_compile exit=$?"
```

Expected: exit 0. Record the sha256 of every script (the result JSON also embeds
the tree identity; scripts change -> recompile and re-run).

## 2. Mechanism self-test (proves the oracles are not vacuously always-FAIL)

```sh
CUDA_VISIBLE_DEVICES=999 /home/ubuntu/venvs/sglang-3090/bin/python \
  selftest_oracle_logic.py --tree /opt/sglang/local-prod-v1.1-candidate \
  --out ../results/selftest.json
echo "exit=$?"
```

Expected: exit 0, `ST-1..ST-4` PASS. This is **synthetic mechanism evidence
only** and must never be cited as product evidence.

## 3. Frozen-tree control run (expect-FAIL)

The frozen tree has no relocation, so the relocation-dependent oracles MUST
FAIL. A control run where such an oracle PASSes means the oracle is vacuous and
must be fixed before reviewing the candidate.

```sh
CUDA_VISIBLE_DEVICES=999 /home/ubuntu/venvs/sglang-3090/bin/python \
  run_all.py --tree /opt/sglang/local-prod-v1.1-candidate \
  --mode frozen-control --outdir ../results
echo "overall exit=$?"    # 0 == every oracle detected the frozen defect
```

Recorded baseline (this scaffold): `overall_exit=0`; all six oracles FAIL.
The historically decisive rows are `crash: CM-2` (frame order
`DROP_SLOT, SET, BATCH_COMMIT`), `crash: CP1/CP2/CP3 refs-reachable` and
`restart: batch-exists-contract` (chain of 4 → `batch_exists == 0`, the F1
symptom).

## 4. Candidate run

Once the implementer's tree exists (e.g. `/tmp/opencode/v1.1.2-optionC-20260917`
or the live candidate):

```sh
CAND=/path/to/candidate-tree           # read-only for us
CUDA_VISIBLE_DEVICES=999 /home/ubuntu/venvs/sglang-3090/bin/python \
  run_all.py --tree "$CAND" --mode candidate --outdir ../results
echo "overall exit=$?"
```

Interpretation of `run_all` exit codes:

| exit | meaning |
|---|---|
| 0 | every oracle PASS (or, for candidate mode, all required checks held) |
| 1 | at least one oracle FAIL — a candidate defect; read `failed_checks` |
| 2 | at least one INVALID — not a pass; re-drive the un-exercised row |
| 3 | harness/child error — investigate, do not accept |

Targeted re-runs (useful when one oracle is INVALID):

```sh
OR=oracle_payload_bytes.py
CUDA_VISIBLE_DEVICES=999 /home/ubuntu/venvs/sglang-3090/bin/python "$OR" \
  --tree "$CAND" --mode candidate --out ../results/candidate-"$OR".json --keep-tmp
```

## 5. PASS vs INVALID discipline

* **PASS**: the required observation was produced and held.
* **FAIL**: a contract row was violated. Cite the row id from
  `REVIEW-PROTOCOL.md` and the evidence field of the failing check.
* **INVALID**: the reclaim/relocation window was not reached, or a needed
  surface was unavailable. Examples: `CM-1:window-exercised` = no relocation
  frame was emitted (the trigger fail-closed); `*:victim-selected` = no
  generation bump; `v1:available` = torch missing.
  **INVALID is never treated as PASS.** Either:
  1. re-drive with a scenario that reaches the window (the capacity scenario is
     the primary; the fragmented scenario is the no-capacity control), or
  2. record `UNVERIFIABLE: <reason>` plus the smallest missing capability.
* A crash cut that truncates before any relocation frame is INVALID, not PASS;
  the crash matrix enforces this through `CM-1`.

## 6. Static checks the dynamic harness cannot cover

Required in addition to the oracle run (see `REVIEW-PROTOCOL.md §7`):

```sh
# 6a. reviewed bytes / diff scope (candidate tree vs frozen)
git -C "$CAND" rev-parse HEAD            # if it is a git worktree
git -C "$CAND" diff --stat -- src/python/sglang | tail -40
# REQUIRED: the diff must stay inside the Extent surface + its tests; any
# change to hicache_storage.py or a non-Extent backend is a N4 finding.

# 6b. lock order (_write_gate -> _lock) on the relocation path
#     manually list every acquisition site on:
#       plan -> destination allocation -> pwrite -> WAL append -> install
#     FAIL if a relocation site takes _lock without _write_gate, or drops/
#     reorders the gate, or calls back into a writer while holding _lock.

# 6c. no new WAL protocol
grep -n "FRAME_" "$CAND"/src/python/sglang/srt/mem_cache/storage/extent/extent_metadata.py
# the frame-type set must remain {SET, BATCH_COMMIT, GROUP_COMMIT, DROP_SLOT,
# CLEAR, CHECKPOINT_MARK}; the crash matrix asserts this dynamically too.
```

## 7. Evidence to retain

* `results/<mode>-SUMMARY.json` (aggregate) and each oracle JSON.
* For any FAIL: the failing check's `evidence` field (refs, sha256, frame
  order, fold mismatches). Use `--keep-tmp` so the store dirs remain.
* The resolved `sglang_file` and the sha256 of the four touched frozen files
  (`REVIEW-PROTOCOL.md §1`) plus the candidate's corresponding hashes.
* The `selftest.json` (mechanism) kept separate from product results.

## 8. Known limitations / do-not-over-claim

* The harness does **not** simulate power loss; it truncates the WAL at frame
  boundaries and reopens a fresh process, which tests reachability and
  durability ordering, not storage-media durability.
* `no_capacity` feasibility uses append-cursor tails; holes behind cursors are
  legitimate destination space for the implementation, so infeasibility only
  classifies expectation. The safety checks are unconditional.
* The capsim scenario is small (4 slots, 16 KiB extents). It is a *mechanism*
  test of the contract, not a capacity/performance test; the bounded-cost check
  is an inequality, not a measurement of the production constant.
* Lock order and non-Extent inertness require the static arguments in §6; the
  dynamic results are corroboration only.
