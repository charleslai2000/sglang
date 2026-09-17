#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: restart / WAL-replay / checkpoint durability of relocated refs.

Contract points:
  * latest committed ref wins after live lookup, checkpoint, WAL replay and
    restart;
  * crash after relocation commit but before retirement: new refs win;
  * group durability preserves the KV/Mamba component contract;
  * a checkpoint taken during relocation must not expose a half-moved state.

Falsification questions:
  RS-1  (checkpointed) after a clean close + checkpoint, does a FRESH process
        resolve every victim key byte-exact to a non-victim location?
  RS-2  (wal-only) after an unclean exit (no close/checkpoint), does a fresh
        process replay the WAL and resolve every victim key byte-exact?
  RS-3  is the Mamba component restored from the durable metadata?
  RS-4  does the ``batch_exists`` consecutive-prefix contract still hold
        (lookup semantics non-regression)?
  RS-5  under a tiny checkpoint threshold (worker rotating during the
        relocation), is nothing lost?
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402


def _write_json(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())


def run_child(tree, store, out, close_mode) -> int:
    H.load_tree(tree)
    b = H.make_backend(store)
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    pre = {}
    for skey, ref in H.index_snapshot(b).items():
        logical = H.strip_suffix(skey, b.config_suffix)
        data = H.read_logical_flat(b, logical, ref["length"])
        pre[skey] = {
            "logical": logical,
            "length": ref["length"],
            "sha256": None if data is None else H.sha256_hex(data),
            "ref": ref,
            "component": b._components.get(skey),
        }
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
    post_gen = H.generations_snapshot(b)
    meta = {
        "pre": pre,
        "suffix": b.config_suffix,
        "trigger_ok": ok,
        "post_gen": post_gen,
        "live": {k: H.sha256_hex(v) for k, v in scen["live"].items()},
        # batch_exists is the KV consecutive-prefix surface.  Mamba is a
        # separate component key and is checked by the component/byte rows.
        "kv_chain": ["H", "a", "b"],
    }
    if close_mode:
        b.close()
        _write_json(out, meta)
        return 0
    _write_json(out, meta)
    os._exit(0)


def inspect_child(tree, store, meta_path, out) -> int:
    H.load_tree(tree)
    with open(meta_path) as fh:
        meta = json.load(fh)
    b = H.make_backend(store)
    post_gen = H.generations_snapshot(b)
    results = {}
    for skey, info in meta["pre"].items():
        ref = H.lookup_ref(b, skey)
        rec = {"resolves": ref is not None, "ref": None, "bytes_ok": False, "component": None}
        if ref is not None:
            rec["ref"] = {
                "extent_id": ref.extent_id,
                "offset": ref.offset,
                "length": ref.length,
                "generation": ref.generation,
            }
            data = H.read_logical_flat(b, info["logical"], info["length"])
            rec["bytes_ok"] = data is not None and H.sha256_hex(data) == info["sha256"]
        rec["component"] = b._components.get(skey)
        rec["gen_current"] = (
            ref is not None and ref.generation == post_gen[ref.extent_id]
        )
        results[skey] = rec
    chain = meta.get("kv_chain") or []
    batch_exists = int(b.batch_exists(chain)) if chain else None
    _write_json(
        out,
        {
            "post_gen": post_gen,
            "results": results,
            "batch_exists_chain": batch_exists,
            "chain": chain,
        },
    )
    os._exit(0)


def _invoke(tree, args) -> None:
    cmd = [sys.executable, os.path.abspath(__file__), "--tree", tree] + list(args)
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "999")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"child {args} rc={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-3000:]}"
        )


