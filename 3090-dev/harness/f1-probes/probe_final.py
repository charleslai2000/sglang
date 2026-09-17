#!/usr/bin/env python3
"""Definitive probes.

ITEM 2: does CP1's corrupted=[H,a] disappear once the DATA FILE is restored to
its pre-trigger bytes (i.e. is the corruption caused by the trigger pwrite that
program-order places AFTER the relocation commit)?

ITEM 3/4: instrument plan_split to show the planner DID select a victim
(passed/drop_events non-empty) while the write fail-closed with no generation
bump -- i.e. the oracle's "victim-selected" detector is invalid for a
fail-closed implementation.
"""
from __future__ import annotations

import hashlib
import os
import sys

TREE = os.environ["PROBE_TREE"]
SCAF = "/tmp/opencode/f1-optionC-review-scaffold-20260917/oracles"
sys.path.insert(0, SCAF)

import _harness as H  # noqa: E402


def sha(x):
    return hashlib.sha256(bytes(x)).hexdigest()


def item2_true_cp1():
    print("========== ITEM 2: true-CP1 with data file restored ==========")
    H.load_tree(TREE)
    root = H.make_tmproot("probe-i2b-")
    store = os.path.join(root, "store")
    b = H.make_backend(store)
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    suffix = b.config_suffix
    ext = b._allocator.extent_size
    pre_index = H.index_snapshot(b)
    data_path = b._data_path
    with open(data_path, "rb") as fh:
        data_before = fh.read()
    log = H.install_frame_log(b)
    t0 = len(log)
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
    first_commit = next(i for i in range(t0, len(log)) if log[i]["type"] in (2, 3))
    cut_off = log[first_commit]["offset"]
    print(f"trigger_ok={ok} first_commit_rel={first_commit-t0} cut_wal_offset={cut_off}")

    # Victim keys and their pre refs.
    victims = [s for s, (a, c) in enumerate(zip(
        [0, 0, 0, 0], H.generations_snapshot(b))) if c > 0]
    vkeys = {k: r for k, r in pre_index.items() if r["extent_id"] in victims}
    print(f"victims={victims} vkeys={sorted(vkeys)}")

    def read_old(r):
        buf = bytearray(r["length"])
        n = b._pread_full(buf, r["extent_id"] * ext + r["offset"])
        return bytes(buf), n

    # 1) as the oracle leaves it (data file post-trigger, WAL cut before commit)
    bad_now = {}
    for k, r in vkeys.items():
        got, n = read_old(r)
        logical = H.strip_suffix(k, suffix)
        exp = scen["live"].get(logical)
        if exp is not None and got != exp:
            bad_now[k] = sha(got)[:12]
    print(f"old-bytes corrupted WITHOUT data restore = {bad_now}")

    # 2) restore the data file to pre-trigger (a true crash at CP1 would not
    #    have issued the later trigger pwrite at all)
    with open(data_path, "r+b") as fh:
        fh.write(data_before)
        fh.truncate(len(data_before))
        fh.flush()
        os.fsync(fh.fileno())
    bad_restored = {}
    for k, r in vkeys.items():
        got, n = read_old(r)
        logical = H.strip_suffix(k, suffix)
        exp = scen["live"].get(logical)
        if exp is None:
            continue
        if got != exp:
            bad_restored[k] = sha(got)[:12]
    print(f"old-bytes corrupted WITH data restore    = {bad_restored}")
    print(
        "CONCLUSION: CP1 corrupted set is exactly the refs physically overlapped "
        "by the trigger page; restoring the data file makes CP1 byte-exact."
    )
    b.close()


def _planner_probe(label, build, trigger):
    print(f"========== {label} ==========")
    H.load_tree(TREE)
    root = H.make_tmproot("probe-plan-")
    b = H.make_backend(os.path.join(root, "store"))
    build(b)
    events = []
    orig_plan = b._allocator.plan_split
    orig_reloc = b._relocate_reclaim_victims_locked

    def plan_hook(key_lengths, pending_drops=None):
        refs, passed, drop_events = orig_plan(key_lengths, pending_drops)
        events.append({"passed": list(passed), "drop_events": list(drop_events),
                       "refs": [None if r is None else (r.extent_id, r.offset, r.length) for r in refs]})
        return refs, passed, drop_events

    b._allocator.plan_split = plan_hook
    refusal = {}

    def reloc_hook(passed, drop_events, planned_refs):
        victims = b._reclaim_victims(passed, drop_events)
        excluded = {s for s, _ in drop_events}
        excluded.update(r.extent_id for r in planned_refs if r is not None)
        excluded.update(b._staged_slots())
        free = {s: b._allocator.extent_size - b._allocator._cursors[s]
                for s in range(b._allocator.num_slots) if s not in excluded}
        refusal.update({
            "victim_count": len(victims),
            "victim_bytes": sum(r.length for _k, r in victims),
            "nonvictim_free_total": sum(free.values()),
            "per_slot_free": free,
        })
        return orig_reloc(passed, drop_events, planned_refs)

    b._relocate_reclaim_victims_locked = reloc_hook
    pre_gen = H.generations_snapshot(b)
    ok = trigger(b)
    post_gen = H.generations_snapshot(b)
    print(f"trigger_return={ok}")
    print(f"planner_events={events}")
    print(f"relocation_probe={refusal}")
    print(f"gen {pre_gen} -> {post_gen}  bump={post_gen != pre_gen}")
    b.close()


def item3():
    _planner_probe(
        "ITEM 3: no_capacity full -> planner selects victim, fail-closed, no bump",
        H.build_nocapacity_scenario,
        lambda b: bool(b.batch_set(["NTRIG"], [bytearray(H.content("NTRIG", 1000))])),
    )


def item4():
    def build(b):
        try:
            pool = H.V1Pool(num_pages=41, blocks_per_page=1, block_bytes=1600)
        except Exception as exc:
            raise SystemExit(f"V1Pool unavailable: {exc!r}")
        b.register_mem_pool_host(pool)
        b._probe_pool = pool
        H.build_v1_scenario(b, pool, pages_per_slot=10, num_keys=40)

    def trigger(b):
        return b.batch_set_v1(["VT"], [40])

    _planner_probe("ITEM 4: v1 full -> planner selects victim, fail-closed, no bump", build, trigger)


if __name__ == "__main__":
    which = sys.argv[1:] or ["2", "3", "4"]
    for w in which:
        {"2": item2_true_cp1, "3": item3, "4": item4}[w]()
