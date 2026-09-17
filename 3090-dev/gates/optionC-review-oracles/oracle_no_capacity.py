#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: destination exhaustion must fail closed with the victim intact.

Contract point: "destination capacity secured BEFORE touching the victim; no
capacity -> fail closed / backpressure, never recycle a live victim."

Two exhaustion shapes:
  A. every slot full (no free tail anywhere);
  B. near-full and fragmented (total free < victim live bytes; the largest
     non-victim tail cannot hold the largest victim ref).

Falsification questions:
  NC-1  is the exhaustion real (packable == False by the tail model)?
  NC-2  are all victim live refs still resolvable with exact bytes afterwards?
  NC-3  when the write fails closed, is allocator state byte-identical?
  NC-4  does any key end up pointing at pre-bump victim generations?
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402


def build_fragmented_scenario(backend):
    """Victim slot 0 holds H(100) + L(7000); the only large destination tail
    (slot 1, 6584 B) cannot hold L, so relocation is infeasible."""
    writes = [
        ("flat", "H", H.content("H-big", 8000)),
        ("flat", "H", H.content("H-small", 100)),
        ("flat", "L", H.content("L", 7000)),
        ("flat", "s", H.content("s", 9800)),
        ("flat", "B1", H.content("B1", 16300)),
        ("flat", "B2", H.content("B2", 16300)),
    ]
    for kind, key, value in writes:
        if kind == "flat":
            if not backend.batch_set([key], [bytearray(value)]):
                raise RuntimeError(f"fragmented priming refused for {key}")
    return {
        "suffix": backend.config_suffix,
        "live": {"H": H.content("H-small", 100), "L": H.content("L", 7000)},
        "trigger_key": "FT",
        "trigger_value": H.content("FT-trigger", 1400),
        "trigger_kind": "flat",
    }


def evaluate(res, backend, scen, tag):
    obs = H.run_trigger(backend, scen)
    if not obs["victims"]:
        res.check(f"{tag}:victim-selected", "victim selected", None, "no generation bump -> INVALID")
        return
    vkeys = H.victim_live_keys(obs, scen)
    if not vkeys:
        res.check(f"{tag}:victim-live-refs", "victim held live refs", None, "none -> INVALID")
        return
    res.check(
        f"{tag}:victim-live-refs",
        "victim held live refs",
        True,
        f"{len(vkeys)} refs in {obs['victims']}",
    )
    res.check(
        f"{tag}:exhaustion-real",
        "is destination capacity genuinely exhausted (tail model)?",
        not obs["feasibility"]["packable"],
        f"feasibility={obs['feasibility']}",
        required=False,
    )

    lost, corrupted, in_old_victim = [], [], []
    for skey in vkeys:
        logical = H.strip_suffix(skey, scen["suffix"])
        expected = scen["live"].get(logical)
        if expected is None:
            continue
        got = H.verify_pre_key_bytes(backend, scen, skey, expected)
        if not got["resolves"]:
            lost.append(skey)
            continue
        if not got["bytes_ok"]:
            corrupted.append(skey)
        if got["ref"]["extent_id"] in obs["victims"] and got["ref"]["generation"] == obs["pre_gen"][
            got["ref"]["extent_id"]
        ]:
            in_old_victim.append(skey)

    res.check(
        f"{tag}:victim-intact",
        "are all victim live refs resolvable with exact bytes after exhaustion?",
        not lost and not corrupted,
        f"lost={lost} corrupted={corrupted}",
    )
    res.check(
        f"{tag}:no-old-generation-exposure",
        "does any key point at a pre-bump victim generation?",
        not in_old_victim,
        f"exposed={in_old_victim}",
    )
    if not obs["ok"]:
        unchanged = (
            obs["pre_index"] == obs["post_index"]
            and obs["pre_gen"] == obs["post_gen"]
            and obs["pre_slot_bytes"] == H.slot_bytes(backend)
        )
        res.check(
            f"{tag}:fail-closed-state-unchanged",
            "on fail-closed, is allocator state byte-identical?",
            unchanged,
            f"index_equal={obs['pre_index'] == obs['post_index']} "
            f"gen_equal={obs['pre_gen'] == obs['post_gen']}",
        )
    else:
        res.check(
            f"{tag}:reclaim-succeeded-without-capacity",
            "reclaim succeeded despite no packable tail capacity",
            not (lost or corrupted),
            "write returned True; acceptable only if every victim ref moved with exact bytes "
            "(a hole free-list may legitimately provide capacity)",
            required=False,
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    args = parser.parse_args(argv)
    H.load_tree(args.tree)
    res = H.OracleResult("oracle_no_capacity", args.mode)
    root = H.make_tmproot("oc-nocap-", args.keep_tmp)

    b = H.make_backend(os.path.join(root, "full"))
    scen = H.build_nocapacity_scenario(b)
    evaluate(res, b, scen, "full")
    b.close()

    b = H.make_backend(os.path.join(root, "frag"))
    scen = build_fragmented_scenario(b)
    evaluate(res, b, scen, "fragmented")
    b.close()

    res.note(
        "frozen-control expectation: full/fragmented victim-intact FAIL (the "
        "frozen allocator recycles the live victim and returns success)."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
