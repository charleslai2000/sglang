# p2io-coder e23 — node-104 orphan (drop_subtree_no_host tombstone-subtree skip)

## status

done

## artifacts

- `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py` — `drop_subtree_no_host` descendant walk fixed.
  - Before: a descendant with `forced_miss_tombstone=True` hit `continue`, skipping the tombstone's ENTIRE subtree. If the tombstone still carried live host-only children (a subtree never detached by `detach_miss_dropped`, or re-attached), those children were orphaned when the drop root was removed: they stayed in the arena + `evictable_host_leaves` + `full_host_duplicates` + aux-mamba `host_lru_lists` while becoming unreachable from the root → node-104 shutdown sanity shape (`H-leaf extra / Duplicate ghost / stale host_leaves / mamba host LRU`).
  - After: the walk appends the tombstone to a `tombstones` list, then `stack.extend(cur.children.values())` so its live host-only children are still collected, freed via `_release_all_component_layers`, and deregistered via `_remove_leaf_from_parent` (bottom-up, in the same pass as normal descendants). The dead tombstone itself is skipped for the host-only release/assert (it holds no KV), and is deregistered via `_remove_leaf_from_parent` after its subtree is freed. Root cause: the e16 belt-and-suspenders skip (`continue`) was too coarse — it must skip the dead node, not its live subtree.
- `3090-dev/test_storage_regression.py` — new `DropToMissEvictionOrderRegressionTests.test_ancestor_drop_does_not_orphan_tombstone_host_children`: builds the exact node-104 shape (host-only L3-durable child `c` under a forced-miss tombstone inside a D-leaf subtree), runs `drop_subtree_no_host`, asserts `c` is not reachable, not in arena, and in none of the four sets; tombstone itself also unregistered.

## evidence

- **RED** — temporarily reverted the fix to the buggy `continue` skip: `test_ancestor_drop_does_not_orphan_tombstone_host_children` FAILS at `AssertionError: True is not false` on `not node_exists(c.id)` (orphan), exit=1.
- **GREEN** — restored fixed walk (verified on disk, no TEMP/BUGGY markers):
  - `DropToMissEvictionOrderRegressionTests`: `Ran 5 tests ... OK` (3 e16 + 1 e17 + 1 e23), exit=0.
  - Affected classes (StorageBackedHollowEvictionTests, RestoreChainHollowEvictionTests, DropToMissSafetyValveTests, RevokeMissDurableClearTests, L3DurabilityWritePathTests): `Ran 15 tests ... OK`, exit=0.
  - Full gate: `python3 -m unittest discover -s 3090-dev -p 'test_*.py' -t 3090-dev` → `Ran 328 tests in 0.112s / OK` (327 + 1 e23), exit=0.
  - Registered: `test/registered/unit/mem_cache/test_extent_file_backend_unit.py` → `Ran 71 tests in 57.729s / OK`, exit=0.
  - `python3 -m py_compile` on both changed files → OK.
  - Anti-pattern scan: no TEMP-RED / BUGGY markers, no TODO/FIXME in the touched region.

## summary

Node 104 is a host-only L3-durable restored anchor orphaned by `drop_subtree_no_host`: the e16 tombstone-skip in the descendant walk `continue`d on a forced-miss tombstone, skipping the tombstone's whole subtree, so a live host-only child under it (never detached by `detach_miss_dropped`, or re-attached) survived in the arena with all four host registrations but unreachable from the root — firing the node-104 shutdown sanity check. Fix: still descend into the tombstone's children (free + deregister them) while skipping the dead node itself, then deregister the tombstone. RED→GREEN demonstrated on a node-104-shape repro; zero e16/e17/Z3/reserve/RH/instrumentation regression.

## followups

- Integration/perf (for orchestrator to schedule under tester): re-run a live M4T under the same host-pressure write_back regime and confirm shutdown `sanity_check` reports 0 violations across the four registers (node-104 shape gone).
- Node 104's live trace shows a durable host-only child attached under a forced-miss tombstone at drop time — worth confirming the exact live ordering (whether the child was never detached or was re-attached) if this shape recurs; the fix is robust to both.

## open_issues

- None new. Pre-existing: `BaseEvictionResult.__del__` "undrained values" AssertionError warnings on undrained single-test results (harness behavior, not from this change; full gate run is clean).
- The scope note's system-level capacity issue (8G Z3 flood 1001, host 22k/68k tokens) is out of scope and untouched.
