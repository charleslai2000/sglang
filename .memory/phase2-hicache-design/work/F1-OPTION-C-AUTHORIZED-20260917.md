# F1 Option C authorized — reclaim-time live-ref relocation (2026-09-17 00:40Z)

Cutoff 09:00 (~8.3 h). Path: `bound proof (DONE, negative) -> Option C fix -> durability review ->
v1.1.2 freeze -> Gate A 64K/128K -> F1 post-wrap -> F2 -> canary -> GREEN/BLOCKED`.

## 1. Why Option C (recorded rationale)

The owner's gate on Option A returned **negative**: the never-rewritten leading run is **O(context)**
(`BOUND-PROOF.md`: 6/12/24/48 pages -> run 6/12/24/48, fraction 1.0), so a write-side "refresh every anchor
page" is O(context) and forbidden. Option B (permanent pinning) was excluded by the owner.

Option C relocates live refs at reclaim time. **Its cost is bounded by the victim slot's live bytes
(<= ~64 MiB, one slot) and does not grow with chain length** — structurally bounded where A was not.
This is the property that makes it the correct fix rather than a workaround.

## 2. Owner-specified reclaim contract (binding; implementation must satisfy exactly)

1. Select victim slot `(slot, generation = g)`.
2. Before generation bump/reuse, enumerate **every currently-live index ref pointing into that victim
   generation**.
3. Relocate **only those live refs** into non-victim destination space: data bytes exact; opaque KV/Mamba
   payload semantics preserved; **dead/stale refs not copied**; cost bounded by victim-slot live bytes,
   max one slot (~64 MiB).
4. Publish relocated refs using the **existing** durability semantics, preferably
   `data write -> SET(s) -> BATCH_COMMIT/GROUP_COMMIT -> index publication`. **No new WAL protocol**
   unless strictly necessary.
5. Latest committed ref must win after live lookup, checkpoint, WAL replay, process restart.
6. Only after **every** live ref in the victim has a **durable published replacement** may the old victim
   be dropped / generation-bumped / reused.

**Crash invariants:** crash before relocation commit -> old refs authoritative; crash after commit before
retirement -> new committed refs win; crash after retirement/reuse -> only new refs reachable; **no state
may expose a ref to overwritten victim bytes**.

**Allocator safety:** never recursively reclaim the same victim; destination capacity secured BEFORE
touching the victim; if destination cannot be allocated -> **fail closed/backpressure, never recycle a live
victim**; preserve lock order (`_write_gate -> _lock`) and checkpoint interaction.

**Hybrid:** treat **all** live refs in the victim uniformly; do **not** special-case KV head pages;

**Non-goals (explicit):** no lookup-semantics change; no permanent pinning; no general compaction/GC; no
touching non-Extent backends.

## 3. Minimum tests (exactly A-G)

A. existing F1 reproducer: p0/p1/p2 survive wrap/reclaim, `batch_exists(chain) == full`.
B. multi-node/multi-key victim: all live refs relocate; dead refs do not.
C. generation: stale old-generation refs fail; new refs resolve exactly.
D. crash matrix: before commit / after commit-before-retire / after retire+reuse.
E. checkpoint + WAL replay: latest relocated refs win.
F. no-capacity case: relocation fails closed without corrupting/reusing the victim.
G. byte exactness: relocated KV + Mamba payloads identical.

## 4. Dispatched in parallel (3 independent children)

| task | owner | deliverable |
|---|---|---|
| `f1-optionC-reclaim-relocation-20260917` | coder | the minimum relocation implementation + tests A-G on a fresh tree `/tmp/opencode/v1.1.2-optionC-20260917/` + the two suite baselines (115 / 42) + extent-only inertness proof |
| `f1-optionC-durability-review-scaffold-20260917` | reviewer | independent adversarial review scaffold: `REVIEW-PROTOCOL.md`, `oracles/` (byte-exact KV+Mamba comparator, crash-matrix driver, generation oracle, live-but-dead discriminator, no-capacity oracle, restart/replay oracle), `RUNBOOK.md`, `THREAT-MODEL.md` — built clean-room from the frozen tree + contract, **not** from the implementer's tests |
| `v1.1.2-freeze-prep-20260917` | devops | freeze tooling: deterministic `manifest/TREE-SHA256.txt` generation, `chmod -R a-w` reproduction, launcher repin that makes "silently runs the wrong tree" impossible, hard preflight (`sglang.__file__` + `/proc/<pid>/environ`), unique per-run L3 namespace helper that refuses the shared store, and `FREEZE-RUNBOOK.md`. **Self-test: re-freezing v1.1 must reproduce `f0ca9206...97ab7` exactly.** |

Three is the concurrency cap for this Goal; implementation is the critical path.

## 5. Gate B validity

Owner: the existing **Gate B native 64K/128K performance PASS remains valid and does not need a re-run**
unless Option C materially changes its write path. Option C hooks the **slot-reclaim path**, not the
ordinary write path — to be confirmed from the implementation's changed-file list and hook site; if the
ordinary write/backup path is unchanged, Gate B stands. If the hook lands on the hot write path, that is a
**material change and must be reported as such** (it would also be a performance risk requiring Gate B
re-validation).

## 6. Final verdict rule (owner)

`GREEN` only if `Gate A + F1 post-wrap + F2 + existing Gate B + canary` all PASS. Otherwise report the
**single** blocker and stop. No other work.

## 7. State

* GPU **0 % / 1-4 MiB**, no servers, ports 30000/30164/30199 free, canonical lock `free` and untouched.
* Frozen v1.1 identity unchanged; no in-place modification of the original identity is permitted.
* Gate A's last result remains labelled **VALID INVALID / pre-fix baseline** only — no partial credit.
