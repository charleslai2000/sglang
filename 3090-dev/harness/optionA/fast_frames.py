#!/usr/bin/env python3
"""Fast WAL frame scan (no CRC): per-SET-frame page ranges + drop events."""
import json, os, struct, sys
sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
import sglang
assert sglang.__file__.startswith("/opt/sglang/local-prod-v1.1-candidate"), sglang.__file__
from sglang.srt.mem_cache.utils import get_hash_str
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916/pre-gate4-store"
SUFFIX = "_-data-models-qwen35-9b-w4a16_0_1"
WAL0 = os.path.join(RUN, f"hicache.meta{SUFFIX}.wal.0")
FRAME_MAGIC = em.FRAME_MAGIC
FV = em.FORMAT_VERSION
HEADER = em.FRAME_HEADER_SIZE

ids = json.load(open("/tmp/opencode/f1-restore-miss-20260916/marker_hashes.json"))["ids"]
hashes = get_hash_str(ids, None, page_size=1)
idx_of = {h + SUFFIX: i for i, h in enumerate(hashes)}

raw = open(WAL0, "rb").read()
off = em.SEGMENT_HEADER_SIZE
frames = []
while off + HEADER <= len(raw):
    magic, version, ftype, _f, _r, plen, seq = struct.unpack_from("<IHBBHIQ", raw, off)
    if magic != FRAME_MAGIC or version != FV:
        print("BAD header at", off); break
    payload = raw[off + HEADER: off + HEADER + plen]
    off += HEADER + plen
    if ftype == em.FRAME_SET:
        p = em.decode_set_payload(payload)
        idxs = []
        slots = set()
        for e in p.entries:
            i = idx_of.get(e.storage_key.decode("utf-8", "replace"))
            if i is not None:
                idxs.append(i)
                slots.add(e.extent_id)
        idxs.sort()
        frames.append({"seq": seq, "type": "SET", "gs": p.group_seq,
                       "batch_id": p.batch_id, "mi": p.member_index, "mc": p.member_count,
                       "n_entries": len(p.entries), "n_pages": len(idxs),
                       "pmin": idxs[0] if idxs else None, "pmax": idxs[-1] if idxs else None,
                       "contig": (idxs[-1] - idxs[0] + 1 == len(idxs)) if idxs else None,
                       "slots": sorted(slots)[:6]})
    elif ftype == em.FRAME_DROP_SLOT:
        dp = em.decode_drop_slot_payload(payload)
        frames.append({"seq": seq, "type": "DROP", "slot": dp.slot,
                       "new_generation": dp.new_generation})
    elif ftype == em.FRAME_GROUP_COMMIT:
        gp = em.decode_group_commit_payload(payload)
        frames.append({"seq": seq, "type": "GCOMMIT", "gs": gp.group_seq,
                       "mc": gp.member_count})
    elif ftype == em.FRAME_BATCH_COMMIT:
        bp = em.decode_batch_commit_payload(payload)
        frames.append({"seq": seq, "type": "BCOMMIT", "batch_id": bp.batch_id,
                       "mc": bp.member_count})
    else:
        frames.append({"seq": seq, "type": f"T{ftype}", "plen": plen})
out = "/tmp/opencode/f1-optionA-anchorrun-20260916/frames.json"
json.dump(frames, open(out, "w"), indent=0)
print("frames", len(frames), "->", out)
# compact print: SET frames only
for f in frames:
    if f["type"] == "SET":
        print("SET  seq=%-5d gs=%-4s batch=%-4s m=%s/%s n=%-5d pages=[%s..%s] contig=%s slots=%s"
              % (f["seq"], f["gs"], f["batch_id"], f["mi"], f["mc"], f["n_pages"],
                 f["pmin"], f["pmax"], f["contig"], f["slots"]))
