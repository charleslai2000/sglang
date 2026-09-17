#!/usr/bin/env python3
"""F1 root-cause verification (CPU-only, read-only w.r.t. /opt, /data, workspace).

Replays the PRESERVED round-1 WAL with the frozen tree's own extent_metadata.replay_records,
rebuilds the allocator state exactly as ExtentFileBackend._restore_allocator does, and then
runs the REAL ExtentFileBackend.batch_exists predicate + the exact _storage_hit_query loop
against the runtime's own page-hash chain for the 23,183-token BIGPREFIX8842 marker.

Answers:
  A. which queried page index is the first absent one (the true->false transition)
  B. how many hits batch_exists reports for the post-restart chain vs the pre-restart chain
  C. whether the head keys (0,1,2) were EVER written to the WAL before the DROP_SLOT sweep
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
from transformers import AutoTokenizer  # noqa: E402

RUN = "/var/log/sglang/local-prod-v1.1/phase9-production-validation-20260916"
COPY = os.path.join(RUN, "pre-gate4-store")
SUFFIX = "_-data-models-qwen35-9b-w4a16_0_1"
CFG = SUFFIX
MANIFEST = os.path.join(COPY, f"hicache.meta{SUFFIX}.manifest")
WAL0 = os.path.join(COPY, f"hicache.meta{SUFFIX}.wal.0")
CURRENT = os.path.join(COPY, f"hicache.meta{SUFFIX}.wal.current")
MODEL = "/data/models/qwen35-9b-w4a16"
OUT = os.path.join("/tmp/opencode/f1-restore-miss-20260916", "verify_f1_lookup.json")
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
         "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee "
         "zulu quantum orbital cascade nebula vertex cipher lattice photon matrix").split()

res = {"sglang_file": sglang.__file__, "stages": {}}


def emit(stage, **kw):
    res["stages"][stage] = kw
    print(f"[{time.strftime('%H:%M:%S')}] {stage}: {json.dumps(kw)[:900]}", flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)


# ---------- 1. the runtime's own page-hash chain for the marker prompt ----------
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
emit("marker", n_ids=len(ids), n_hashes=len(hashes),
     matches_round1_prompt_tokens=(len(ids) == 23183),
     hash_len=len(hashes[0]),
     first_hash=hashes[0], last_hash=hashes[-1])

# runtime query windows (page_size == 1)
#  post-restart: matched prefix 0 -> new_input_tokens = prompt minus final token
#  pre-restart (l3_probe / round-1 at 21:28:58): an L1 head of 3 tokens was matched
CHAIN_POST = [h + CFG for h in hashes][: (len(ids) - 1)]           # 23182 keys, page 0..23181
CHAIN_PRE = [h + CFG for h in hashes][3 : (len(ids) - 1)]          # 23179 keys, page 3..23181
emit("query_windows", post_restart_keys=len(CHAIN_POST),
     pre_restart_keys=len(CHAIN_PRE),
     post_first_key=CHAIN_POST[0][:32], pre_first_key=CHAIN_PRE[0][:32])

# ---------- 2. read the preserved WAL ----------
state = em.read_manifest(MANIFEST)
active_gen = em.read_current(CURRENT)
t = time.time()
frames = em.iter_segment_frames(WAL0, active=True)
_torn = frames.torn_tail
all_frames = list(frames)
first_set = next((f for f in all_frames if f.frame_type == em.FRAME_SET), None)
first_drop_seq = min((f.seq for f in all_frames if f.frame_type == em.FRAME_DROP_SLOT),
                     default=None)
emit("wal_read", n_frames=len(all_frames),
     torn_tail=None if _torn is None else {"offset": _torn.last_valid_offset},
     s=round(time.time() - t, 1), first_set_seq=(first_set.seq if first_set else None),
     first_drop_seq=first_drop_seq)

# what did the very first SET frame install? (the first keys ever written)
if first_set is not None:
    p = em.decode_set_payload(first_set.payload)
    emit("first_set_frame", seq=first_set.seq, batch_id=p.batch_id,
         member_count=p.member_count, n_entries=len(p.entries),
         head=[{"slot": e.extent_id, "off": e.offset, "len": e.length,
                "gen": e.generation, "comp": e.component,
                "key16": e.storage_key.decode()[:16],
                "key_tail": e.storage_key.decode()[-len(CFG):] == CFG,
                "is_page0": e.storage_key.decode() == CHAIN_POST[0]}
               for e in p.entries[:6]],
         n_page_keys_in_frame=sum(1 for e in p.entries
                                  if e.storage_key.decode() in set(CHAIN_POST)))

# ---------- 3. full replay -> rebuilt index (== post-restart runtime state) ----------
t = time.time()
replay = em.replay_records(all_frames, state, num_slots=state.num_slots)
emit("replay_full", n_entries=len(replay.entries), s=round(time.time() - t, 1),
     seen_max_seq=replay.seen_max_seq)

num_slots = state.num_slots
alloc = ExtentAllocator(67108864, num_slots)
index = {}
for e in replay.entries:
    key = e.storage_key.decode("utf-8")
    index[key] = ExtentRef(e.extent_id, e.offset, e.length, e.generation)
alloc._generations = list(replay.generations)
alloc._index = index
alloc._next_slot = state.next_slot
emit("allocator_rebuilt", n_index=len(index),
     generations_set=sorted(set(replay.generations)),
     next_slot=state.next_slot,
     n_index_entries_with_gen_0=sum(1 for r in index.values() if r.generation == 0))

# ---------- 4. the REAL predicate: ExtentFileBackend.batch_exists ----------
shim = types.SimpleNamespace(_allocator=alloc, _lock=threading.Lock())
shim._storage_key = ExtentFileBackend._storage_key.__get__(shim)


def real_batch_exists(keys):
    return ExtentFileBackend.batch_exists(shim, keys, None)


# _storage_hit_query loop, transcribed verbatim from cache_controller.py:1308-1317
def hit_query(keys):
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
     post_restart__chain_from_page0__hits=post_hits,
     post_restart__requested=len(CHAIN_POST),
     pre_restart__chain_from_page3__hits=pre_hits,
     pre_restart__requested=len(CHAIN_PRE),
     STORAGE_BATCH_SIZE=STORAGE_BATCH_SIZE,
     batch_exists_first_batch_returned=real_batch_exists(CHAIN_POST[:STORAGE_BATCH_SIZE]))

# per-index membership for the marker chain
present_idx = [i for i, k in enumerate(CHAIN_POST) if alloc.lookup(k) is not None]
first_present = present_idx[0] if present_idx else None
first_absent = next((i for i in range(len(CHAIN_POST)) if alloc.lookup(CHAIN_POST[i]) is None), None)
# longest contiguous present run starting at each index
run_from = {}
i = 0
while i < len(CHAIN_POST):
    if alloc.lookup(CHAIN_POST[i]) is None:
        i += 1
        continue
    j = i
    while j + 1 < len(CHAIN_POST) and alloc.lookup(CHAIN_POST[j + 1]) is not None:
        j += 1
    run_from[i] = j - i + 1
    i = j + 1
longest = max(run_from.items(), key=lambda kv: kv[1]) if run_from else (None, 0)
emit("membership_post_restart",
     n_present=len(present_idx), n_absent=len(CHAIN_POST) - len(present_idx),
     first_present_index=first_present, first_absent_index=first_absent,
     longest_present_run_start=longest[0], longest_present_run_len=longest[1],
     runs=[{"start": s, "len": n} for s, n in sorted(run_from.items())][:6])

# ---------- 5. were the head keys ever written, before the DROP_SLOT sweep? ----------
pre_drop = [f for f in all_frames if first_drop_seq is not None and f.seq < first_drop_seq]
t = time.time()
replay_pre = em.replay_records(pre_drop, state, num_slots=num_slots)
pre_index = {e.storage_key.decode("utf-8"): e for e in replay_pre.entries}
emit("replay_pre_drop", n_frames=len(pre_drop), n_entries=len(pre_index),
     s=round(time.time() - t, 1))
head = []
for i in (0, 1, 2, 3, 4):
    e = pre_index.get(CHAIN_POST[i])
    head.append({"page_index": i, "present_pre_drop": e is not None,
                 "slot": (e.extent_id if e is not None else None),
                 "gen": (e.generation if e is not None else None)})
emit("head_keys_pre_drop", head=head,
     n_present_pre_drop_in_chain=sum(1 for k in CHAIN_POST if k in pre_index),
     first_absent_pre_drop=next((i for i in range(len(CHAIN_POST))
                                 if CHAIN_POST[i] not in pre_index), None))
print("DONE", flush=True)
