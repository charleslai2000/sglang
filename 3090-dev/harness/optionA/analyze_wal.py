#!/usr/bin/env python3
"""Analyze the preserved WAL's SET frames to understand the write-once head structure.

Read-only. CPU-only. Frozen-tree code.
"""
import json, os, sys, time
sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
import sglang
assert sglang.__file__.startswith("/opt/sglang/local-prod-v1.1-candidate"), sglang.__file__
from sglang.srt.mem_cache.utils import get_hash_str
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916/pre-gate4-store"
SUFFIX = "_-data-models-qwen35-9b-w4a16_0_1"
MANIFEST = os.path.join(RUN, f"hicache.meta{SUFFIX}.manifest")
WAL0 = os.path.join(RUN, f"hicache.meta{SUFFIX}.wal.0")
CURRENT = os.path.join(RUN, f"hicache.meta{SUFFIX}.wal.current")

ids = json.load(open("/tmp/opencode/f1-restore-miss-20260916/marker_hashes.json"))["ids"]
hashes = get_hash_str(ids, None, page_size=1)
N = len(hashes)
idx_of = {h + SUFFIX: i for i, h in enumerate(hashes)}
print("n_ids", len(ids), "n_hashes", N)

state = em.read_manifest(MANIFEST)
frames = list(em.iter_segment_frames(WAL0, active=True))
print("n_frames", len(frames))

# per page-index write count and slot history
from collections import defaultdict
writes = defaultdict(list)   # page idx -> list of (seq, slot)
for f in frames:
    if f.frame_type != em.FRAME_SET:
        continue
    try:
        p = em.decode_set_payload(f.payload)
    except Exception as e:
        continue
    for e in p.entries:
        k = e.storage_key.decode("utf-8", "replace")
        i = idx_of.get(k)
        if i is not None:
            writes[i].append((f.seq, e.extent_id, e.offset, f.seq))

print("pages covered by SET:", len(writes))
# write-count histogram
from collections import Counter
wc = Counter(len(v) for v in writes.values())
print("write-count histogram (n_writes -> num_pages):", dict(sorted(wc.items())))
# For each page idx, list writes
for i in list(range(0, 12)) + [100, 1000, 5000, 10000, 20000, N-3, N-2]:
    if i in writes:
        print(f"page {i}: {len(writes[i])} writes {writes[i][:6]}")
# Identify the write-once prefix: consecutive pages from 0 with exactly 1 write
run = 0
while run in writes and len(writes[run]) == 1:
    run += 1
print("write-once prefix length from page0:", run)
# What about pages whose only write is in slot 0 (the destroyed slot)?
slot0_pages = [i for i,v in writes.items() if len(v)==1 and v[0][1]==0]
print("parked-in-slot0 pages with exactly 1 write:", len(slot0_pages), "min/max", (min(slot0_pages) if slot0_pages else None, max(slot0_pages) if slot0_pages else None))
# total distinct pages present
print("total pages with >=1 write:", len(writes), "of", N)
