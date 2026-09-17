#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SYNTHETIC self-test for the oracle mechanism (NOT product evidence).

Purpose: prove the oracles are not vacuously always-FAIL.  It constructs:
  * feasibility classifications (packable True/False);
  * a *manually* relocated post-state that the byte comparator must accept, and
    a corrupted copy that it must reject;
  * a synthetic WAL frame stream folded by the crash-matrix expectation fold.

This does NOT execute the product's relocation path and must never be cited as
production evidence; it validates the review harness only.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    args = parser.parse_args(argv)
    H.load_tree(args.tree)
    res = H.OracleResult("selftest_oracle_logic", args.mode)

    # 1. feasibility
    ok_feas = H.feasible_relocation({1: 10000}, {0}, {0: [{"length": 8000}, {"length": 1000}]})
    bad_feas = H.feasible_relocation({1: 5000}, {0}, {0: [{"length": 8000}]})
    res.check(
        "ST-1:feasibility",
        "does the capacity classifier separate packable from non-packable?",
        ok_feas["packable"] and not bad_feas["packable"],
        f"packable={ok_feas} other={bad_feas}",
    )

    # 2. byte comparator on a manually relocated (synthetic) post-state
    root = H.make_tmproot("oc-selftest-", args.keep_tmp)
    b = H.make_backend(os.path.join(root, "store"))
    key = "PK"
    data = H.content("PK", 1000)
    assert b.batch_set([key], [bytearray(data)])
    suffix = b.config_suffix
    alloc = b._allocator
    extent = alloc.extent_size
    # place identical bytes at slot1 offset0 and repoint the index there,
    # bumping the victim slot exactly as a relocation would.
    old_gen = alloc._generations[0]
    with b._lock:
        alloc._index.pop(key + suffix, None)
        alloc._slot_keys[0].discard(key + suffix)
        alloc._slot_bytes[0] -= 1000
        alloc._generations[0] = old_gen + 1
        alloc._cursors[0] = 0
        alloc._index[key + suffix] = H.ExtentRef(1, 0, 1000, alloc._generations[1])
        alloc._slot_keys[1].add(key + suffix)
        alloc._slot_bytes[1] += 1000
        alloc._cursors[1] = 1000
    with open(b._data_path, "r+b") as fh:
        fh.write(data)
        fh.seek(extent)
        fh.write(data)
        fh.flush()
    scen = {"suffix": suffix, "live": {key: data}, "trigger_key": "x", "trigger_value": b"", "trigger_kind": "flat"}
    good = H.verify_pre_key_bytes(b, scen, key + suffix, data)
    res.check(
        "ST-2:comparator-accepts-exact",
        "does the byte comparator accept byte-exact relocated payload?",
        good["resolves"] and good["bytes_ok"],
        f"{good}",
    )
    # corrupt the destination bytes: comparator must reject
    with open(b._data_path, "r+b") as fh:
        fh.seek(extent)
        fh.write(b"\x00" * 1000)
    bad = H.verify_pre_key_bytes(b, scen, key + suffix, data)
    res.check(
        "ST-3:comparator-rejects-corrupt",
        "does the byte comparator reject same-length corrupted payload?",
        bad["resolves"] and (not bad["bytes_ok"]) and bad["length_ok"],
        f"{bad}",
    )
    b.close()

    # 3. crash-matrix independent fold
    try:
        meta = H.meta_mod
        pre = {
            "K": {"ref": {"extent_id": 0, "offset": 0, "length": 10, "generation": 0}},
            "V": {"ref": {"extent_id": 0, "offset": 10, "length": 10, "generation": 0}},
        }
        set_p = meta.encode_set_payload(
            meta.SetPayload(
                group_epoch=b"\x00" * 16,
                group_seq=0,
                batch_id=7,
                member_index=0,
                member_count=1,
                entries=[
                    meta.SetEntry(
                        storage_key=b"K",
                        extent_id=1,
                        offset=0,
                        length=10,
                        generation=0,
                        component=0,
                    )
                ],
            )
        )
        commit_p = meta.encode_batch_commit_payload(meta.BatchCommitPayload(7, 1))
        drop_p = meta.encode_drop_slot_payload(meta.DropSlotPayload(0, 1))
        import base64 as _b64

        frames = [
            {"type": 1, "payload_b64": _b64.b64encode(set_p).decode()},
            {"type": 2, "payload_b64": _b64.b64encode(commit_p).decode()},
            {"type": 4, "payload_b64": _b64.b64encode(drop_p).decode()},
        ]
        before_commit = fold_stub(pre, frames, cut=1)
        after_commit = fold_stub(pre, frames, cut=2)
        after_drop = fold_stub(pre, frames, cut=3)
        res.check(
            "ST-4:fold-semantics",
            "does the independent fold model uncommitted/committed/dropped order?",
            before_commit["K"]["extent_id"] == 0
            and after_commit["K"]["extent_id"] == 1
            and after_drop["K"]["extent_id"] == 1
            and "V" in after_commit
            and "V" not in after_drop,
            f"cut1={before_commit} cut2={after_commit} cut3={after_drop}",
        )
    except Exception as exc:
        res.check("ST-4:fold-semantics", "independent fold executed", None, f"exception: {exc!r}")

    res.note("SYNTHETIC self-test only; not evidence about any production implementation.")
    return res.finish(args.out, argv)


def fold_stub(pre, frames, cut):
    import base64

    installed = {k: dict(v["ref"]) for k, v in pre.items()}
    staged = {}
    for fr in frames[:cut]:
        t = fr["type"]
        payload = base64.b64decode(fr["payload_b64"])
        if t == 1:
            p = H.meta_mod.decode_set_payload(payload)
            staged.setdefault(p.batch_id, []).extend((p, e) for e in p.entries)
        elif t == 2:
            bc = H.meta_mod.decode_batch_commit_payload(payload)
            for _p, e in staged.get(bc.batch_id, []):
                installed[e.storage_key.decode()] = {
                    "extent_id": e.extent_id,
                    "offset": e.offset,
                    "length": e.length,
                    "generation": e.generation,
                }
        elif t == 4:
            ds = H.meta_mod.decode_drop_slot_payload(payload)
            for k in [k for k, r in installed.items() if r["extent_id"] == ds.slot]:
                installed.pop(k, None)
    return installed


if __name__ == "__main__":
    sys.exit(main())
