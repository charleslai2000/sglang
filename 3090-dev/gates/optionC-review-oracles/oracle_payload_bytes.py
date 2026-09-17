#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: byte-exact preservation of relocated KV *and* Mamba payloads.

Contract points:
  * relocation must move ONLY live refs out of the victim generation;
  * bytes must be exact (opaque payload, not re-interpreted);
  * KV and Mamba refs in the same victim slot are treated uniformly;
  * destination capacity must be secured before the victim is touched
    (with capacity available the write must succeed and preserve);
  * relocation cost is bounded by the victim live bytes (+ the new page),
    never O(file/context).

Falsification questions answered:
  PB-1  did the trigger actually select a victim slot with live refs?
  PB-2  is every victim live ref still resolvable after the reclaim?
  PB-3  do the relocated bytes match the pre-relocation bytes by checksum?
  PB-4  are the relocated refs outside the victim slot (non-victim space)?
  PB-5  Mamba component metadata preserved (not silently downgraded to KV)?
  PB-6  are unrelated (non-victim) keys untouched?
  PB-7  is the write I/O bounded by victim live bytes (not a full rewrite)?
  PB-8  does the real v1 zero-copy surface preserve bytes too?

Negative control (frozen tree) is expected to FAIL PB-2/PB-3/PB-4: the frozen
allocator simply drops the victim slot.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402


def _component_of(backend, storage_key):
    comp = getattr(backend, "_components", None)
    if comp is None:
        return None
    return comp.get(storage_key)


def run_scenario(backend, scen, res, tag):
    obs = H.run_trigger(backend, scen)

    if not obs["victims"]:
        res.check(
            f"{tag}:victim-selected",
            "did the trigger select (generation-bump) a victim slot?",
            None,
            "no generation bump observed -> reclaim window not reached (INVALID, not PASS)",
        )
        return obs
    res.check(f"{tag}:victim-selected", "victim slot selected", True, f"victims={obs['victims']}")

    vkeys = H.victim_live_keys(obs, scen)
    if not vkeys:
        res.check(
            f"{tag}:victim-has-live-refs",
            "did the victim slot hold live refs before the reclaim?",
            None,
            f"victim(s) {obs['victims']} had no live index refs pre-trigger (INVALID)",
        )
        return obs
    res.check(
        f"{tag}:victim-has-live-refs",
        "victim slot held live refs before reclaim",
        True,
        f"{len(vkeys)} live refs in victim(s) {obs['victims']}",
        evidence={k: v for k, v in vkeys.items()},
    )

    feas = obs["feasibility"]
    if feas["packable"]:
        res.check(
            f"{tag}:write-succeeds-with-capacity",
            "with non-victim capacity, does the reclaim write succeed?",
            bool(obs["ok"]),
            f"ok={obs['ok']} feasibility={feas}",
        )
    else:
        res.check(
            f"{tag}:write-succeeds-with-capacity",
            "capacity classification",
            True,
            f"no packable non-victim capacity by tail model -> fail-closed allowed: feasibility={feas}",
            required=False,
        )

    # PB-2/PB-3/PB-4/PB-5: per victim key
    lost, corrupted, in_victim, gen_bad, comp_bad = [], [], [], [], []
    details = {}
    for skey, pre_ref in vkeys.items():
        # recover expected bytes by logical key (mamba keys appear as "m.mamba")
        logical = H.strip_suffix(skey, scen["suffix"])
        expected = scen["live"].get(logical)
        if expected is None:
            # not a key this oracle authored: skip byte comparison but still report
            details[skey] = {"no_expected_bytes": True}
            continue
        got = H.verify_pre_key_bytes(backend, scen, skey, expected)
        if not got["resolves"]:
            lost.append(skey)
        else:
            if not got["bytes_ok"]:
                corrupted.append(skey)
            if got["ref"]["extent_id"] in obs["victims"]:
                in_victim.append(skey)
            if got["ref"]["generation"] != obs["post_gen"][got["ref"]["extent_id"]]:
                gen_bad.append(skey)
        details[skey] = got

    res.check(
        f"{tag}:live-refs-survive",
        "is every victim live ref still resolvable after reclaim?",
        not lost,
        f"lost={lost}",
    )
    res.check(
        f"{tag}:bytes-checksum-exact",
        "do relocated bytes match pre-relocation bytes by sha256 (not just length)?",
        not corrupted and not lost,
        f"corrupted={corrupted} lost={lost}",
        evidence=details,
    )
    res.check(
        f"{tag}:dest-non-victim",
        "are relocated refs in non-victim space?",
        not in_victim and not lost,
        f"still-in-victim={in_victim} lost={lost}",
    )
    res.check(
        f"{tag}:generation-current",
        "does every surviving ref carry its slot's current generation?",
        not gen_bad,
        f"stale-generation={gen_bad}",
    )

    # PB-5 component preservation.  The pre-trigger component mapping is not
    # captured by run_trigger, so re-derive it from the scenario: Mamba
    # component keys end in ".mamba" + suffix.
    for skey in vkeys:
        logical = H.strip_suffix(skey, scen["suffix"])
        if logical.endswith(".mamba"):
            want = H.meta_mod.component_from_pool_name(H.PoolName.MAMBA)
            got_c = _component_of(backend, skey)
            if got_c != want:
                comp_bad.append((skey, got_c, want))
    res.check(
        f"{tag}:mamba-component-preserved",
        "is the Mamba component preserved through relocation (not re-emitted as KV)?",
        not comp_bad,
        f"bad={comp_bad}",
    )

    # PB-6 non-victim keys untouched
    victim_set = set(obs["victims"])
    changed = []
    for skey, pre_ref in obs["pre_index"].items():
        if pre_ref["extent_id"] in victim_set:
            continue
        post_ref = obs["post_index"].get(skey)
        if post_ref != pre_ref:
            changed.append({"key": skey, "pre": pre_ref, "post": post_ref})
    res.check(
        f"{tag}:non-victim-untouched",
        "are non-victim keys' refs unchanged by the reclaim?",
        not changed,
        f"changed={changed}",
    )

    # PB-7 cost bound
    if obs["stats_before"] and obs["stats_after"]:
        delta = obs["stats_after"].get("bytes_written", 0) - obs["stats_before"].get(
            "bytes_written", 0
        )
        victim_bytes = sum(r["length"] for r in vkeys.values())
        trigger_bytes = len(scen["trigger_value"])
        bound = victim_bytes + trigger_bytes + 2 * backend._extent_size
        res.check(
            f"{tag}:cost-bounded",
            "is relocated I/O bounded by victim live bytes + new page?",
            delta <= bound,
            f"delta_bytes_written={delta} bound={bound} (victim={victim_bytes} new={trigger_bytes})",
        )
    else:
        res.check(
            f"{tag}:cost-bounded",
            "is relocated I/O bounded?",
            None,
            "stats_snapshot unavailable; cannot measure bytes_written",
        )
    return obs


