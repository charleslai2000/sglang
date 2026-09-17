# phase9-gates-final-20260916 -- final M1 GPU gate harnesses (v3)

Fail-closed harnesses for the three final M1 gates. **Harness/test infrastructure
only: nothing under `/opt/sglang/**` is modified, no GPU lock is taken and no
server/port is bound by this fix.**

| script | purpose | py_compile |
|---|---|---|
| `gate_common.py` | shared stdlib-only helpers: lock, ports, HTTP, strict `/flush_cache`, `/generate`, tier parsing, host-pool sizing/parsing, reclaim-event parsing, namespace guard, snapshot+offline-replay, subprocess tree work | `rc=0` |
| `lock_probe.py` | fresh-process canonical-lock probe | `rc=0` |
| `prompt_builder.py` | deterministic `>=N`-token prompt builder (CPU only) | `rc=0` |
| `wal_forensics.py` | CPU-only offline WAL identity/replay + membership + **slot cursors/generations/live bytes/free tails** + DROP_SLOT history + victim-slot proof, using the tree under test's own code | `rc=0` |
| `gate_a_content_integrity.py` | **Gate A**: DEVICE == L3 == RECOVERED per-token ids, two >=65K prompts, staged storage preconditions, mandatory storage-tier restore | `rc=0` |
| `gate_a_f1_cold_l1.py` | **Gate A-F1**: unique-prefix circular reclaim of a live target slot + post-reclaim cold-L1 storage restore | `rc=0` |
| `f2_restart_recovery.py` | **F2**: genuine new process + new lock generation, WAL rotation, post-restart storage restore | `rc=0` |
| `test_gate_helpers.py` | targeted unit tests for the pure helpers (no GPU / no server) | `rc=0` |

`python -m py_compile` was rerun on every `.py` in this directory after the v3
edits: all `rc=0` (see "Verification" below).

---

## Run commands

Run the **gate driver** on CPU (`CUDA_VISIBLE_DEVICES=""`); it launches the
server child with the real GPU UUID itself and owns the canonical lock.

```bash
TREE=/opt/sglang/local-prod-v1.1.2-candidate          # the tree UNDER TEST
PY=$TREE/env/bin/python
H=/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916

# Gate A  (two >=65K prompts; DEVICE == L3 == RECOVERED; storage-tier restore)
CUDA_VISIBLE_DEVICES="" $PY $H/gate_a_content_integrity.py --tree $TREE --port 30165

# Gate A-F1  (unique-prefix reclaim of a live target slot + cold-L1 restore)
CUDA_VISIBLE_DEVICES="" $PY $H/gate_a_f1_cold_l1.py --tree $TREE --port 30165 --expect fixed

# Gate A-F1  (unfixed control tree only: destructive reclaim -> zero-hit miss)
CUDA_VISIBLE_DEVICES="" $PY $H/gate_a_f1_cold_l1.py --tree $TREE --port 30165 --expect unfixed

# F2  (primer + recover in two separate processes + lock generations)
CUDA_VISIBLE_DEVICES="" $PY $H/f2_restart_recovery.py --tree $TREE --port 30165

# Short canary (existing driver, no storage oracle; run last)
TREE=$TREE PORT=30165 OUT=$H/final-campaign-20260917/canary.json \
  CUDA_VISIBLE_DEVICES="" $PY $H/final-campaign-20260917/canary_driver.py
```

Order: **Gate A -> Gate A-F1 -> F2 -> short canary**. Each gate takes the
canonical GPU lock `/tmp/opencode/gpu-3090.lock` itself (bounded backoff,
released in `finally`) and never signals another agent's server. `--tree`
defaults to `/opt/sglang/local-prod-v1.1-candidate` (parameterised).

### Environment variables (all optional except the tree/port you choose)

