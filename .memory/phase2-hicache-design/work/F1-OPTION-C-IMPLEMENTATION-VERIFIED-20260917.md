# F1 Option C — implementation landed, orchestrator-verified (2026-09-17 ~00:55Z)

Cutoff 09:00 (~8 h). Status: implementation **DONE and independently spot-verified**; adversarial
durability review still to run.

## 1. Authoritative tree + scope (verified by orchestrator, not just reported)

Tree: `/tmp/opencode/v1.1.2-optionC-20260917/` (fresh `cp -a` of the frozen candidate).
`diff -rq frozen/src candidate/src` => **exactly 3 files**, no others:

| file | candidate sha256 | frozen sha256 |
|---|---|---|
| `storage/extent/extent_allocator.py` | `fdbd9e4965b5f0613ff7e12c539995233403f9567d7e7b54f5bb4d93bef10d13` | `285df97c01da9d754c33153aedf3cf21d77ec0449740220e8d758819ee552566` |
| `storage/extent/extent_file_backend.py` | `b284ec2a710d2afbc85f620365f00cab2726b4ae38407a9aaf9effac54e07002` | `fbd19f10e66900a48dcc5acbeb5901c9c00cbc0e5a73fe208b6cac799b1b6b13` |
| `test/.../test_extent_file_backend_unit.py` | `bb08e341d14c7fe53abc541874ed908b970480f073acfb2ae9fe755bca4ff117` | `65e14e3fbc840aef9bda45f3b6f34b29f186edcd6cc9fc08dc32f7bf3407eaf4` |

Frozen tree unmodified (`find -newermt` empty). No `/opt`, `/data`, or workspace write.

## 2. The decisive verification: LOOKUP SEMANTICS PROVABLY UNCHANGED

The owner forbade changing lookup semantics. Independently confirmed by **byte comparison**, which is
stronger than reading a diff:

* `srt/mem_cache/hicache_storage.py` — **byte-identical** to frozen (the `batch_exists` contract lives here).
* `srt/managers/cache_controller.py` — **byte-identical** to frozen (`_storage_hit_query`,
  `_page_transfer` positional mapping, prefetch revocation all untouched).
* `ExtentFileBackend.batch_exists` in the candidate is the **same body** as frozen
  (`return i` on the first `lookup(...) is None`, else `len(keys)`).

So the fix is entirely on the **durability side**, exactly as ruled: the chain is no longer destroyed, rather
than the lookup being made gap-tolerant.

## 3. Hook site and the Gate-B question (owner follow-up #1)

`_relocate_reclaim_victims_locked` — `extent_file_backend.py:2016`; victim enumeration `_reclaim_victims:1988`;
pure placement `ExtentAllocator.plan_relocation` — `extent_allocator.py:434`; per-entry durable publish
`_append_relocation_commit:1142`.

Called from the two write entry points (`:1458` v1 zero-copy path, `:2166` v2/generic path) **before** the
DROP_SLOT append / generation bump.

