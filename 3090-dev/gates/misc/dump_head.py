import struct
import sys

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916/pre-gate4-store"
SUF = "_-data-models-qwen35-9b-w4a16_0_1"
WAL = f"{RUN}/hicache.meta{SUF}.wal.0"
with open(WAL, "rb") as f:
    data = f.read(2_000_000)

names = {1: "SET", 2: "BATCH_COMMIT", 3: "GROUP_COMMIT", 4: "DROP_SLOT", 5: "CLEAR", 6: "CHECKPOINT"}
off = em.SEGMENT_HEADER_SIZE
seen = 0
while off < len(data) and seen < 14:
    try:
        ftype, seq, payload, consumed = em.decode_frame(data[off:])
    except Exception as e:
        print("stop at", off, "err", e)
        break
    off += consumed
    seen += 1
    name = names.get(ftype, ftype)
    if ftype == em.FRAME_SET:
        p = em.decode_set_payload(payload)
        keys = [(e.storage_key.decode()[:12], e.extent_id, e.offset, e.length) for e in p.entries]
        print(seq, name, "batch", p.batch_id, "member", p.member_index, "/", p.member_count, keys)
    elif ftype == em.FRAME_BATCH_COMMIT:
        print(seq, name, "payload_len", len(payload))
    else:
        print(seq, name)
print("scanned", seen, "frames, bytes", off)
