#!/usr/bin/env python3
"""CPU-only offline WAL forensics using the TREE UNDER TEST's own code.

Modes
-----
identity
    Read the store's manifest/wal.current/segment list and report the manifest
    state (checkpoint_lsn, wal_floor, wal_active_gen, n_entries, next_slot,
    geometry) plus on-disk sizes.  Used by F2 to prove checkpoint rotation
    (wal_floor advanced, manifest grew) with the tree's own parser.

membership
    Rebuild the allocator from manifest + every WAL segment in
    ``[wal_floor .. wal_active_gen]`` with the tree's ``replay_records``, then:
      * membership of the requested page-hash window (n_present / first_absent /
        contiguous run),
      * the REAL ``ExtentFileBackend.batch_exists`` + verbatim
        ``_storage_hit_query`` loop,
      * the chain-head key's full SET / DROP_SLOT history (whether the head was
        re-SET after the last drop of a slot it ever lived in).
      * allocator slot state (cursors, generations, live bytes, empty slots,
        per-slot free tail) so a harness can PROVE a circular-reclaim/precondition
        instead of inferring it from cumulative write bytes,
      * DROP_SLOT frame history per slot (the generation bump),
      * for ``--victim-slot S`` (or the head key's current slot): the live refs
        and live *target-window* refs the slot holds, and the relocation
        headroom outside it.

This script is READ-ONLY w.r.t. the store: it never writes, repairs, rotates,
clears or unlinks anything.  A snapshot copy must be analysed, never a live
store that a server is concurrently writing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import types


def _emit(out_path, obj):
    text = json.dumps(obj, indent=2, default=str)
    if out_path:
        tmp = out_path + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(text + "\n")
        os.replace(tmp, out_path)
    print(text)


def _read_only_replay(em, namespace, suffix):
    manifest = em.manifest_path(namespace, suffix)
    current = em.current_path(namespace, suffix)
    if not os.path.exists(manifest):
        raise SystemExit(f"manifest missing: {manifest}")
    state = em.read_manifest(manifest)
    active_gen = em.read_current(current)
    gens = list(range(int(state.wal_floor), int(active_gen) + 1))
    segment_frames = []
    segments = []
    for gen in gens:
        path = em.segment_path(namespace, suffix, gen)
        if not os.path.exists(path):
            segments.append({"generation": gen, "path": path,
                             "missing": True})
            raise SystemExit(f"WAL segment missing: {path}")
        frames = em.iter_segment_frames(path, active=(gen == active_gen))
        segment_frames.append(frames)
        segments.append({
            "generation": gen,
            "bytes": os.path.getsize(path),
            "n_frames": len(frames),
            "torn_tail": None if frames.torn_tail is None
            else frames.torn_tail.last_valid_offset,
            "active": gen == active_gen,
        })
    replay = em.replay_records(segment_frames, state,
                               num_slots=state.num_slots)
    return state, active_gen, segment_frames, replay, segments


def _replay_slot_state(em, segment_frames, num_slots):
    """Rebuild per-slot cursors/next_slot by replaying frames in WAL order.

    ``_cursors`` is runtime state (the manifest does not carry it), but it is a
    deterministic function of the frame stream: a SET advances its slot's cursor
    to ``offset + length``; a DROP_SLOT resets that slot's cursor to 0.  The
    live index alone is NOT enough -- a slot can hold dead space (cursor high,
    few live refs), which is exactly what makes a circular reclaim's relocation
    feasible or not, so the offline proof must reproduce it.
    """
    cursors = [0] * int(num_slots)
    next_slot = 0
    n_set = 0
    n_drop = 0
    for frames in segment_frames:
        for frame in frames:
            if frame.frame_type == em.FRAME_SET:
                try:
                    decoded = em.decode_set_payload(frame.payload)
                except Exception:
                    continue
                n_set += 1
                for entry in decoded.entries:
                    slot = int(entry.extent_id)
                    if not 0 <= slot < int(num_slots):
                        continue
                    end = int(entry.offset) + int(entry.length)
                    if end > cursors[slot]:
                        cursors[slot] = end
                    next_slot = slot
            elif frame.frame_type == em.FRAME_DROP_SLOT:
                try:
                    decoded = em.decode_drop_slot_payload(frame.payload)
                except Exception:
                    continue
                slot = int(decoded.slot)
                if 0 <= slot < int(num_slots):
                    cursors[slot] = 0
                    n_drop += 1
    return {"cursors": cursors, "next_slot": next_slot,
            "n_set_frames": n_set, "n_drop_slot_frames": n_drop}


def mode_identity(em, args):
    namespace, suffix = args.namespace, args.suffix
    manifest = em.manifest_path(namespace, suffix)
    state = em.read_manifest(manifest)
    current_path = em.current_path(namespace, suffix)
    active_gen = em.read_current(current_path)
    out = {
        "mode": "identity",
        "tree": args.tree,
        "namespace": namespace,
        "suffix": suffix,
        "manifest_bytes": os.path.getsize(manifest),
        "wal_current": active_gen,
        "manifest_state": {
            "checkpoint_lsn": state.checkpoint_lsn,
            "wal_floor": state.wal_floor,
            "wal_active_gen": state.wal_active_gen,
            "n_entries": len(state.entries),
            "next_slot": state.next_slot,
            "extent_size": state.extent_size,
            "file_size": state.file_size,
            "num_slots": state.num_slots,
            "file_uuid": state.file_uuid.hex(),
            "namespace_epoch": state.namespace_epoch.hex(),
            "data_dev": state.data_dev,
            "data_ino": state.data_ino,
        },
        "wal_segments": [],
        "data_bytes": None,
    }
    for name in sorted(os.listdir(namespace)):
        if name.startswith(f"hicache.data{suffix}"):
            out["data_bytes"] = os.path.getsize(os.path.join(namespace, name))
        if name.startswith(f"hicache.meta{suffix}.wal.") and \
                not name.endswith(".current"):
            gen = int(name.rsplit(".", 1)[1])
            out["wal_segments"].append(
                {"generation": gen,
                 "bytes": os.path.getsize(os.path.join(namespace, name))})
    out["wal_segments"].sort(key=lambda r: r["generation"])
    return out


def mode_membership(em, ExtentAllocator, ExtentRef, ExtentFileBackend,
                    get_hash_str, STORAGE_BATCH_SIZE, args):
    namespace, suffix = args.namespace, args.suffix
    state, active_gen, segment_frames, replay, segments = _read_only_replay(
        em, namespace, suffix)

    index = {}
    for entry in replay.entries:
        try:
            key = entry.storage_key.decode("utf-8")
        except UnicodeDecodeError:
            continue
        index[key] = ExtentRef(entry.extent_id, entry.offset, entry.length,
                               entry.generation)
    alloc = ExtentAllocator(int(state.extent_size), int(state.num_slots))
    alloc._generations = list(replay.generations)
    alloc._index = index
    slot_state = _replay_slot_state(em, segment_frames, state.num_slots)
    alloc._cursors = list(slot_state["cursors"])
    alloc._next_slot = slot_state["next_slot"]
    for key, ref in index.items():
        alloc._slot_keys[ref.extent_id].add(key)
        alloc._slot_bytes[ref.extent_id] += int(ref.length)

    shim = types.SimpleNamespace(_allocator=alloc, _lock=threading.Lock())
    shim.config_suffix = suffix
    shim._storage_key = ExtentFileBackend._storage_key.__get__(shim)

    def real_batch_exists(keys):
        return ExtentFileBackend.batch_exists(shim, keys, None)

    def hit_query(keys):  # verbatim cache_controller.py storage-hit loop
        cnt = 0
        for start in range(0, len(keys), STORAGE_BATCH_SIZE):
            batch = keys[start:start + STORAGE_BATCH_SIZE]
            n = real_batch_exists(batch)
            cnt += n
            if n < len(batch):
                return cnt
        return cnt

    out = {
        "mode": "membership",
        "tree": args.tree,
        "namespace": namespace,
        "suffix": suffix,
        "manifest_state": {
            "checkpoint_lsn": state.checkpoint_lsn,
            "wal_floor": state.wal_floor,
            "wal_active_gen": state.wal_active_gen,
            "n_entries": len(state.entries),
            "next_slot": state.next_slot,
            "extent_size": state.extent_size,
            "file_size": state.file_size,
            "num_slots": state.num_slots,
        },
        "wal_segments": segments,
        "replay": {
            "n_entries": len(replay.entries),
            "seen_max_seq": replay.seen_max_seq,
            "generations_set": sorted(set(replay.generations)),
            "dropped_tail": None if replay.dropped_tail is None
            else replay.dropped_tail.last_valid_offset,
        },
        "STORAGE_BATCH_SIZE": STORAGE_BATCH_SIZE,
    }

    if not args.ids_json:
        out["error"] = "membership mode requires --ids-json"
        return out
    payload = json.load(open(args.ids_json))
    ids = payload["ids"] if isinstance(payload, dict) else payload
    hashes = get_hash_str([int(t) for t in ids], None, page_size=1)
    if isinstance(hashes, str):
        hashes = [hashes]
    n_pages = len(hashes)
    window_len = (int(args.query_window_len)
                  if args.query_window_len is not None else n_pages - 1)
    window_len = max(0, min(window_len, n_pages))
    window = list(hashes[:window_len])
    out["prompt"] = {"n_ids": len(ids), "n_hashes": n_pages,
                     "query_window_len": window_len,
                     "window_from_page0": True}

    def lookup_hit(h):
        return alloc.lookup(shim._storage_key(h)) is not None

    present = [i for i, h in enumerate(window) if lookup_hit(h)]
    first_absent = next((i for i in range(len(window)) if not lookup_hit(window[i])),
                        None)
    runs = []
    i = 0
    while i < len(window):
        if not lookup_hit(window[i]):
            i += 1
            continue
        j = i
        while j + 1 < len(window) and lookup_hit(window[j + 1]):
            j += 1
        runs.append({"start": i, "len": j - i + 1})
        i = j + 1
    longest = max(runs, key=lambda r: r["len"]) if runs else {"start": None,
                                                             "len": 0}
    out["membership"] = {
        "n_present": len(present),
        "n_absent": len(window) - len(present),
        "first_absent_index": first_absent,
        "first_present_index": present[0] if present else None,
        "longest_run_start": longest["start"],
        "longest_run_len": longest["len"],
        "n_runs": len(runs),
        "runs_head": runs[:8],
    }

    # ---- allocator slot state (precondition-proof surface, FIX 2/FIX 5) ----
    num_slots = int(alloc.num_slots)
    extent_size = int(alloc.extent_size)
    cursors = [int(c) for c in alloc._cursors]
    slot_bytes = [int(b) for b in alloc._slot_bytes]
    generations = [int(g) for g in alloc._generations]
    live_slots = [s for s in range(num_slots)
                  if alloc._slot_keys[s] or slot_bytes[s] > 0]
    empty_slots = [s for s in range(num_slots)
                   if s not in set(live_slots) and cursors[s] == 0]
    free_tails = [extent_size - cursors[s] for s in range(num_slots)]
    max_tail = max(free_tails) if free_tails else 0
    out["allocator_state"] = {
        "num_slots": num_slots,
        "extent_size": extent_size,
        "used_bytes": int(alloc.used_bytes),
        "free_bytes": num_slots * extent_size - int(alloc.used_bytes),
        "next_slot": int(alloc._next_slot),
        "cursors": cursors,
        "slot_bytes": slot_bytes,
        "generations": generations,
        "live_slots": live_slots,
        "empty_slots": empty_slots,
        "free_tail_bytes": free_tails,
        "max_free_tail_bytes": max_tail,
        "max_free_tail_slot": (free_tails.index(max_tail)
                               if free_tails else None),
        "cursor_source": "WAL frame replay (SET advances, DROP_SLOT resets)",
        "slot_state_replay": slot_state,
    }

    # ---- DROP_SLOT frame history (the generation bump) ----
    drop_history = []
    for frames in segment_frames:
        for frame in frames:
            if frame.frame_type != em.FRAME_DROP_SLOT:
                continue
            try:
                decoded = em.decode_drop_slot_payload(frame.payload)
            except Exception:
                continue
            drop_history.append({"seq": frame.seq, "slot": int(decoded.slot),
                                 "new_generation": int(decoded.new_generation)})
    per_slot_max_gen = {}
    for rec in drop_history:
        per_slot_max_gen[rec["slot"]] = max(
            per_slot_max_gen.get(rec["slot"], 0), rec["new_generation"])
    out["drop_slot_frames"] = {
        "n": len(drop_history),
        "history_head": drop_history[:8],
        "history_tail": drop_history[-8:],
        "per_slot_max_new_generation": per_slot_max_gen,
        "slots_dropped": sorted(per_slot_max_gen),
    }
    out["predicate"] = {
        "window_from_page0_hits": hit_query(window),
        "window_from_page0_requested": len(window),
        "first_batch_returned": real_batch_exists(
            window[:STORAGE_BATCH_SIZE]) if window else 0,
    }

    # head history: SET frames for page 0 and DROP_SLOT frames for its slots
    head_hash = hashes[0] if hashes else None
    head_key = (head_hash + suffix) if head_hash else None
    set_history = []
    drop_history = []
    n_set_frames = 0
    n_drop_frames = 0
    for frames in segment_frames:
        for frame in frames:
            if frame.frame_type == em.FRAME_SET:
                n_set_frames += 1
                try:
                    decoded = em.decode_set_payload(frame.payload)
                except Exception:
                    continue
                for entry in decoded.entries:
                    try:
                        key = entry.storage_key.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if key == head_key:
                        set_history.append({
                            "seq": frame.seq, "slot": entry.extent_id,
                            "offset": entry.offset, "length": entry.length,
                            "generation": entry.generation})
            elif frame.frame_type == em.FRAME_DROP_SLOT:
                n_drop_frames += 1
                try:
                    decoded = em.decode_drop_slot_payload(frame.payload)
                except Exception:
                    continue
                drop_history.append({"seq": frame.seq, "slot": decoded.slot,
                                     "new_generation": decoded.new_generation})
    head_slots = sorted({r["slot"] for r in set_history})
    head_last_set_seq = max((r["seq"] for r in set_history), default=None)
    drop_seqs_for_head_slots = [d["seq"] for d in drop_history
                                if d["slot"] in set(head_slots)]
    head_slot_last_drop_seq = (max(drop_seqs_for_head_slots)
                               if drop_seqs_for_head_slots else None)
    head_refreshed = (
        head_last_set_seq is not None
        and (head_slot_last_drop_seq is None
             or head_last_set_seq > head_slot_last_drop_seq))
    out["head"] = {
        "head_hash": head_hash,
        "head_storage_key": head_key,
        "n_set_frames": n_set_frames,
        "n_drop_slot_frames": n_drop_frames,
        "head_set_history_n": len(set_history),
        "head_set_history_head": set_history[:6],
        "head_set_history_tail": set_history[-6:],
        "head_slots": head_slots,
        "head_last_set_seq": head_last_set_seq,
        "head_slot_last_drop_seq": head_slot_last_drop_seq,
        "head_refreshed_after_drop": head_refreshed,
        "head_present_in_rebuilt_index": bool(
            head_key and alloc.lookup(head_key) is not None),
    }

    # ---- target-window slot placement + explicit victim-slot proof ----------
    window_keys = [shim._storage_key(h) for h in window]
    window_key_set = set(window_keys)
    window_refs = {}
    for key in window_keys:
        ref = alloc.lookup(key)
        if ref is not None:
            window_refs[key] = ref
    histogram = {}
    for ref in window_refs.values():
        histogram[ref.extent_id] = histogram.get(ref.extent_id, 0) + 1
    head_ref = window_refs.get(head_key)
    out["target_slots"] = {
        "n_target_refs": len(window_refs),
        "slot_histogram": {str(k): v for k, v in sorted(histogram.items())},
        "head_current_slot": (head_ref.extent_id if head_ref else None),
        "head_current_generation": (head_ref.generation if head_ref else None),
        "head_current_offset": (head_ref.offset if head_ref else None),
        "head_current_length": (head_ref.length if head_ref else None),
    }
    victim_slot = args.victim_slot
    victim_auto = victim_slot is None
    if victim_slot is None and head_ref is not None:
        victim_slot = head_ref.extent_id

    def slot_detail(v: int) -> dict:
        v = int(v)
        v_keys = sorted(alloc._slot_keys[v])
        v_live = [k for k in v_keys
                  if alloc.lookup(k) is not None
                  and alloc._index[k].extent_id == v]
        v_live_bytes = sum(int(alloc._index[k].length) for k in v_live)
        v_target = [k for k in v_live if k in window_key_set]
        v_target_bytes = sum(int(alloc._index[k].length) for k in v_target)
        headroom = max((free_tails[s] for s in range(num_slots) if s != v),
                       default=0)
        return {
            "slot": v,
            "generation": generations[v],
            "cursor": cursors[v],
            "free_tail_bytes": free_tails[v],
            "slot_keys_total": len(v_keys),
            "live_refs": len(v_live),
            "live_bytes": v_live_bytes,
            "target_live_refs": len(v_target),
            "target_live_bytes": v_target_bytes,
            "target_live_head_present": bool(
                head_key and head_key in set(v_target)),
            "holds_live_target_refs": len(v_target) > 0,
            "relocation_headroom_bytes": headroom,
            "reclaim_relocatable": headroom >= v_live_bytes,
            "drop_frames": [r for r in drop_history if r["slot"] == v],
        }

    out["target_slot_details"] = {
        str(s): slot_detail(s) for s in sorted(histogram)}
    victim = None
    if victim_slot is not None and 0 <= int(victim_slot) < num_slots:
        victim = slot_detail(victim_slot)
        victim["auto_selected_from_head"] = bool(victim_auto)
    out["victim"] = victim
    if victim is not None and not victim["reclaim_relocatable"]:
        out["victim"]["fail_closed_reason"] = (
            "no destination capacity outside victim slot "
            f"{victim['slot']}: relocation headroom "
            f"{victim['relocation_headroom_bytes']} B < victim live bytes "
            f"{victim['live_bytes']} B; the circular reclaim must refuse the "
            "write (ExtentFileBackend fail-closed)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True,
                    choices=["identity", "membership"])
    ap.add_argument("--tree", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--suffix", required=True)
    ap.add_argument("--ids-json")
    ap.add_argument("--query-window-len", type=int)
    ap.add_argument("--victim-slot", type=int, default=None,
                    help="slot to report live/live-target refs and reclaim "
                         "headroom for (default: the head key's current slot)")
    ap.add_argument("--out")
    args = ap.parse_args()

    tree = args.tree.rstrip("/")
    sys.path.insert(0, os.path.join(tree, "src", "python"))
    import sglang  # noqa: E402
    if not sglang.__file__.startswith(tree + "/src/"):
        raise SystemExit(
            f"editable-install landmine: sglang.__file__={sglang.__file__} "
            f"not under {tree}/src/")
    from sglang.srt.mem_cache.utils import get_hash_str  # noqa: E402
    from sglang.srt.mem_cache.storage.extent import extent_metadata as em  # noqa: E402
    from sglang.srt.mem_cache.storage.extent.extent_allocator import (  # noqa: E402
        ExtentAllocator, ExtentRef)
    from sglang.srt.mem_cache.storage.extent.extent_file_backend import (  # noqa: E402
        ExtentFileBackend)
    from sglang.srt.mem_cache.hicache_storage import (  # noqa: E402
        STORAGE_BATCH_SIZE)

    if args.mode == "identity":
        out = mode_identity(em, args)
    else:
        out = mode_membership(em, ExtentAllocator, ExtentRef, ExtentFileBackend,
                              get_hash_str, STORAGE_BATCH_SIZE, args)
    out["sglang_file"] = sglang.__file__
    _emit(args.out, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