**Gate B determination (answering the coder's flagged follow-up):** the call site is syntactically on the
write entry points, but `_reclaim_victims` returns `[]` whenever the pure planner produced no circular-reclaim
victims (`passed` empty), and `_relocate_reclaim_victims_locked` then returns `True` immediately
(`if not victims: return True`) **before** any allocation, I/O, or WAL work. On the ordinary no-wrap path the
added cost is one function call plus an iteration over an empty `passed`.

Measurements support this: a no-wrap 1980-page write took **0.1453 s (candidate) vs 0.1477 s (frozen)** —
candidate marginally faster, i.e. within noise, **no regression**.

=> **Gate B (native 64K/128K write-path performance) remains VALID; no re-run required.** The relocation
body executes only on a circular reclaim, which is the mechanism under repair, not the steady-state write
path. (If a later change moves the hook body onto the ordinary path, this determination must be revisited.)

## 4. Contract + invariant evidence (tests A-G, FAIL-before -> PASS-after)

`verify_frozen.json` (unfixed tree) vs `verify_candidate.json` (fixed tree); all seven flip:

| test | frozen | candidate |
|---|---|---|
| A F1 reproducer | `batch_exists=0`, `bytes_exact=false`, refs `{h0:null,h1:null,h2:null}` | `batch_exists=3`, `bytes_exact=true`, refs resolve to `[1,14000..15000,0]` |
| B multi-key victim | `all_live=false`, `bytes_exact=false` | `all_live=true`, `bytes_exact=true`, `stale_absent=true`, `no_stale_wal=true` |
| C generation | `new_gen_matches=false`, `new_verify_true=false` | `new_gen_matches=true`, `new_verify_true=true`, `stale_verify_false=true`, `victim_generation_bumped=true` |
| D crash matrix | all four false | `before_commit_old_authoritative=true`, `after_commit_new_wins=true`, `after_retire_only_new=true`, `no_victim_exposure=true` |
| E checkpoint+replay | `manifest_has_head=false`, `reopened_ok=false`, `latest_refs_win=false` | all true, `bytes_exact=true` |
| F no-capacity | `refused=false`, `victim_intact=false`, `reopened_intact=false` | `refused=true`, `victim_intact=true`, `used_unchanged=true`, `new_absent=true`, `no_drop_frame=true`, `reopened_intact=true` |
| G KV+Mamba byte exact | `kv_exact=false`, `mamba_exact=false` | `kv_exact=true`, `mamba_exact=true`, `components_preserved=true`, `relocated=true` |

WAL ordering observed: `SET@5, BATCH_COMMIT@6, DROP@7` — i.e. the relocation commit strictly precedes the
victim drop, satisfying contract point 6 and the crash invariants.

Suites: `test_extent_file_backend_unit.py` **115 passed** (baseline), `test_extent_g1_metadata_unit.py`
**42 OK**, plus `test_extent_g1_allocator_unit.py` **17 OK**.

**Disclosed test change:** `test_circular_wrap_drops_oldest_slot` asserted the *pre-fix destructive*
behaviour and was replaced by `test_circular_wrap_relocates_live_refs_or_fails_closed`. This is a deliberate
contract change (the old assertion encoded the defect), reported rather than hidden — the adversarial review
must confirm the replacement is a genuine behavioural test and not a weakened assertion.

## 5. Behavioral consequence to flag to the owner (by contract, not a defect)

On a circular reclaim with **no non-victim destination capacity**, relocation now **fails closed and refuses
the write** instead of overwriting live victims. That is precisely the owner's required
"never recycle a live victim / backpressure" semantics, but it is a **real operational behavior change under
a tightly packed store**: backpressure rather than silent live-data loss. A production compaction/GC or
retention-policy follow-up may be wanted; it is **out of the current authorized scope** and was not
implemented.

## 6. Remaining before the GPU campaign

1. **Adversarial durability review** must run over this implementation using the independent scaffold
   (`f1-optionC-durability-review-scaffold-20260917`) — the implementer's A-G tests are implementation
   evidence, **not** acceptance.
2. Then freeze the unique `v1.1.2-candidate` identity (devops prep running).
3. Then the single GPU campaign: Gate A 64K/128K -> F1 post-wrap cold-L1 -> F2 true restart -> canary.

GPU untouched: **0 % / 1-4 MiB**, no servers, ports 30000/30164/30199 free, canonical lock `free`.

## 7. Owner decision (2026-09-17 ~01:00Z): close-out, no new mechanisms

Owner accepted the implementation facts and set the closing sequence. **No further tests or design
branches.**

Sequence (unchanged): `independent durability review -> freeze v1.1.2 if PASS -> ONE final GPU campaign`.

The independent review is scoped to exactly **four** acceptance questions:
1. Is the new test genuinely validating relocation behaviour rather than manufacturing PASS by weakening the
   old assertion?
2. Can destination allocation implicitly recursively re-reclaim the CURRENT victim?
3. Under checkpoint/replay, does the LATEST relocated ref always win?
4. Does no-capacity/backpressure leave any half-publication / half-retirement state?

PASS on those four => **approved to freeze `v1.1.2-candidate`**.

Owner also confirmed:
* the crash matrix, fail-closed, and KV+Mamba byte-exactness results are the key ones, and
  `SET -> BATCH_COMMIT -> DROP` satisfies "new ref durable before victim retirement";
* the measured no-wrap steady-path result keeps the **existing Gate B valid**;
* "backpressure instead of overwriting live victim under a full store" is the **correct new contract, not a
  blocker** — it is registered as a **post-launch capacity-operations item**; no compaction/GC is to be
  designed today;
* the final GPU campaign stays as-is:
  `Gate A 64K/128K -> F1 post-wrap cold-L1 -> F2 true restart/rebuild -> short canary`;
* only two outcomes are acceptable: `GREEN`, or `BLOCKED + single blocker`;
* GGUF / SWE / IQ3 / reasoning / Rust scheduler remain out of scope.

Dispatched: `f1-optionC-durability-adjudication-20260917` (reviewer-deep) — executes the independent oracle
scaffold against the candidate (and the frozen control), settles Q1-Q4, and returns PASS/FAIL/INVALID. The
implementation's own A-G tests are explicitly treated as implementation evidence, **not** acceptance.

## 8. Independent review scaffold complete (2026-09-17 ~01:05Z)

The clean-room scaffold under `/tmp/opencode/f1-optionC-review-scaffold-20260917/` is complete. All Python
scripts passed `py_compile`; it uses CPU-only `CUDA_VISIBLE_DEVICES=999`, did not touch the GPU lock, start a
server, bind a port, or modify frozen/source/data/evidence paths.

Its frozen-tree control run is **non-vacuous**: `run_all.py --mode frozen-control` exited 0 while all six
production oracles reported **FAIL** on the known-bad frozen tree:
`payload_bytes`, `generation`, `live_dead`, `no_capacity`, `crash_matrix`, `restart_replay`.
The synthetic oracle-logic self-test also passed (comparator rejects same-length corruption; independent
WAL-fold semantics pass), but is explicitly **not** product evidence.

The remaining acceptance step is the reviewer-deep execution against the candidate, followed by the required
static checks for lock order, non-Extent scope, candidate identity, and exact relocation call graph. No
additional tests or design branches are authorized.
