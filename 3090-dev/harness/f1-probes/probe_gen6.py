#!/usr/bin/env python3
"""Diagnostic probes for item 1 (GEN-6) and item 2 (CP1).

Read-only wrt candidate/frozen/oracles/evidence. Writes nothing except stdout.
"""
from __future__ import annotations

import os
import sys

TREE = os.environ["PROBE_TREE"]
SCAF = "/tmp/opencode/f1-optionC-review-scaffold-20260917/oracles"
sys.path.insert(0, SCAF)

import _harness as H  # noqa: E402


def churn_probe(*, with_scenario: bool, max_size=None, min_free=None, label=""):
    H.load_tree(TREE)
    assert H.tree_info()["python_root"].startswith(TREE), H.tree_info()
    root = H.make_tmproot("probe-gen6-")
    kwargs = {}
    if max_size is not None:
        kwargs["max_size"] = max_size
    if min_free is not None:
        kwargs["min_free_space"] = min_free
    b = H.make_backend(os.path.join(root, "store"), **kwargs)

    # capture refusal events from the relocation path
    refusals = []
    orig = b._relocate_reclaim_victims_locked

    def hooked(passed, drop_events, planned_refs):
        victims = b._reclaim_victims(passed, drop_events)
        if victims:
            vbytes = sum(r.length for _k, r in victims)
            excluded = {s for s, _ in drop_events}
            excluded.update(r.extent_id for r in planned_refs if r is not None)
            excluded.update(b._staged_slots())
            free = {
                s: b._allocator.extent_size - b._allocator._cursors[s]
                for s in range(b._allocator.num_slots)
                if s not in excluded
            }
            refusals.append(
                {
                    "passed": list(passed),
                    "drop_slots": sorted(excluded),
                    "victim_bytes": vbytes,
                    "nonvictim_free": free,
                    "nonvictim_free_total": sum(free.values()),
                }
            )
        return orig(passed, drop_events, planned_refs)

    b._relocate_reclaim_victims_locked = hooked

    scen = H.build_capacity_scenario(b, mixed_mamba=False) if with_scenario else None
    if scen is not None:
        H.run_trigger(b, scen)

    churn = []
    for i in range(1200):
        key = f"churn{i:04d}"
        churn.append(bool(b.batch_set([key], [bytearray(H.content(key, 1000))])))
    used = b._allocator.used_bytes
    gens = list(b._allocator._generations)
    cursors = list(b._allocator._cursors)
    print(
        f"[{label}] successes={sum(churn)}/1200 tail200={sum(churn[-200:])} "
        f"used={used} file={b._file_size} max_size={b._max_size_bytes} "
        f"min_free={b._min_free_bytes} gens={gens} cursors={cursors} "
        f"refusal_events={len(refusals)}"
    )
    if refusals:
        r0 = refusals[0]
        print(
            f"    first_refusal: victims_in={r0['drop_slots']} "
            f"victim_bytes={r0['victim_bytes']} "
            f"nonvictim_free_total={r0['nonvictim_free_total']} "
            f"per_slot={r0['nonvictim_free']}"
        )
        print(f"    distict_nonvictim_free_totals="
              f"{sorted({x['nonvictim_free_total'] for x in refusals})[:10]}")
    b.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "fresh"):
        churn_probe(with_scenario=False, label="fresh/no-eviction")
        churn_probe(with_scenario=True, label="post-capacity/no-eviction")
    if mode in ("all", "gc"):
        churn_probe(with_scenario=False, max_size="60Ki", label="fresh/max_size=60Ki")
        churn_probe(with_scenario=True, max_size="60Ki", label="post-capacity/max_size=60Ki")
    if mode in ("all", "gc-small"):
        churn_probe(with_scenario=False, max_size="20Ki", label="fresh/max_size=20Ki")
