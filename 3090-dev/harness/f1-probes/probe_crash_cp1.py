#!/usr/bin/env python3
"""Item 2: frame-level reconstruction of the CP1 cut.

Replicates oracle_crash_matrix child_run in-process (no WAL truncation, no
replay) and prints:
  * the post-trigger frame stream (types, seq, offset, decoded SET entries);
  * the pre/post index refs for the corrupted keys;
  * which victim-slot byte ranges the trigger write physically overwrites.
This is the discriminator: are H/a overwritten by the trigger's own pwrite
(which is ordered AFTER the fsync'd relocation commit), or by the relocation?
"""
from __future__ import annotations

import os
import sys

TREE = os.environ["PROBE_TREE"]
SCAF = "/tmp/opencode/f1-optionC-review-scaffold-20260917/oracles"
sys.path.insert(0, SCAF)

import _harness as H  # noqa: E402


def main():
    H.load_tree(TREE)
    root = H.make_tmproot("probe-cp1-")
    store = os.path.join(root, "store")
    b = H.make_backend(store)
    scen = H.build_capacity_scenario(b, mixed_mamba=True)
    pre_index = H.index_snapshot(b)
    print("== pre-state victim refs ==")
    for k, r in sorted(pre_index.items()):
        print(f"  {k}: slot={r['extent_id']} off={r['offset']} len={r['length']} gen={r['generation']}")

    log = H.install_frame_log(b)
    trig = len(log)
    ok = bool(b.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))
    print(f"trigger_ok={ok}")
    post_index = H.index_snapshot(b)
    post_gen = H.generations_snapshot(b)
    print(f"post_gen={post_gen}")

    print("== frames after trigger ==")
    for i in range(trig, len(log)):
        fr = log[i]
        t = fr["type"]
        line = f"  [{i}] {H.frame_name(t)} seq={fr['seq']} wal_off={fr['offset']}"
        if t == 1:
            import base64
            p = H.meta_mod.decode_set_payload(base64.b64decode(fr["payload_b64"]))
            ents = [(e.storage_key.decode(), e.extent_id, e.offset, e.length, e.generation) for e in p.entries]
            line += f" batch={p.batch_id} entries={ents}"
        elif t == 2:
            import base64
            bc = H.meta_mod.decode_batch_commit_payload(base64.b64decode(fr["payload_b64"]))
            line += f" batch={bc.batch_id} count={bc.member_count}"
        elif t == 4:
            import base64
            ds = H.meta_mod.decode_drop_slot_payload(base64.b64decode(fr["payload_b64"]))
            line += f" slot={ds.slot} gen={ds.new_generation}"
        print(line)

    # Which victim byte ranges does the trigger pwrite physically touch?
    trigger_key = scen["trigger_key"]
    tref = post_index.get(trigger_key + scen["suffix"])
    print(f"== trigger ref = {tref}")
    if tref is not None:
        lo, hi = tref["offset"], tref["offset"] + tref["length"]
        for k, r in sorted(pre_index.items()):
            if r["extent_id"] == tref["extent_id"]:
                rlo, rhi = r["offset"], r["offset"] + r["length"]
                overlap = max(0, min(hi, rhi) - max(lo, rlo))
                print(
                    f"  victim_ref {k}: slot={r['extent_id']} [{rlo},{rhi}) "
                    f"trigger_slot={tref['extent_id']} [{lo},{hi}) overlap={overlap}B "
                    f"{'<== OVERWRITTEN' if overlap else ''}"
                )
        print(f"  relocated post-refs (victim keys):")
        for k, r in sorted(pre_index.items()):
            pr = post_index.get(k)
            if pr is not None:
                print(f"    {k}: pre_slot={r['extent_id']}@ {r['offset']} -> post_slot={pr['extent_id']}@ {pr['offset']} (moved={pr['extent_id'] != r['extent_id'] or pr['offset'] != r['offset']})")
    b.close()


if __name__ == "__main__":
    main()
