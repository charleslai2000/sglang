#!/usr/bin/env python3
"""F1 root-cause verification v2 (CPU-only; read-only w.r.t. /opt, /data, workspace).

Uses the frozen tree's OWN code to answer, for the 23,183-token BIGPREFIX8842 marker:
  A. every (seq, slot, gen) at which the chain-head keys (pages 0..3) were ever SET
     -> proves write-once + where page 0 lived
  B. the rebuilt index membership of the runtime's query window
  C. the REAL ExtentFileBackend.batch_exists + the verbatim _storage_hit_query loop
"""
import json
import os
import random
import sys
import threading
import time
import types

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")
import sglang  # noqa: E402
assert sglang.__file__.startswith("/opt/sglang/local-prod-v1.1-candidate"), sglang.__file__

from sglang.srt.mem_cache.utils import get_hash_str  # noqa: E402
from sglang.srt.mem_cache.storage.extent import extent_metadata as em  # noqa: E402
from sglang.srt.mem_cache.storage.extent.extent_allocator import (  # noqa: E402
    ExtentAllocator,
    ExtentRef,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (  # noqa: E402
    ExtentFileBackend,
)
from sglang.srt.mem_cache.hicache_storage import STORAGE_BATCH_SIZE  # noqa: E402

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916"
COPY = os.path.join(RUN, "pre-gate4-store")
SUFFIX = "_-data-models-qwen35-9b-w4a16_0_1"
CFG = SUFFIX
MANIFEST = os.path.join(COPY, f"hicache.meta{SUFFIX}.manifest")
WAL0 = os.path.join(COPY, f"hicache.meta{SUFFIX}.wal.0")
CURRENT = os.path.join(COPY, f"hicache.meta{SUFFIX}.wal.current")
OUT = os.path.join("/tmp/opencode/f1-restore-miss-20260916", "verify_f1_v2.json")
HASHES_OUT = os.path.join("/tmp/opencode/f1-restore-miss-20260916", "marker_hashes.json")

res = {"sglang_file": sglang.__file__, "stages": {}}


def emit(stage, **kw):
    res["stages"][stage] = kw
    print(f"[{time.strftime('%H:%M:%S')}] {stage}: {json.dumps(kw)[:1200]}", flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)


# ---------- 1. the runtime's own page-hash chain (reuse cached hashes if present) ----------
if os.path.exists(HASHES_OUT):
    ids = json.load(open(HASHES_OUT))["ids"]
    hashes = get_hash_str(ids, None, page_size=1)
else:
    from transformers import AutoTokenizer
    MODEL = "/data/models/qwen35-9b-w4a16"
    WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
             "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee "
             "zulu quantum orbital cascade nebula vertex cipher lattice photon matrix").split()
    ct = open(os.path.join(MODEL, "chat_template.jinja")).read()
    tok = AutoTokenizer.from_pretrained(MODEL)
    rng = random.Random(777777)
    body = " ".join(rng.choice(WORDS) for _ in range(int(12000 * 1.35)))
    MARKER = ("PHASE9-L3-LARGE-PREFIX-8842. This is a large unique prefix for L3 eviction/restore. "
              f"{body} PHASE9-L3-LARGE-PREFIX-8842 END. Reply with exactly: BIGPREFIX8842.")
    rendered = tok.apply_chat_template([{"role": "user", "content": MARKER}], tokenize=False,
                                       add_generation_prompt=True, chat_template=ct,
                                       enable_thinking=False)
    ids = tok(rendered, add_special_tokens=False)["input_ids"]
    hashes = get_hash_str(ids, None, page_size=1)
    json.dump({"ids": ids}, open(HASHES_OUT, "w"))

CHAIN = [h + CFG for h in hashes]
CHAIN_POST = CHAIN[: len(ids) - 1]      # post-restart query: pages 0..23181 (23182 keys)
CHAIN_PRE = CHAIN[3 : len(ids) - 1]     # pre-restart-style window: pages 3..23181
emit("marker", n_ids=len(ids), n_hashes=len(hashes), hash_len=len(hashes[0]),
     matches_round1=(len(ids) == 23183),
     chain_post=len(CHAIN_POST), chain_pre=len(CHAIN_PRE))

# ---------- 2. read the preserved WAL ----------
state = em.read_manifest(MANIFEST)
active_gen = em.read_current(CURRENT)
t = time.time()
frames = em.iter_segment_frames(WAL0, active=True)
torn = frames.torn_tail
all_frames = list(frames)
first_drop_seq = min((f.seq for f in all_frames if f.frame_type == em.FRAME_DROP_SLOT), default=None)
emit("wal_read", n_frames=len(all_frames), first_drop_seq=first_drop_seq,
     torn_tail=None if torn is None else torn.last_valid_offset, s=round(time.time() - t, 1))

