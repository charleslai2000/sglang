# Threat model — plausible-looking implementations that still violate the contract

Each row is a way an implementation can pass **the implementer's own tests**
(and often a naive review) while violating the live-ref relocation contract,
and the independent oracle that catches it. The common thread: implementer
tests usually assert over *the refs their relocator decided to move*, using
*their own* read-back buffers, at *one* durability boundary, after a *clean
close*. Each threat exploits one of those blind spots.

| ID | Threat | Why the implementer's tests miss it | Oracle that catches it |
|---|---|---|---|
| T1 | **Partial enumeration**: relocate only the KV/head refs of the victim; leave sidecar or other live refs behind | the test iterates the relocator's own key list, which excludes the refs it never enumerated | `live_dead: LD-1`; `payload: mixed:live-refs-survive` / `:mamba-component-preserved` |
| T2 | **Length-only corruption**: move bytes with a layout/offset bug that preserves `len()`; read-back uses a fresh buffer and checks only the boolean/length | length check passes; a dummy/zeroed buffer is never poisoned | `payload: *:bytes-checksum-exact` (sha256); `v1:bytes-checksum-exact` poisons the target page before reading |
| T3 | **Dead-ref resurrection**: iterate `_slot_keys[victim]` including a stale-generation entry, re-register it at the new generation | no production test creates a stale `_index` entry, so it is never exercised | `live_dead: LD-2:stale-not-resurrected` (defensive seam; reachability note in the protocol) |
| T4 | **Destination inside the victim**: relocate refs into the victim slot's own free tail, then overwrite it with the new page | a byte test that reads before the overwrite passes; a short test may never re-read | `payload: *:dest-non-victim`; `crash: CP1-before-commit`; `generation: GEN-4` |
| T5 | **Recursive reclaim**: allocating the destination triggers another reclaim that selects the same victim (or re-enters the write path) and bumps it twice | single-threaded happy path never re-enters; no assertion on generation deltas | `generation: GEN-3b:single-step-bump`; static call-graph check (A1, protocol §7) |
| T6 | **Drop before commit**: emit `DROP_SLOT` before the replacement data/commit is durable; after a clean `close()` everything looks fine | `close()` checkpoints the already-consistent state; only a crash *between* the frames reveals it | `crash: CM-2:no-drop-before-replacement-commit`; `CP1-before-commit:refs-reachable-bytes-exact` |
| T7 | **Checkpoint taken mid-relocation**: manifest snapshot between destination pwrite and `BATCH_COMMIT`, so the relocated refs are absent from the manifest; a clean reopen re-checkpoints from RAM and hides it | the test closes/checkpoints again, which snapshots the corrected in-RAM index | `crash: CP2-after-commit-before-retire` (WAL-only replay); `restart: walonly:*`; `checkpoint-load:*` |
| T8 | **Group boundary splits KV from Mamba**: relocate KV with an ungrouped batch but Mamba with (or without) the group, or re-emit a Mamba component as KV | a presence test finds the key and ignores `component`; restart picks the wrong sidecar policy | `payload: mixed:mamba-component-preserved`; `restart: *:mamba-component-restored`; `live_dead: LD-3c` |
| T9 | **Fail-closed that already mutated**: on exhausted capacity, return `False`/all-`False` after bumping the victim generation or dropping its keys | the test asserts the return code only, not that state is unchanged | `no_capacity: *:fail-closed-state-unchanged`; `*:victim-intact`; `*:no-old-generation-exposure` |
| T10 | **Self-confirming read-back**: compare relocated bytes to the implementer's own shared buffer (which they also wrote from), not to storage | both sides are the same buffer/alias, so corruption cancels | `payload: v1` poisons the pool page before the read; flat path reads through the public `batch_get` into a fresh target and compares sha256 |
| T11 | **Generation bookkeeping shortcut**: install a relocated ref with a "fresh" generation not equal to its slot's current generation, or bump without re-registering | live lookup in the same process can still succeed if lookup only checks non-None | `generation: GEN-2:survivor-generation-current`; `crash: *:generation-current`; `restart: *:generation-consistent` |
| T12 | **New WAL protocol**: introduce a "relocation/pin" frame type that their own replay understands but older replay/rollback does not | their tests exercise their replay; nothing checks the frame-type set against the frozen protocol | `crash: CM-0:no-new-wal-protocol`; static diff of `extent_metadata.py` frame constants |
| T13 | **Whole-file compaction dressed as relocation**: rewrite all extents to make the victim safe; misses disappear but cost is O(file/context) | the test measures correctness, not bytes written, and the file is small in tests | `payload: *:cost-bounded`; `*:non-victim-untouched` |
| T14 | **Permanent pinning**: mark relocated refs un-evictable so they can never be reclaimed; short tests never reach the pressure point | tests stop before the pinned set exceeds capacity; the failure is a later deadlock/backpressure | `generation: GEN-6:no-permanent-pinning`; static pin/lifecycle audit |
| T15 | **Engine-liveness assumption**: treat "live" as "the engine currently references it", so a ref that is live in the backend but reachable only through an unconsidered path is not relocated | engine end-to-end tests only re-request the paths the engine exercises | `live_dead: LD-1` (Mamba sidecar sharing the victim); protocol §2 adversarial note |
| T16 | **Fix the predicate instead of the durability**: make `batch_exists` gap-tolerant / non-consecutive so the F1 miss disappears | the e2e restore test goes green while `_page_transfer` maps hit index *i* to host slot *i* and silently misplaces pages | `restart: *:batch-exists-contract`; static diff of the lookup path; this is the already-rejected direction (`F1-ROOT-CAUSE-REPORT §4`) |
| T17 | **Non-Extent collateral**: change a shared contract (`hicache_storage.py`) while "on the way", altering other backends' byte/behaviour | the Extent test suite is green; other backends are not run | `N4` diff scope + repo non-Extent suite (protocol §7 `UNVERIFIABLE` without the diff) |

## Confidence versus proof

* T2/T4/T6/T8/T9/T10/T11/T12/T13/T16 have **deterministic** oracles: a single
  run on the candidate either produces the required observation or not.
* T5/T7/T14/T15/T17 are **timing- or scope-dependent**: the dynamic oracle is a
  bounded stress plus an independent fold, and the terminal review must add the
  static argument named in `REVIEW-PROTOCOL.md §7`. A green stress run alone is
  not proof; a red one is sufficient to block.

## Non-threats (do not invent requirements)

* An implementation that fail-closes on a full/fragmented file is contract-
  compliant even though it relocates nothing: `no_capacity` PASSes when the
  victim is intact and state is unchanged. The liveness regressions
  (`write-succeeds-with-capacity`) are reported separately and are not the same
  failure class.
* A relocation that uses holes behind allocator cursors is allowed; the tail
  feasibility model is only used to classify expectation, never to fail an
  implementation that preserves bytes.
* Generic error variants (`io_uring` vs `preadv`, Python vs C++ exceptions) are
  not product rows and must not spawn oracle variants.