| variable | default | meaning |
|---|---|---|
| `SGLANG_GATE_TREE` | `/opt/sglang/local-prod-v1.1.2-candidate` | tree under test (also `--tree`) |
| `SGLANG_GATE_MODEL` | `/data/models/qwen35-9b-w4a16` | model path (also `--model`) |
| `SGLANG_GATE_PORT` | `30165` | gate server port (also `--port`; never 30000/30164) |
| `SGLANG_GATE_L3_ROOT` | `/data/l3` | namespace root; final dir is `<root>/phase9-gates-final-20260916/<gate>-<run-id>` |
| `SGLANG_GATE_RUN_ID` | UTC-stamp + driver pid | makes the namespace unique per run |
| `SGLANG_GATE_RUN_DIR` | `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916` | reports/logs |
| `SGLANG_GATE_PYTHON` | `<tree>/env/bin/python` | interpreter fallback |
| `SGLANG_GATE_NAMESPACE_REUSE` | unset | `=1` allows reusing a populated namespace (normally refused) |
| `SGLANG_GATE_LOCK` | `/tmp/opencode/gpu-3090.lock` | canonical lock |
| `SGLANG_GATE_GPU_UUID` | `GPU-2e3ed202-3655-d919-0a64-259209bc6587` | GPU pin for the server child |

Per-gate knobs (see `--help`): `--hc-size`, `--host-pool-margin`,
`--chain-tokens`, `--prompt-tokens`, `--filler-tokens`, `--max-fillers`,
`--sweep-tokens`, `--sweep-requests`, `--extent-size`, `--file-size`,
`--min-index-fraction`, `--min-restore-fraction`, `--expect`, `--namespace`.

---

## Host-pool sizing (the campaign root cause) and the arithmetic

HiCache write-back is **device -> host -> storage**: the graded prefix must first
be **resident in the host pool** to be backed up at all. The final campaign ran
`--hicache-size 2`, which allocates a **19,904-token** kv host pool
(`0.33 GB`) against a `65,536`-token device pool and a `~65,000`-token prompt;
the prompt can never be staged, so the product logged
`write_back: KV subtree dropped without backup due to host memory pressure`
(**72x** in Gate A s1, **253x** in F1 s1) and every arm saw `storage = 0`.

Facts used (LOCAL-PROD-v1.1.2, `qwen35-9b-w4a16`, `--kv-cache-dtype fp8_e4m3`):

* one KV token in the host pool is **16 KiB** (`HICACHE_BYTES_PER_TOKEN`);
* `--hicache-size` is **SI GB (10^9)**, not GiB, and is **split** across the
  device pools (kv + mamba) proportionally to their byte sizes
  (`hybrid_pool_assembler._split_hicache_size`); for this hybrid model the kv
  pool receives ~0.165 of the requested GB.
* Two measured anchors: `--hicache-size 2 -> 19904 kv tokens / 0.33 GB`;
  `--hicache-size 32 -> 318457 kv tokens / 5.22 GB`.
  `318457/32 == 19904/2 == 9952.0` kv-host tokens per SI GB
  (`HICACHE_KV_TOKENS_PER_GB`).

Chosen value: **`--hicache-size 8`** (the gates pass it explicitly; they do not
rely on the launcher default).

| quantity | value |
|---|---|
| graded prompt (Gate A) | 65,000 tokens (~1.06 GB KV) |
| host-pool margin | 4,096 tokens |
| required kv host tokens | 69,096 |
| minimum `--hicache-size` | `ceil(69096 / 9952) = 7` GB |
| chosen `--hicache-size` | **8 GB** -> predicted **79,616** kv host tokens (~1.30 GB) |
| actual allocated pool | parsed from the server console and asserted `>= required` before any measured request |

Why this forces eviction to storage instead of dropping the backup:

* host pool **79,616 >= 65,000 prompt + 4,096** -> the prompt is staged into host
  and written back to the extent store (no `dropped without backup`);
* it is still ~4x below the production perf profile (`L2_GB=32`) and far below
  `prompt + one graded filler`, so **unrelated filler prefixes** still push the
  target out of L2 (proven by volume in the report: unrelated tokens >= one full
  host-pool cycle) and force a storage restore.

If the *actual* allocated pool is below `prompt + margin`, the gate returns
**INVALID** before the measured request with the parsed numbers. To raise the
pool use `--hc-size 9|10|...`; the report's `host_pool_sizing` block records the
full arithmetic and the measured anchors.

---

## Gate A -- staged storage preconditions (INVALID before the measured request)

The L3 and RECOVERED arms are measured only after **every** precondition below
is asserted (each is a required check; any failure sets `invalid_reason` and the
measured request is withheld):

