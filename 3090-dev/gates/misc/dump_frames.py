import sys

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916/pre-gate4-store"
SUF = "_-data-models-qwen35-9b-w4a16_0_1"
WAL = f"{RUN}/hicache.meta{SUF}.wal.0"
names = {1: "SET", 2: "BATCH_COMMIT", 3: "GROUP_COMMIT", 4: "DROP_SLOT", 5: "CLEAR", 6: "CHECKPOINT"}
n = 0
for f in em.iter_segment_frames(WAL, active=True):
    n += 1
    if n > 18:
        break
    name = names.get(f.frame_type, f.frame_type)
    if f.frame_type == em.FRAME_SET:
        p = em.decode_set_payload(f.payload)
        keys = [e.storage_key.decode()[:12] for e in p.entries]
        print(f.seq, name, keys)
    elif f.frame_type == em.FRAME_BATCH_COMMIT:
        print(f.seq, name, "payload_len", len(f.payload))
    else:
        print(f.seq, name)
print("scanned", n, "frames")