def run_v1_scenario(res, root):
    try:
        pool = H.V1Pool(num_pages=41, blocks_per_page=1, block_bytes=1600)
    except Exception as exc:  # torch missing / import failure
        res.check("v1:available", "v1 zero-copy path exercisable", None, f"V1Pool unavailable: {exc}")
        return
    be = H.make_backend(os.path.join(root, "v1store"))
    be.register_mem_pool_host(pool)
    try:
        # 4 slots x 10 pages of 1600 B = 40 keys fill the file exactly; the
        # 41st write wraps into victim slot 0.
        scen = H.build_v1_scenario(be, pool, pages_per_slot=10, num_keys=40)
        pre_bytes = {f"v{i:03d}": pool.read_page(i) for i in range(40)}
        obs = H.run_trigger(be, scen)
        if not obs["victims"]:
            res.check("v1:victim-selected", "v1 trigger selected victim", None, "no generation bump")
            return
        res.check("v1:victim-selected", "v1 trigger selected victim", True, f"victims={obs['victims']}")
        vkeys = H.victim_live_keys(obs, scen)
        lost, bad, in_victim = [], [], []
        for skey in vkeys:
            logical = H.strip_suffix(skey, scen["suffix"])
            if logical not in pre_bytes:
                continue
            pid = int(logical[1:])
            ref = H.lookup_ref(be, skey)
            # poison the destination page so a miss cannot look like a hit
            pool.set_page(pid, bytes(pool.page_bytes))
            be.batch_get_v1([logical], [pid])
            got = pool.read_page(pid)
            if ref is None:
                lost.append(skey)
                continue
            if got != pre_bytes[logical]:
                bad.append(skey)
            if ref.extent_id in obs["victims"]:
                in_victim.append(skey)
        res.check(
            "v1:live-refs-survive",
            "v1: every victim live ref resolvable after reclaim",
            not lost,
            f"lost={lost}",
        )
        res.check(
            "v1:bytes-checksum-exact",
            "v1: relocated zero-copy bytes exact (poisoned target, sha256)",
            not bad and not lost,
            f"mismatched={bad} lost={lost}",
        )
        res.check(
            "v1:dest-non-victim",
            "v1: relocated refs in non-victim space",
            not lost and not in_victim,
            f"still-in-victim={in_victim} lost={lost}",
        )
    except Exception as exc:
        res.check("v1:scenario", "v1 zero-copy scenario executed", None, f"exception: {exc!r}")
    finally:
        be.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    args = parser.parse_args(argv)
    H.load_tree(args.tree)
    res = H.OracleResult("oracle_payload_bytes", args.mode)
    root = H.make_tmproot("oc-payload-", args.keep_tmp)

    # --- flat KV-only ---
    b = H.make_backend(os.path.join(root, "kvstore"))
    scen = H.build_capacity_scenario(b, mixed_mamba=False)
    run_scenario(b, scen, res, "kv")
    b.close()

    # --- mixed KV + Mamba in the same victim slot ---
    b = H.make_backend(os.path.join(root, "mixstore"))
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    run_scenario(b, scen, res, "mixed")
    b.close()

    # --- real v1 zero-copy surface ---
    run_v1_scenario(res, root)

    res.note(
        "frozen-control expectation: kv/mixed live-refs-survive and "
        "bytes-checksum-exact FAIL (the frozen allocator drops the victim slot)."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
