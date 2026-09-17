#!/usr/bin/env python3
"""Airtight probes for item 2 (corruption source), item 3 (no_capacity), item 4 (v1)."""
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


def item2():
    print("========== ITEM 2: CP1 corruption source ==========")
    H.load_tree(TREE)
    root = H.make_tmproot("probe-i2-")
    b = H.make_backend(os.path.join(root, "store"))
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    h_exp = scen["live"]["H"]
    a_exp = scen["live"]["a"]
    trig = scen["trigger_value"]
    pre = H.index_snapshot(b)
    log = H.install_frame_log(b)
    t0 = len(log)
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(trig)]))
    post = H.index_snapshot(b)
    print(f"trigger_ok={ok}")
    print(f"frames_after_trigger={[H.frame_name(log[i]['type']) for i in range(t0, len(log))]}")
    # Directly pread the OLD victim byte ranges from the data file (slot 0).
    ext = b._allocator.extent_size
    for key, off, ln, exp in (("H", 8000, 100, h_exp), ("a", 8100, 1000, a_exp)):
        buf = bytearray(ln)
        n = b._pread_full(buf, 0 * ext + off)
        exp_s = sha(exp)
        trig_slice = bytes(trig[off : off + ln]) if off + ln <= len(trig) else None
        print(
            f"  slot0[{off},{off+ln}) pread={n}B "
            f"sha={sha(buf)} expected_H/a={exp_s} "
            f"equals_trigger_slice={trig_slice is not None and sha(buf)==sha(trig_slice)} "
            f"equals_expected={sha(buf)==exp_s}"
        )
    # Show the post-index old refs for H/a were relocated (so they no longer point at slot0)
    print(f"  post-index H={post.get('H'+scen['suffix'])}")
    print(f"  post-index a={post.get('a'+scen['suffix'])}")
    b.close()


def item3():
    print("========== ITEM 3: no_capacity fail-closed invisibility ==========")
    H.load_tree(TREE)
    root = H.make_tmproot("probe-i3-")
    b = H.make_backend(os.path.join(root, "full"))
    scen = H.build_nocapacity_scenario(b)
    pre_index = H.index_snapshot(b)
    pre_gen = H.generations_snapshot(b)
    pre_bytes = H.slot_bytes(b)
    log = H.install_frame_log(b)
    t0 = len(log)
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
    post_index = H.index_snapshot(b)
    post_gen = H.generations_snapshot(b)
    frames = [H.frame_name(log[i]["type"]) for i in range(t0, len(log))]
    print(f"trigger_ok={ok} frames={frames}")
    print(f"gen {pre_gen} -> {post_gen}")
    print(
        f"state_unchanged: index={pre_index == post_index} "
        f"gen={pre_gen == post_gen} slot_bytes={pre_bytes == H.slot_bytes(b)}"
    )
    # victim refs still exact?
    bad = []
    for k, exp in scen["live"].items():
        sk = k + scen["suffix"] if not k.endswith(".mamba") else k + scen["suffix"]
        # mamba not authored for nocapacity; keys n###
        pass
    for i in range(64):
        k = f"n{i:03d}"
        got = H.read_logical_flat(b, k, 1000)
        if got != scen["live"][k]:
            bad.append(k)
    print(f"victim_live_refs_corrupted={bad}")
    clear = b._allocator._slot_keys[0]
    print(f"slot0_live_key_count={len(clear)}")
    b.close()


def item4():
    print("========== ITEM 4: v1 scenario geometry ==========")
    H.load_tree(TREE)
    root = H.make_tmproot("probe-i4-")
    try:
        pool = H.V1Pool(num_pages=41, blocks_per_page=1, block_bytes=1600)
    except Exception as exc:
        print(f"V1Pool unavailable: {exc!r}")
        return
    b = H.make_backend(os.path.join(root, "v1store"))
    b.register_mem_pool_host(pool)
    try:
        scen = H.build_v1_scenario(b, pool, pages_per_slot=10, num_keys=40)
        pre_gen = H.generations_snapshot(b)
        cursors = list(b._allocator._cursors)
        used = b._allocator.used_bytes
        ext = b._allocator.extent_size
        free = {s: ext - cursors[s] for s in range(b._allocator.num_slots)}
        log = H.install_frame_log(b)
        t0 = len(log)
        obs = H.run_trigger(b, scen)
        frames = [H.frame_name(log[i]["type"]) for i in range(t0, len(log))]
        print(
            f"page_bytes={pool.page_bytes} file={b._file_size} ext={ext} "
            f"slots={b._allocator.num_slots} used={used} cursors={cursors} free={free}"
        )
        print(f"pre_gen={pre_gen} post_gen={obs['post_gen']} victims={obs['victims']}")
        print(f"trigger_ok={obs['ok']} frames={frames}")
        vkeys = H.victim_live_keys(obs, scen)
        print(f"victim_key_count={len(vkeys)} feasibility={obs['feasibility']}")
    finally:
        b.close()


if __name__ == "__main__":
    which = sys.argv[1:] or ["2", "3", "4"]
    for w in which:
        {"2": item2, "3": item3, "4": item4}[w]()
