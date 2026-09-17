#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: generation/staleness semantics across victim reclaim.

Contract points:
  * crash/retire invariants ultimately rely on the generation guard: a ref
    captured before a generation bump must never resolve;
  * the replacement ref must carry the destination slot's current generation;
  * slot generations are monotonic and a victim's old generation must remain
    unreachable (no key may be exposed to overwritten victim bytes);
  * after the victim is reused again, the relocated refs are unaffected.

Falsification questions:
  GEN-1  do all pre-reclaim victim refs fail re-verification afterwards?
  GEN-2  does every surviving ref carry its slot's current generation?
  GEN-3  are generations monotonic and strictly bumped on victims?
  GEN-4  is the victim's pre-bump generation unreachable in the index?
  GEN-5  does the relocated data survive a subsequent reuse of the victim slot?
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
    res = H.OracleResult("oracle_generation", args.mode)
    root = H.make_tmproot("oc-generation-", args.keep_tmp)
    b = H.make_backend(os.path.join(root, "store"))
    scen = H.build_capacity_scenario(b, mixed_mamba=False)
    obs = H.run_trigger(b, scen)

    if not obs["victims"]:
        res.check("GEN-0", "victim selected", None, "no generation bump -> INVALID")
        b.close()
        return res.finish(args.out, argv)
    vkeys = H.victim_live_keys(obs, scen)
    if not vkeys:
        res.check("GEN-0b", "victim had live refs", None, "no live refs -> INVALID")
        b.close()
        return res.finish(args.out, argv)

    pre_gen = obs["pre_gen"]
    post_gen = obs["post_gen"]
    victims = set(obs["victims"])

    # GEN-1: every pre ref must now fail verify (stale).
    stale_bad = []
    for skey, pre_ref in vkeys.items():
        ref_obj = H.ExtentRef(
            pre_ref["extent_id"], pre_ref["offset"], pre_ref["length"], pre_ref["generation"]
        )
        with b._lock:
            ok = b._allocator.verify([skey], [ref_obj])[0]
        if ok:
            stale_bad.append(skey)
    res.check(
        "GEN-1:pre-refs-invalidated",
        "do all pre-reclaim victim refs fail re-verification after the bump?",
        not stale_bad,
        f"still-verifying={stale_bad}",
    )

    # GEN-2: surviving refs carry current slot generation.
    gen_bad = []
    for skey in vkeys:
        ref = H.lookup_ref(b, skey)
        if ref is None:
            continue
        if ref.generation != post_gen[ref.extent_id]:
            gen_bad.append((skey, ref.generation, post_gen[ref.extent_id]))
    res.check(
        "GEN-2:survivor-generation-current",
        "does every surviving victim ref carry its slot's current generation?",
        not gen_bad,
        f"bad={gen_bad}",
    )

    # GEN-3: monotonic; victims strictly bumped.
    regress = [(s, pre_gen[s], post_gen[s]) for s in range(len(pre_gen)) if post_gen[s] < pre_gen[s]]
    victims_bumped = all(post_gen[s] > pre_gen[s] for s in victims)
    res.check(
        "GEN-3:monotonic",
        "are slot generations monotonic, with victim slots strictly bumped?",
        (not regress) and victims_bumped,
        f"regress={regress} victims={sorted(victims)} pre={pre_gen} post={post_gen}",
    )
    # GEN-3b: no recursive reclaim of the same victim inside one trigger.
    multi = [(s, pre_gen[s], post_gen[s]) for s in range(len(pre_gen)) if post_gen[s] - pre_gen[s] > 1]
    res.check(
        "GEN-3b:single-step-bump",
        "was no victim slot bumped more than once by a single reclaim?",
        not multi,
        f"multi_bump={multi} (a nested reclaim of the same victim violates A1)",
    )

    # GEN-4: no key resolves to a victim's pre-bump generation.
    exposed = []
    for skey, ref in obs["post_index"].items():
        if ref["extent_id"] in victims and ref["generation"] == pre_gen[ref["extent_id"]]:
            exposed.append((skey, ref))
    res.check(
        "GEN-4:old-generation-unreachable",
        "is the victim's pre-bump generation unreachable in the index?",
        not exposed,
        f"exposed={exposed}",
    )

    # GEN-5: force a further reuse of a victim slot; relocated refs unaffected.
    pre_survive = {
        skey: H.verify_pre_key_bytes(b, scen, skey, scen["live"][H.strip_suffix(skey, scen["suffix"])])
        for skey in vkeys
        if H.strip_suffix(skey, scen["suffix"]) in scen["live"]
    }
    before = {k: v["got_sha256"] for k, v in pre_survive.items()}
    reuse_targets = sorted(victims)
    reused = False
    for i in range(256):
        key = f"reuse{i:03d}"
        val = H.content(key, 1000)
        ok = b.batch_set([key], [bytearray(val)])
        ref = H.lookup_ref(b, key + scen["suffix"])
        if ref is not None and ref.extent_id in victims:
            reused = True
            break
    after = {
        k: H.verify_pre_key_bytes(b, scen, k, scen["live"][H.strip_suffix(k, scen["suffix"])])
        for k in vkeys
        if H.strip_suffix(k, scen["suffix"]) in scen["live"]
    }
    changed = [
        k
        for k in after
        if after[k]["got_sha256"] != before.get(k)
        or not after[k]["resolves"]
    ]
    res.check(
        "GEN-5:stable-across-victim-reuse",
        "do relocated refs survive a subsequent reuse of the victim slot?",
        (not changed) if reused else None,
        f"reused_victim={reused} changed={changed}",
    )

    # GEN-6: no permanent pinning / permanent backpressure under churn.
    churn = []
    for i in range(1200):
        key = f"churn{i:04d}"
        churn.append(bool(b.batch_set([key], [bytearray(H.content(key, 1000))])))
    tail_ok = any(churn[-200:])
    res.check(
        "GEN-6:no-permanent-pinning",
        "does the write path keep making progress under churn (no pinned deadlock)?",
        tail_ok,
        f"successes={sum(churn)}/{len(churn)} tail200_success={sum(churn[-200:])}",
    )

    b.close()
    res.note(
        "frozen-control expectation: GEN-1 PASS (drop invalidates), GEN-2/GEN-4 "
        "vacuous (refs lost), GEN-5 FAIL because the relocated refs never existed."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