1. **host pool stages the prompt** -- actual kv host tokens (parsed from the
   console) `>= prompt + --host-pool-margin`;
2. **(a) target created + L1-resident** -- DEVICE arm with
   `device >= 0.8 * prompt`, `storage == 0`;
3. **(b) write-back to L3 observed** -- `evt=extent_write` count/bytes grew and
   the namespace manifest/WAL grew;
4. **(c) target present in this run's OWN Extent index** -- offline replay of the
   run's namespace (`wal_forensics.py --mode membership`), requiring
   `n_present >= ceil(--min-index-fraction * window)` and head present;
5. **(d)/(e) L1+L2 eviction forced by unrelated fillers** -- filler prompts are
   random-id prompts that do not share the target prefix; the report proves
   `unrelated_tokens >= device pool (65536)` and `>= one full host-pool cycle`;
6. **no GRADED-TARGET `dropped without backup due to host memory pressure`**
   event (target-scoped). A drop is disposable only when a **positive DELTA
   proof** shows the target's durable extent-index refs did not shrink across
   the drop: the frozen drop-free baseline must be **complete** for the full
   target window, every membership proxy must be present in both snapshots, and
   a re-snapshot consumed immediately after the drop lines must confirm the
   no-decrease verdict. A partial baseline, a missing proxy, a decrease, or an
   unattributable drop is `unknown` => INVALID (fail closed). The console
   node-id ordering is **not** an attribution mechanism (the rule was removed:
   its parent-before-child invariant is false). The
   `--min-index-fraction 0.99` STAGE acceptance
   (`persist_target_in_extent_index`) is a separate pre-existing tolerance and
   is intentionally unchanged.
7. **required pre-measurement pre-assertions** (`invalidates`, never FAILs):
   host pool stages the workload, target in the extent index, device-miss and
   host-miss guaranteed by unrelated-filler volume, storage candidate hit, and
   no target-scoped drop -- proven offline / by volume, **not** by a re-warming
   request;
8. **only then** the measured L3 arm: `storage > 0`, `device == 0`,
   `storage_backend == ExtentFileBackend`, ids == DEVICE ids;
9. **RECOVERED arm**: stop s1, wait for `/proc/<pid>` to disappear, relaunch a
   new process against the same namespace, assert same `file_uuid`, host pool
   still stages the prompt, and `storage > 0`, `device == 0`, ids == DEVICE ids.

### Target-scoped drop predicate: positive complete-baseline delta

`gate_common.durable_delta_status` / `delta_status_with_rechecks` classify a
`dropped without backup` row.  A row becomes **FOREIGN** (disposable) only when
a positive no-decrease **delta** proof holds on the target's extent-index
membership:

* monotone proxies, none may worsen: `n_present` (must not fall), `n_absent`
  (must not rise), `first_absent_index` (must not move earlier; `None` is best),
  `n_runs` (must not rise), `longest_run_len` (must not fall);
* the frozen drop-free baseline must be **COMPLETE** (all proxies present,
  `n_absent == 0`, one run, `n_present >= query_window_len`).  A **partial**
  baseline is `unknown` => INVALID: a target page that only becomes durable
  after the snapshot can then be dropped, and the drop can be masked by
  concurrent growth -- neither is observable in the aggregate proxies;
* a **re-snapshot** is consumed immediately after the drop lines, and the
  verdict must hold for **every** post-drop snapshot (worst case), so a drop
  landing between snapshots is still caught.

Anything else -- partial baseline, missing proxy, decrease, unparsed root, empty
membership -- is `unknown` => INVALID (fail closed).  `root_id` is record-only;
the removed console node-id ordering rule is never used.

INVALID vs FAIL (Gate A): `INVALID` = a precondition above did not hold (host
pool, tree binding, port, server health, flush, offline membership, store
identity, non-executed request). `FAIL` = every precondition held, the storage
tier restore was confirmed, and a **content** check failed (token mismatch or
cross-session bleed). The report always carries `invalid_reason` xor
`fail_reason`.

Store footprint: Gate A pins `EXTENT_SIZE=64 MiB` and
`FILE_SIZE=(target_slots + max_fillers*filler_slots + 4)*64 MiB` (sparse; zero
test-store growth beyond the written extents), with GC pinned off
(`MAX_SIZE=0`, `MIN_FREE_SPACE=0`) and `WAL_CHECKPOINT_BYTES=32 MiB` so the
run's own WAL replay stays cheap.

