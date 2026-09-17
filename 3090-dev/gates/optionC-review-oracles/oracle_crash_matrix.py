#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: crash matrix at the three relocation durability boundaries.

Crash points (contract):
  CP1  crash BEFORE the relocation commit  -> old refs authoritative;
  CP2  crash AFTER commit, BEFORE victim retirement (generation bump) -> new
       committed refs win;
  CP3  crash AFTER retirement/reuse        -> only new refs reachable;
  and in ALL three: no reachable ref may be exposed to overwritten victim
  bytes.

Method (independent of the implementer's tests and of any internal hook the
implementation may add):

  1. A child process builds the capacity scenario with real writes, snapshots
     the pre-state (refs + exact-byte sha256) of every index entry, records
     the WAL frame stream produced by the reclaim (type/seq/offset/payload)
     through a wrapper around the existing ``_append_wal_frame``, then exits
     with ``os._exit`` so no clean-close checkpoint hides the WAL.
  2. The parent derives the three cut points from the frame stream:
       CP1 = just before the first BATCH_COMMIT/GROUP_COMMIT after the trigger;
       CP2 = just before the first DROP_SLOT at/after that commit;
       CP3 = full stream.
     It copies the on-disk store, truncates the active WAL segment at the cut
     (a torn-tail-free frame boundary), then opens a FRESH backend process.
  3. The fresh process replays the WAL and reports, for every pre-state key,
     whether it resolves and whether its bytes are sha256-exact.  The parent
     also folds the WAL independently (only committed batches/groups install;
     DROP_SLOT removes a slot's keys) and requires the replayed index to equal
     the folded expectation.

Falsification questions:
  CM-1  does the reclaim trigger actually exercise a relocation window?
  CM-2  is no DROP_SLOT of a live victim emitted before its replacement commit
        (durability ordering)?
  CM-3  CP1: do all old refs survive byte-exact (old refs authoritative)?
  CM-4  CP2: do all keys resolve byte-exact to the committed replacement?
  CM-5  CP3: is only the new committed state reachable, byte-exact?
  CM-6  in every cut, does the replayed index equal the independent fold?
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402

COMMIT_TYPES = (2, 3)  # BATCH_COMMIT, GROUP_COMMIT
DROP_TYPE = 4


# ---------------------------------------------------------------------------
# child modes
# ---------------------------------------------------------------------------

def _write_json(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())


def child_run(tree, store, meta_path) -> int:
    H.load_tree(tree)
    b = H.make_backend(store)
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    pre = {}
    for skey, ref in H.index_snapshot(b).items():
        logical = H.strip_suffix(skey, b.config_suffix)
        data = H.read_logical_flat(b, logical, ref["length"])
        pre[skey] = {
            "ref": ref,
            "logical": logical,
            "length": ref["length"],
            "sha256": None if data is None else H.sha256_hex(data),
        }
    log = H.install_frame_log(b)
    trigger_start = len(log)
    if scen["trigger_kind"] == "v1":  # not used here; keep flat
        raise RuntimeError("crash matrix expects a flat trigger")
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
    trigger_end = len(log)
    post_gen = H.generations_snapshot(b)
    post_index = H.index_snapshot(b)
    meta = {
        "pre": pre,
        "frame_log": log,
        "trigger_start": trigger_start,
        "trigger_end": trigger_end,
        "ok": ok,
        "suffix": b.config_suffix,
        "wal_generation": b._wal_generation,
        "post_gen": post_gen,
        "post_index": post_index,
        "scenario_trigger": scen["trigger_key"],
    }
    _write_json(meta_path, meta)
    os._exit(0)


def child_inspect(tree, store, meta_path, out_path) -> int:
    H.load_tree(tree)
    with open(meta_path) as fh:
        meta = json.load(fh)
    pre = meta["pre"]
    b = H.make_backend(store)
    post_gen = H.generations_snapshot(b)
    post_index = H.index_snapshot(b)
    results = {}
    for skey, info in pre.items():
        ref = H.lookup_ref(b, skey)
        rec = {"pre_ref": info["ref"], "resolves": ref is not None}
        if ref is not None:
            rec["ref"] = {
                "extent_id": ref.extent_id,
                "offset": ref.offset,
                "length": ref.length,
                "generation": ref.generation,
            }
            data = H.read_logical_flat(b, info["logical"], info["length"])
            rec["sha256"] = None if data is None else H.sha256_hex(data)
            rec["bytes_ok"] = data is not None and rec["sha256"] == info["sha256"]
        else:
            rec["ref"] = None
            rec["sha256"] = None
            rec["bytes_ok"] = False
        results[skey] = rec
    _write_json(
        out_path,
        {
            "post_gen": post_gen,
            "post_index": post_index,
            "results": results,
            "meta_suffix": meta["suffix"],
        },
    )
    # Do NOT close(): a clean close checkpoints/rotates the WAL and would
    # mutate the shared store for the next crash variant.  The process exit
    # releases the meta lock; the WAL fd is closed by the OS, leaving the
    # replayed bytes exactly as replayed.
    os._exit(0)


# ---------------------------------------------------------------------------
# independent WAL fold
# ---------------------------------------------------------------------------

def fold_expected(pre, frames, cut) -> dict:
    """Independent fold of committed batches/groups and DROP_SLOT."""
    installed = {k: dict(v["ref"]) for k, v in pre.items()}
    staged: dict = {}
    for fr in frames[:cut]:
        t = fr["type"]
        payload = base64.b64decode(fr["payload_b64"])
        if t == 1:  # SET
            p = H.meta_mod.decode_set_payload(payload)
            staged.setdefault(p.batch_id, []).extend((p, e) for e in p.entries)
        elif t == 2:  # BATCH_COMMIT
            bc = H.meta_mod.decode_batch_commit_payload(payload)
            for p, e in staged.get(bc.batch_id, []):
                installed[e.storage_key.decode("utf-8")] = {
                    "extent_id": e.extent_id,
                    "offset": e.offset,
                    "length": e.length,
                    "generation": e.generation,
                }
        elif t == 3:  # GROUP_COMMIT
            gc = H.meta_mod.decode_group_commit_payload(payload)
            for _bid, entries in staged.items():
                for p, e in entries:
                    if (
                        p.group_epoch == gc.group_epoch
                        and p.group_seq == gc.group_seq
                    ):
                        installed[e.storage_key.decode("utf-8")] = {
                            "extent_id": e.extent_id,
                            "offset": e.offset,
                            "length": e.length,
                            "generation": e.generation,
                        }
        elif t == DROP_TYPE:  # DROP_SLOT
            ds = H.meta_mod.decode_drop_slot_payload(payload)
            for k in [k for k, r in installed.items() if r["extent_id"] == ds.slot]:
                installed.pop(k, None)
    return installed


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def _invoke(tree, args) -> int:
    cmd = [sys.executable, os.path.abspath(__file__), "--tree", tree] + list(args)
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "999")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"child {args} failed rc={proc.returncode}\nstdout={proc.stdout[-4000:]}\n"
            f"stderr={proc.stderr[-4000:]}"
        )
    return proc.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    parser.add_argument("--_child-run", nargs=2, metavar=("STORE", "META"))
    parser.add_argument("--_child-inspect", nargs=3, metavar=("STORE", "META", "OUT"))
    args = parser.parse_args(argv)

    if args._child_run:
        store, meta = args._child_run
        return child_run(args.tree, store, meta)
    if args._child_inspect:
        store, meta, out = args._child_inspect
        return child_inspect(args.tree, store, meta, out)

    H.load_tree(args.tree)
    res = H.OracleResult("oracle_crash_matrix", args.mode)
    root = H.make_tmproot("oc-crash-", args.keep_tmp)
    run_store = os.path.join(root, "run_store")
    os.makedirs(run_store)
    meta_path = os.path.join(root, "run_meta.json")
    try:
        _invoke(args.tree, ["--_child-run", run_store, meta_path])
    except Exception as exc:
        res.error = str(exc)
        return res.finish(args.out, argv)

    with open(meta_path) as fh:
        meta = json.load(fh)
    log = meta["frame_log"]
    trig = meta["trigger_start"]
    suffix = meta["suffix"]

    if not meta["ok"]:
        res.check(
            "CM-1:window-exercised",
            "did the reclaim trigger commit (relocation window exercised)?",
            None,
            "trigger write returned False -> no relocation frames; CP1..CP3 would be vacuous (INVALID)",
        )
        return res.finish(args.out, argv)

    after = [i for i in range(trig, len(log))]
    first_commit = next((i for i in after if log[i]["type"] in COMMIT_TYPES), None)
    first_drop = next(
        (i for i in after if log[i]["type"] == DROP_TYPE and (first_commit is None or i >= first_commit)),
        None,
    )
    drop_before_commit = [
        i for i in after if log[i]["type"] == DROP_TYPE and (first_commit is None or i < first_commit)
    ]
    gens = {fr.get("wal_generation") for fr in log}
    if len(gens) != 1:
        res.check("CM-0:single-wal-segment", "frame stream lives in one WAL segment", None, f"gens={gens}")
        return res.finish(args.out, argv)

    known_types = {1, 2, 3, 4, 5, 6}
    unknown = sorted({fr["type"] for fr in log} - known_types)
    res.check(
        "CM-0:no-new-wal-protocol",
        "does the reclaim use only existing WAL frame types (no new protocol)?",
        not unknown,
        f"unknown_frame_types={unknown} (contract forbids a new WAL protocol)",
    )

    res.check(
        "CM-1:window-exercised",
        "did the reclaim trigger produce relocation frames?",
        first_commit is not None,
        f"frames_after_trigger={len(after)} first_commit={first_commit} first_drop={first_drop} "
        f"order={[H.frame_name(log[i]['type']) for i in after]}",
    )
    res.check(
        "CM-2:no-drop-before-replacement-commit",
        "is no live-victim DROP_SLOT emitted before its replacement commit?",
        not drop_before_commit,
        f"drops_before_first_commit={drop_before_commit} "
        f"order={[H.frame_name(log[i]['type']) for i in after]}",
    )

    cuts = {
        "CP1-before-commit": first_commit if first_commit is not None else len(log),
        "CP2-after-commit-before-retire": first_drop if first_drop is not None else len(log),
        "CP3-after-retire-reuse": len(log),
    }
    # Geometry validation pins the manifest to the data file's inode, so the
    # crash variants must be exercised in-place on the same store: save the
    # full WAL bytes and restore them before each cut (same inode).
    wal_seg = H.meta_mod.segment_path(run_store, suffix, meta["wal_generation"])
    with open(wal_seg, "rb") as fh:
        wal_full = fh.read()

    def restore_full_wal():
        with open(wal_seg, "r+b") as fh:
            fh.write(wal_full)
            fh.truncate(len(wal_full))
            fh.flush()
            os.fsync(fh.fileno())

    expectations = {}
    for name, cut in cuts.items():
        # CM-6 independent fold
        expectations[name] = fold_expected(meta["pre"], log, cut)

        restore_full_wal()
        if cut < len(log):
            off = log[cut]["offset"]
            size = os.path.getsize(wal_seg)
            if 0 < off <= size:
                os.truncate(wal_seg, off)
        out_path = os.path.join(root, name, "inspect.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            _invoke(
                args.tree,
                ["--_child-inspect", run_store, meta_path, out_path],
            )
        except Exception as exc:
            res.check(f"{name}:reopen", "fresh process reopened and replayed the cut WAL", None, str(exc))
            continue
        with open(out_path) as fh:
            ins = json.load(fh)

        lost, corrupted, ref_mismatch, gen_bad = [], [], [], []
        for skey, rec in ins["results"].items():
            if not rec["resolves"]:
                lost.append(skey)
                continue
            if not rec.get("bytes_ok"):
                corrupted.append(skey)
            exp = expectations[name].get(skey)
            if exp != rec["ref"]:
                ref_mismatch.append({"key": skey, "expected": exp, "actual": rec["ref"]})
            if rec["ref"]["generation"] != ins["post_gen"][rec["ref"]["extent_id"]]:
                gen_bad.append(skey)
        res.check(
            f"{name}:refs-reachable-bytes-exact",
            "do the expected refs resolve with sha256-exact bytes after replay?",
            not lost and not corrupted,
            f"lost={lost} corrupted={corrupted}",
            evidence={"post_gen": ins["post_gen"], "expected_keys": sorted(expectations[name])},
        )
        res.check(
            f"{name}:fold-equals-replay",
            "does the replayed index equal the independent WAL fold?",
            not ref_mismatch,
            f"mismatches={ref_mismatch}",
        )
        res.check(
            f"{name}:generation-current",
            "does every reachable ref carry its slot's post-replay generation?",
            not gen_bad,
            f"stale={gen_bad}",
        )

    res.note(
        "INVALID discipline: a cut that truncates before any relocation frame "
        "(no commit/drop emitted) does not exercise a crash window and is "
        "reported via CM-1, not as PASS."
    )
    res.note(
        "frozen-control expectation: CM-2 FAIL (DROP_SLOT precedes the SET/"
        "BATCH_COMMIT of the replacement) and CP1/CP3 refs-reachable FAIL."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