def evaluate_variant(res, root, tree, name, close_mode, meta_suffix=""):
    store = os.path.join(root, name + meta_suffix)
    os.makedirs(store, exist_ok=True)
    meta_path = os.path.join(root, name + meta_suffix + ".json")
    insp_path = os.path.join(root, name + meta_suffix + ".inspect.json")
    _invoke(tree, ["--_child-run", store, meta_path, "close" if close_mode else "no-close"])
    with open(meta_path) as fh:
        meta = json.load(fh)
    if not meta["trigger_ok"]:
        res.check(f"{name}:trigger", "reclaim trigger committed", None, "trigger returned False -> INVALID")
        return
    _invoke(tree, ["--_child-inspect", store, meta_path, insp_path])
    with open(insp_path) as fh:
        ins = json.load(fh)

    lost, corrupted, gen_bad, comp_bad, in_victim = [], [], [], [], []
    mamba_code = H.meta_mod.component_from_pool_name(H.PoolName.MAMBA)
    for skey, rec in ins["results"].items():
        if not rec["resolves"]:
            lost.append(skey)
            continue
        if not rec["bytes_ok"]:
            corrupted.append(skey)
        if not rec["gen_current"]:
            gen_bad.append(skey)
        logical = H.strip_suffix(skey, meta["suffix"])
        if logical.endswith(".mamba") and rec["component"] != mamba_code:
            comp_bad.append({"key": skey, "component": rec["component"], "want": mamba_code})
    res.check(
        f"{name}:refs-byte-exact-after-restart",
        "does every victim key resolve byte-exact after restart/replay?",
        not lost and not corrupted,
        f"lost={lost} corrupted={corrupted}",
    )
    res.check(
        f"{name}:generation-consistent",
        "do restored refs carry their slot's restored generation?",
        not gen_bad,
        f"stale={gen_bad}",
    )
    res.check(
        f"{name}:mamba-component-restored",
        "is the Mamba component restored from durable metadata?",
        not comp_bad,
        f"bad={comp_bad}",
    )
    res.check(
        f"{name}:batch-exists-contract",
        "does batch_exists still return the consecutive-prefix length?",
        ins["batch_exists_chain"] == len(ins["chain"]),
        f"chain={ins['chain']} batch_exists={ins['batch_exists_chain']}",
    )


def run_checkpoint_load(res, root, tree):
    """RS-5: tiny checkpoint threshold; worker rotates during relocation."""
    store = os.path.join(root, "ckptload")
    os.makedirs(store, exist_ok=True)
    b = H.make_backend(store, wal_checkpoint_bytes=1)
    try:
        scen = H.build_capacity_scenario(b, mixed_mamba=True)
        pre = {}
        for skey, ref in H.index_snapshot(b).items():
            logical = H.strip_suffix(skey, b.config_suffix)
            data = H.read_logical_flat(b, logical, ref["length"])
            pre[skey] = {"logical": logical, "length": ref["length"], "sha256": H.sha256_hex(data) if data else None}
        ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
        for i in range(200):
            key = f"cl{i:03d}"
            b.batch_set([key], [bytearray(H.content(key, 1000))])
        if not ok:
            res.check("checkpoint-load:trigger", "trigger committed", None, "trigger returned False")
            return
        bad = []
        for skey, info in pre.items():
            data = H.read_logical_flat(b, info["logical"], info["length"])
            if data is None or H.sha256_hex(data) != info["sha256"]:
                bad.append(skey)
        res.check(
            "checkpoint-load:refs-byte-exact",
            "under a rotating checkpoint worker, are relocated refs exact?",
            not bad,
            f"bad={bad}",
        )
    except Exception as exc:
        res.check("checkpoint-load:scenario", "checkpoint-load scenario executed", None, f"exception: {exc!r}")
    finally:
        b.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    parser.add_argument("--_child-run", nargs=3, metavar=("STORE", "OUT", "CLOSE"))
    parser.add_argument("--_child-inspect", nargs=3, metavar=("STORE", "META", "OUT"))
    args = parser.parse_args(argv)

    if args._child_run:
        store, out, close_mode = args._child_run
        return run_child(args.tree, store, out, close_mode == "close")
    if args._child_inspect:
        store, meta, out = args._child_inspect
        return inspect_child(args.tree, store, meta, out)

    H.load_tree(args.tree)
    res = H.OracleResult("oracle_restart_replay", args.mode)
    root = H.make_tmproot("oc-restart-", args.keep_tmp)
    try:
        evaluate_variant(res, root, args.tree, "checkpointed", close_mode=True)
        evaluate_variant(res, root, args.tree, "walonly", close_mode=False)
        run_checkpoint_load(res, root, args.tree)
    except Exception as exc:
        res.error = str(exc)
        return res.finish(args.out, argv)
    res.note(
        "frozen-control expectation: refs-byte-exact-after-restart FAILS "
        "(the replayed index has no ref for the recycled victim keys)."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