---

## Gate A-F1 -- deterministic circular reclaim of a live target slot

### New wrap trigger (fixes "recycle_events = 0 despite 1.49 GB written")

The predecessor swept with `chain + unique suffix`. That prefix-matches the
chain: the product reuses the chain's existing storage refs and allocates almost
no **new** slots, so the circular cursor never advanced. F1 now writes
**unrelated, unique prefixes** (a distinct random-id prompt per request, seed
`180000+i`), so every request allocates brand-new keys and advances the cursor.

### Slot-allocation math proving the cursor reaches a live target slot

Pinned geometry: `EXTENT_SIZE=64 MiB`, page = 16 KiB -> `4096 pages/slot`;
`FILE_SIZE = (chain_slots + 2*filler_slots + 8 + reloc_reserve_slots) * 64 MiB`
(`--reloc-reserve-slots`, default 2 -> the closure-2 destination reserve).
For a 62,000-token chain: `chain_slots = ceil(62000/4096) = 16`,
`filler_slots = ceil(16000/4096) = 4` -> **34 slots (2.125 GiB)** with the
default reserve.

* the chain is written first into an empty store, so the target's refs occupy
  the oldest slots (the head lands in the first slot the cursor fills);
* the offline pre-sweep replay reports, per target slot: cursor, generation,
  live refs/live bytes, target refs, and free tail;
* write-back fillers (unrelated) evict the chain from L2 into the slots after
  the target; the sweep then fills the remaining free region (`2*filler_slots +
  margin`) and the cursor wraps into the first full slot that holds live target
  refs -- `full_target_slots` in the report (the victim is the **oldest full
  target slot**, not necessarily the head slot; on the preserved campaign WAL
  the head is in slot 0 while the wrap victim is the full slot 1);
* the victim is detected dynamically from the console (`reclaim relocated` /
  `reclaim relocation ... refused` / `evt=extent_recycle` naming a
  target-holding slot) and confirmed offline.
  A fail-closed refusal is **not** terminal on first occurrence (the campaign
  saw 9 refusals and then made progress): the sweep continues through
  `--max-consecutive-refusals` (default 16) consecutive refusal rounds before
  giving up, and any successful relocation/recycle ends it immediately.

### Preconditions asserted before the cold request (no inference)

* `pre_target_slots_known` / `pre_victim_candidates_known`;
* `victim_held_live_target_refs` -- the victim slot's **live target refs > 0**
  (offline replay, both before and after);
* `wrap_into_victim_observed` -- a reclaim/refusal/recycle event names the
  victim slot, or a `DROP_SLOT` frame exists for it;
* `victim_reclaim_executed` -- a **successful** relocation of the victim's live
  refs (`reclaim relocated N live refs out of victim slots [...]`), or a
  recycle with a generation bump;
* `victim_generation_changed` -- post-sweep generation > pre-sweep generation
  (or a `DROP_SLOT` frame with a higher generation);
* `head_resolved_after_reclaim` -- the head key is still present and/or has
  moved out of the victim generation;
* `post_target_in_index` and `batch_exists_eq_expected` -- the offline
  `batch_exists` equals the full requested window;
* `post_no_target_drop_without_backup` -- target-scoped: a drop is disposable
  only under the positive complete-baseline delta above; every other drop is
  INVALID.  The unique-prefix **sweep** has no pre-drop baseline, so **any**
  `dropped without backup` inside it is `unknown` => INVALID -- deliberately
  **conservative** (**false-INVALID**: campaign-blocking but verdict-safe),
  because unrelated-filler disposability is NOT provable in that window without
  per-drop attribution.

### Relocation-destination reserve (owner closure 2)

Before the sweep is sent, and again pre-cold, the harness proves a **bounded
non-victim destination capacity** exists and that the expected relocation of the
largest target-holding candidate fits into it
(`relocation_headroom_bytes >= live_bytes`, `reclaim_relocatable`,
`target_live_refs > 0`). A 100%-live store with no destination outside the
victim is the product's **expected fail-closed Option-C backpressure**, not a
valid relocation-success geometry: it returns **INVALID before the measured
request** (`gate-a-f1-reserve-preflight`), never FAIL/PASS.