# ---------- 3. history of the head keys across every SET frame ----------
WATCH = {CHAIN[i]: i for i in range(6)}
hist = {i: [] for i in range(6)}
t = time.time()
n_set_frames = 0
for f in all_frames:
    if f.frame_type != em.FRAME_SET:
        continue
    n_set_frames += 1
    try:
        p = em.decode_set_payload(f.payload)
    except Exception:
        continue
    for e in p.entries:
        try:
            k = e.storage_key.decode("utf-8")
        except Exception:
            continue
        i = WATCH.get(k)
        if i is not None:
            hist[i].append({"seq": f.seq, "slot": e.extent_id, "off": e.offset,
                            "len": e.length, "gen": e.generation})
emit("head_key_write_history", n_set_frames=n_set_frames, s=round(time.time() - t, 1),
     page0=hist[0], page1=hist[1], page2=hist[2], page3=hist[3],
     page0_n_writes=len(hist[0]), page1_n_writes=len(hist[1]),
     page2_n_writes=len(hist[2]), page3_n_writes=len(hist[3]))

# ---------- 4. full replay -> the index the restart server rebuilt ----------
t = time.time()
replay = em.replay_records(all_frames, state, num_slots=state.num_slots)
emit("replay_full", n_entries=len(replay.entries), seen_max_seq=replay.seen_max_seq,
     s=round(time.time() - t, 1))

num_slots = state.num_slots
alloc = ExtentAllocator(67108864, num_slots)
index = {}
for e in replay.entries:
    index[e.storage_key.decode("utf-8")] = ExtentRef(
        e.extent_id, e.offset, e.length, e.generation)
alloc._generations = list(replay.generations)
alloc._index = index
alloc._next_slot = state.next_slot
emit("allocator_rebuilt", n_index=len(index), generations_set=sorted(set(replay.generations)),
     next_slot=state.next_slot)

# ---------- 5. the REAL predicate (ExtentFileBackend.batch_exists) ----------
shim = types.SimpleNamespace(_allocator=alloc, _lock=threading.Lock())
shim.config_suffix = CFG
shim._storage_key = ExtentFileBackend._storage_key.__get__(shim)
assert shim._storage_key("abc") == "abc" + CFG


def real_batch_exists(keys):
    return ExtentFileBackend.batch_exists(shim, keys, None)


def hit_query(keys):                      # verbatim cache_controller.py:1308-1317
    cnt = 0
    for start in range(0, len(keys), STORAGE_BATCH_SIZE):
        batch = keys[start:start + STORAGE_BATCH_SIZE]
        n = real_batch_exists(batch)
        cnt += n
        if n < len(batch):
            return cnt
    return cnt


post_hits = hit_query(CHAIN_POST)
pre_hits = hit_query(CHAIN_PRE)
emit("batch_exists_result",
     post_chain_from_page0_hits=post_hits, post_requested=len(CHAIN_POST),
     pre_chain_from_page3_hits=pre_hits, pre_requested=len(CHAIN_PRE),
     STORAGE_BATCH_SIZE=STORAGE_BATCH_SIZE,
     first_batch_returned=real_batch_exists(CHAIN_POST[:STORAGE_BATCH_SIZE]),
     lookup_page0_is_none=(alloc.lookup(CHAIN[0]) is None),
     lookup_page3_is_none=(alloc.lookup(CHAIN[3]) is None))

# ---------- 6. per-index membership + run structure of the query window ----------
present = [i for i in range(len(CHAIN_POST)) if alloc.lookup(CHAIN_POST[i]) is not None]
runs = []
i = 0
while i < len(CHAIN_POST):
    if alloc.lookup(CHAIN_POST[i]) is None:
        i += 1
        continue
    j = i
    while j + 1 < len(CHAIN_POST) and alloc.lookup(CHAIN_POST[j + 1]) is not None:
        j += 1
    runs.append({"start": i, "len": j - i + 1})
    i = j + 1
longest = max(runs, key=lambda r: r["len"]) if runs else {"start": None, "len": 0}
emit("membership_query_window",
     n_present=len(present), n_absent=len(CHAIN_POST) - len(present),
     first_present=(present[0] if present else None),
     first_absent=next((i for i in range(len(CHAIN_POST))
                        if alloc.lookup(CHAIN_POST[i]) is None), None),
     longest_run_start=longest["start"], longest_run_len=longest["len"],
     n_runs=len(runs), runs=runs[:8])
print("DONE", flush=True)
