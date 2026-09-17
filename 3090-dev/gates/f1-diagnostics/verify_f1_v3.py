#!/usr/bin/env python3
"""F1 v3: correct predicate harness. `batch_exists` applies `_storage_key` itself,
so it must receive BARE page hashes (no config_suffix)."""
import json, os, sys, threading, time, types
sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
import sglang  # noqa
assert sglang.__file__.startswith("/opt/sglang/local-prod-v1.1-candidate")
from sglang.srt.mem_cache.utils import get_hash_str
from sglang.srt.mem_cache.storage.extent import extent_metadata as em
from sglang.srt.mem_cache.storage.extent.extent_allocator import ExtentAllocator, ExtentRef
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.hicache_storage import STORAGE_BATCH_SIZE

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916"
COPY = os.path.join(RUN, "pre-gate4-store")
SUF = "_-data-models-qwen35-9b-w4a16_0_1"
OUT = "/tmp/opencode/f1-restore-miss-20260916/verify_f1_v3.json"
res = {"sglang_file": sglang.__file__, "stages": {}}
def emit(stage, **kw):
    res["stages"][stage] = kw
    print(f"[{time.strftime('%H:%M:%S')}] {stage}: {json.dumps(kw)[:1200]}", flush=True)
    open(OUT, "w").write(json.dumps(res, indent=2))

ids = json.load(open("/tmp/opencode/f1-restore-miss-20260916/marker_hashes.json"))["ids"]
hashes = get_hash_str(ids, None, page_size=1)          # BARE 64-hex page keys
N = len(ids) - 1                                        # 23182 prefetchable pages
WIN_FROM_0 = hashes[:N]                                 # runtime window (pages 0..23181)
WIN_FROM_3 = hashes[3:N]
emit("marker", n_ids=len(ids), n_window=len(WIN_FROM_0))

state = em.read_manifest(os.path.join(COPY, f"hicache.meta{SUF}.manifest"))
frames = em.iter_segment_frames(os.path.join(COPY, f"hicache.meta{SUF}.wal.0"), active=True)
allf = list(frames)
t = time.time()
replay = em.replay_records(allf, state, num_slots=state.num_slots)
emit("replay_full", n_entries=len(replay.entries), s=round(time.time() - t, 1))

alloc = ExtentAllocator(67108864, state.num_slots)
index = {}
for e in replay.entries:
    index[e.storage_key.decode()] = ExtentRef(e.extent_id, e.offset, e.length, e.generation)
alloc._generations = list(replay.generations)
alloc._index = index
shim = types.SimpleNamespace(_allocator=alloc, _lock=threading.Lock())
shim.config_suffix = SUF
shim._storage_key = ExtentFileBackend._storage_key.__get__(shim)
assert shim._storage_key("abc") == "abc" + SUF

def real_batch_exists(keys):
    return ExtentFileBackend.batch_exists(shim, keys, None)

def hit_query(keys):                                    # verbatim cache_controller.py:1308-1317
    cnt = 0
    for s in range(0, len(keys), STORAGE_BATCH_SIZE):
        batch = keys[s:s + STORAGE_BATCH_SIZE]
        n = real_batch_exists(batch)
        cnt += n
        if n < len(batch):
            return cnt
    return cnt

emit("predicate",
     window_from_page0_hits=hit_query(WIN_FROM_0), window_from_page0_requested=len(WIN_FROM_0),
     window_from_page3_hits=hit_query(WIN_FROM_3), window_from_page3_requested=len(WIN_FROM_3),
     first_batch_returned=real_batch_exists(WIN_FROM_0[:STORAGE_BATCH_SIZE]),
     lookup_page0_none=(alloc.lookup(shim._storage_key(hashes[0])) is None),
     lookup_page3_none=(alloc.lookup(shim._storage_key(hashes[3])) is None),
     lookup_page0_storage_key=shim._storage_key(hashes[0]),
     STORAGE_BATCH_SIZE=STORAGE_BATCH_SIZE)
print("DONE", flush=True)