**Conservative by construction: possible false-INVALID, never false-PASS.**
`relocation_headroom_bytes` is the **max single** non-victim free tail, while the
product's `plan_relocation` fits the relocation across the **aggregate** free
tail of all non-victim slots; the sequential sweep cursor also packs the
trailing slots (including the `--reloc-reserve-slots` reserve) before it can
wrap, so trailing-slot packing can consume that reserve at the exact wrap
moment. This preflight is therefore **conservative**: it can return INVALID
(failure class **false-INVALID** -- campaign-blocking but verdict-safe) even
where the product would have found a destination. It can **never** produce a
**false-PASS**: a PASS still requires an observed successful relocation
(`victim_target_relocation_count_positive` in `fixed` mode), and a
refusal/recycle-only reclaim path is INVALID before the measured cold request.

`--reloc-reserve-slots` (default 2) appends that many spare slots to
`FILE_SIZE` -- a small, bounded term so the wrap is still reached; it is *not*
a pad large enough to dodge the wrap. `wal_forensics`'s
`relocation_headroom_bytes`/`reclaim_relocatable` are the offline oracle for
this. INVALID in `fixed` mode; recorded as optional evidence in the `unfixed`
control, where a destructive reclaim is the expectation.

The "allocator has no free destination except through the normal reclaim path"
condition is reported as the victim's `relocation_headroom_bytes` vs
`live_bytes`: in a packed circular store the free tail outside the victim is
`< 1 page`, so the product's reclaim path is the only allocator that can place
the new pages -- and its relocation is **fail-closed** when that headroom is
smaller than the victim's live bytes.

### Flush (FIX 4) and the cold oracle

`/flush_cache` is executed **strictly**: success requires HTTP 200 **and** the
`Cache flushed` body, after `/metrics` shows the server idle. A non-2xx (e.g.
`HTTPError 400` from `Deferred flush_cache timed out while waiting for idle
state`) or a timeout sets `flush_cache_confirmed = false` and the gate returns
**INVALID before sending the cold request** -- never "OK on an error string".
One unrelated cold-filler round is then sent and the target is re-proved present
in `cold_pre_target_still_indexed` before the measured cold request.

F1 INVALID vs FAIL:

* **INVALID**: flush not confirmed; host pool mis-sized; no wrap attempted;
  the wrap was **refused** by the product's fail-closed relocation (the
  head-slot recycle was not exercised); the victim held no live target refs;
  the pre-sweep/post-sweep relocation reserve is absent (no bounded non-victim
  destination capacity, or the expected relocation does not fit);
  generation/head/index/batch_exists post-state unsatisfied; any
  `dropped without backup` not proven FOREIGN by the positive
  complete-baseline delta (in the SWEEP there is no baseline at all, so every
  drop there is INVALID -- **conservative** **false-INVALID**, see above).
  The expected shape for this case is
  `wrap_observed = true`, the victim holding live refs, and insufficient refusal
  headroom -> **INVALID, not FAIL**. This is expected behavior; covered by
  synthetic regression, not by a preserved-WAL replay artifact.
* **FAIL** (`--expect fixed`): the reclaim executed and the cold request ran,
  but the restore did not come from storage (`storage == 0`), the zero-hit miss
  marker appeared, `batch_exists != expected`, or the ids differ from the DEVICE
  reference.
* **PASS** (`--expect fixed`): relocation executed, cold `storage > 0`,
  `device == 0`, no zero-hit miss, `batch_exists == expected`, ids exact.

`--expect unfixed` is the control mode for a tree whose reclaim is destructive
(no relocation): PASS requires a recycled victim, a zero-hit cold miss, and the
offline replay showing the head absent with the rest of the chain present.

---

## F2 -- genuine restart recovery

`--phase all` runs `primer` and `recover` in separate processes:

* **primer**: unique namespace, host-pool sizing asserted, chain written and
  proved present in the extent index (offline membership) with no
  `dropped without backup due to host memory pressure` at all.  The primer takes
  a single post-write-back membership snapshot, so no pre-drop baseline and no
  positive delta proof exists: ANY drop is `unknown` => INVALID.  This is
  deliberately **conservative** (**false-INVALID**: campaign-blocking but
  verdict-safe) because unrelated-filler disposability is NOT provable in that
  window without per-drop attribution.  WAL checkpoint rotation count `> 1`,
  manifest grew, storage restore positive; SIGTERM server #1 while the driver
  still holds the lock; prove `/proc/<pid>` is gone and a fresh-process lock
  probe still sees the lock held; release the lock.
