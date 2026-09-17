#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Oracle: live-vs-dead discriminator + group-boundary coverage.

Contract points:
  * all live refs in the victim generation are treated uniformly, not just KV
    head pages (Mamba sidecar included);
  * dead/stale refs are NOT copied;
  * a ref that is live but reachable only through a path the maintainer may
    not have considered (sidecar component; grouped write) is still preserved;
  * grouped KV/Mamba members staged behind a group commit are not silently
    dropped or relocated before their group boundary.

Falsification questions:
  LD-1  are Mamba sidecar refs in the victim preserved byte-exact too?
  LD-2  is a generation-stale entry in the victim slot NOT resurrected?
  LD-3  does staging a group, triggering reclaims, then committing leave the
        staged KV+Mamba members exact and visible?
  LD-4  are staged (invisible) members never exposed before GROUP_COMMIT?

REACHABILITY NOTE for LD-2: in the frozen allocator a generation-mismatched
entry cannot persist in ``_index`` (apply_drops removes slot keys and lookup
lazily evicts mismatches), so LD-2 is a defensive seam, not a production
state.  It is included because the relocation enumeration is the only code
that could turn such an entry back into a live ref.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _harness as H  # noqa: E402


def check_victim_preserved(res, backend, obs, scen, tag):
    vkeys = H.victim_live_keys(obs, scen)
    if not obs["victims"] or not vkeys:
        res.check(f"{tag}:precondition", "victim with live refs", None, "not reached -> INVALID")
        return
    bad = []
    for skey in vkeys:
        logical = H.strip_suffix(skey, scen["suffix"])
        expected = scen["live"].get(logical)
        if expected is None:
            continue
        got = H.verify_pre_key_bytes(backend, scen, skey, expected)
        if not got["resolves"] or not got["bytes_ok"]:
            bad.append(got)
    res.check(
        f"{tag}:uniform-preservation",
        "are every victim live ref (KV and sidecar) preserved byte-exact?",
        not bad,
        f"failures={bad}",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    H.add_common_args(parser)
    args = parser.parse_args(argv)
    H.load_tree(args.tree)
    res = H.OracleResult("oracle_live_dead", args.mode)
    root = H.make_tmproot("oc-livedead-", args.keep_tmp)

    # LD-1 mixed KV + Mamba in the same victim slot
    b = H.make_backend(os.path.join(root, "mixed"))
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    obs = H.run_trigger(b, scen)
    check_victim_preserved(res, b, obs, scen, "LD-1")
    b.close()

    # LD-2 stale-entry discriminator (defensive seam)
    b = H.make_backend(os.path.join(root, "stale"))
    scen = H.build_capacity_scenario(b, mixed_mamba=False)
    suffix = scen["suffix"]
    pre_gen = H.generations_snapshot(b)
    victim_guess = 0
    stale_key = "STALE" + suffix
    stale_ref = H.ExtentRef(victim_guess, 0, 64, pre_gen[victim_guess] + 1000)
    alloc = b._allocator
    with b._lock:
        alloc._index[stale_key] = stale_ref
        alloc._slot_keys[victim_guess].add(stale_key)
    before = H.lookup_ref(b, stale_key)
    obs = H.run_trigger(b, scen)
    after = H.lookup_ref(b, stale_key)
    resurrected = after is not None
    res.check(
        "LD-2:stale-not-resurrected",
        "is a generation-stale victim entry NOT turned back into a live ref?",
        (not resurrected) and (before is None),
        f"before={before} after={after} victims={obs['victims']}",
    )
    b.close()

    # LD-3/LD-4 grouped KV + Mamba staged across reclaims
    b = H.make_backend(os.path.join(root, "group"))
    try:
        kv_pool = H.PagePool(1000)
        m_pool = H.PagePool(1200)
        b.register_mem_host_pool_v2(kv_pool, H.PoolName.KV)
        b.register_mem_host_pool_v2(m_pool, H.PoolName.MAMBA)
        gid = b.open_group()
        kv_bytes = H.content("gkv", 1000)
        m_bytes = H.content("gmamba", 1200)
        kv_pool.set_page(0, kv_bytes)
        m_pool.set_page(0, m_bytes)
        r1 = b.batch_set_v2(
            [H.PoolTransfer(name=H.PoolName.KV, host_indices=[0], keys=["GK"])],
            group_id=gid,
        )
        r2 = b.batch_set_v2(
            [H.PoolTransfer(name=H.PoolName.MAMBA, host_indices=[0], keys=["GM"])],
            group_id=gid,
        )
        staged_ok = bool(r1.get(H.PoolName.KV, [False])[0]) and bool(
            r2.get(H.PoolName.MAMBA, [False])[0]
        )
        res.check("LD-3a:stage-accepted", "group staging accepted", staged_ok, f"{r1} {r2}")
        visible_before = H.lookup_ref(b, "GK" + b.config_suffix) is not None
        res.check(
            "LD-4:staged-invisible",
            "are staged members invisible before GROUP_COMMIT?",
            not visible_before,
            f"GK visible={visible_before}",
        )
        # Trigger reclaims while the group is open.
        gen_before = H.generations_snapshot(b)
        for i in range(80):
            key = f"gs{i:03d}"
            b.batch_set([key], [bytearray(H.content(key, 1000))])
        gen_after = H.generations_snapshot(b)
        reclaimed = gen_after != gen_before
        committed = b.commit_group(gid)
        res.check(
            "LD-3b:group-commit-succeeds",
            "does GROUP_COMMIT succeed after concurrent reclaims?",
            bool(committed),
            f"reclaimed={reclaimed} committed={committed}",
        )
        got_kv = H.read_logical_flat(b, "GK", 1000)
        got_m = H.read_logical_flat(b, "GM.mamba", 1200)
        res.check(
            "LD-3c:staged-bytes-exact",
            "are committed grouped KV+Mamba members byte-exact?",
            H.bytes_equal_exact(got_kv, kv_bytes) and H.bytes_equal_exact(got_m, m_bytes),
            f"kv_ok={H.bytes_equal_exact(got_kv, kv_bytes)} "
            f"mamba_ok={H.bytes_equal_exact(got_m, m_bytes)} reclaimed={reclaimed}",
        )
    except Exception as exc:
        res.check("LD-3:grouped-scenario", "grouped scenario executed", None, f"exception: {exc!r}")
    finally:
        b.close()

    res.note(
        "LD-2 is a defensive seam: the frozen allocator cannot leave a stale "
        "generation in _index; the check asserts the relocator does not create one."
    )
    return res.finish(args.out, argv)


if __name__ == "__main__":
    sys.exit(main())