* **recover**: a NEW process re-acquires the lock (generation must advance),
  relaunches against the same namespace, asserts the same `file_uuid`, the
  host pool still stages the chain, and the post-restart request has
  `storage > 0` with `device == 0` and ids == the primer's DEVICE ids.

F2 INVALID vs FAIL: `INVALID` = restart not genuine (same process / inherited
lock fd / no new lock generation), store identity changed, host pool too small,
or no storage-tier restore. `FAIL` = genuine restart + confirmed storage
restore but content mismatch.

---

## Store policy: unique namespaces, no shared-store access

Every run sets a UNIQUE namespace before the server starts
(`SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR = <root>/phase9-gates-final-20260916/<gate>-<runid>`).

* No store-clear endpoint is ever called. `resolve_namespace()` refuses a
  namespace resolving inside the shared production store
  `/data/l3/local-prod-v1.1` and refuses a pre-populated namespace unless
  `SGLANG_GATE_NAMESPACE_REUSE=1`.
* The preserved `pre-gate4-store/` copy and `/data/l3/local-prod-v1.1/**` are
  never read, written, or deleted. `/data/models/**` is untouched.
* Gate A-F1's `/flush_cache` resets in-memory radix/device state only; it does
  **not** call `/hicache/storage-backend/clear` and does not modify store files.
  Offline forensics always replay a **snapshot copy**, never a live store.

### Wrap evidence is NOT `total_store_written > file_size`

That counter includes re-writes to existing refs and is not evidence of a wrap.
The v3 report records, instead: per-slot cursor/generation/live-bytes/target
refs before and after, the victim slot id, pre/post generation, relocation
count/bytes, `evt=extent_recycle` events, `DROP_SLOT` frames, and the resulting
head ref (slot + generation).

---

## Verification

* `python -m py_compile` on every `.py` in this directory: **all rc=0**
  (`PYTHONDONTWRITEBYTECODE=1`).
* `CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest
  test_gate_helpers`: **74 tests, OK** (CPU only).
* CPU-only dry-run of the new precondition logic: `wal_forensics.py --mode
  membership` was run against the **preserved campaign snapshot**
  (`gateA-F1/store-snapshot-post-sweep-f1-20260917T082421Z-302181`, read-only) and
  confirms `sglang.__file__` resolves inside the tree under test and reproduces the
  slot cursors and the membership/head state. The victim live-ref count and the
  fail-closed refusal reason are expected values covered by synthetic regression,
  not reproduced from this snapshot.
* The tree under test is always asserted to resolve
  `sglang.__file__` under `<tree>/src/` (guards the editable-install landmine
  that would otherwise silently load the stale workspace copy).

### Exit-code table

| rc | verdict | meaning |
|---|---|---|
| 0 | `PASS` | all required checks executed and passed |
| 1 | `FAIL` | preconditions held; a required content/oracle check failed |
| 2 | `INVALID` | a precondition/oracle was not established: port busy, preflight mismatch, server unhealthy, host pool too small, target not in the extent index, no reclaim executed, flush not confirmed, restart not genuine, evidence field missing |
| 3 | `PENDING` | canonical GPU lock not acquired within the bounded window |
| 4 | `ERROR` | unexpected driver exception |
| 5 | `BLOCKED` | missing external input (tree/model/tokenizer/namespace) |

### Expected run time (single RTX 3090, 9B W4A16, 64K context)

| gate | expected |
|---|---|
| Gate A | ~35-60 min (2x 65K prefill + ~5 unrelated 16K fillers + 2x offline membership) |
| Gate A-F1 | ~25-45 min (62K prefill, write-back fillers, unique-prefix sweep, 3 offline replays) |
| F2 | ~35-60 min (primer + recover, each with a 62K prefill and offline membership) |

WAL replay on startup scales with WAL size; the gates pin
`WAL_CHECKPOINT_BYTES` (16-32 MiB) so stores stay small.
