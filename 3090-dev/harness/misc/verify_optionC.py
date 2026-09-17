#!/usr/bin/env python3
"""F1 Option C verifier: reclaim-time live-ref relocation (tests A-G).

Drives the real ExtentFileBackend (real ExtentAllocator, real WAL fds, real
batch_exists, real recovery) against the tree on PYTHONPATH.  Tests A-G from
the task contract.  Run against the frozen tree for FAIL-before and against
the candidate tree for PASS-after; the JSON records which assertions passed.
"""

import ctypes
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time

import sglang

assert (
    os.environ.get("OPTIONC_TREE", "") in sglang.__file__
), f"sglang.__file__={sglang.__file__} not under OPTIONC_TREE"

from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolName,
    PoolTransfer,
)
from sglang.srt.mem_cache.storage.extent import extent_metadata as em
from sglang.srt.mem_cache.storage.extent.extent_allocator import (
    ExtentAllocator,
    ExtentRef,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

EXTENT = 16 * 1024
FILE = 64 * 1024
PAGE = 1000

RESULTS = {"sglang_file": sglang.__file__, "tests": {}}
FAILURES = []


def record(name, passed, **detail):
    RESULTS["tests"].setdefault(name, {})
    RESULTS["tests"][name].update(detail)
    if not passed:
        FAILURES.append(name)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {json.dumps(detail, default=str)[:900]}", flush=True)


def make_backend(storage_dir, *, extent="16Ki", file_size="64Ki", max_size=None,
                 model="optionc"):
    extra = {
        "storage_dir": storage_dir,
        "extent_size": extent,
        "file_size": file_size,
    }
    if max_size is not None:
        extra["max_size"] = max_size
    cfg = HiCacheStorageConfig(
        extra_config=extra,
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True,
        model_name=model,
    )
    return ExtentFileBackend(cfg)


class ZCPool:
    """Per-index zero-copy host pool stand-in for batch_set_v1."""

    def __init__(self, sizes):
        self.page_size = 1
        self._pages = [bytearray(n) for n in sizes]

    def fill(self, index, payload):
        self._pages[index][:] = payload

    def get_page_buffer_meta(self, indices):
        idx = indices.tolist() if hasattr(indices, "tolist") else list(indices)
        ptrs = [ctypes.addressof(ctypes.c_char.from_buffer(self._pages[i])) for i in idx]
        return ptrs, [len(self._pages[i]) for i in idx]


class PgPool:
    """Fixed-page-size host pool for the v2 surface (KV / MAMBA)."""

    def __init__(self, page_bytes, slots=64):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def fill(self, index, payload):
        self._pages[index][:] = payload

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return bytearray(self._page_bytes)

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index][:] = data_page


def bytes_of(i, n):
    return bytes([i % 251]) * n


def read_equal(backend, key, expected):
    got = backend.get(key, bytearray(len(expected)))
    return got is not None and bytes(got) == bytes(expected)


def active_frames(backend):
    path = em.segment_path(
        backend._storage_dir, backend.config_suffix, backend._wal_generation
    )
    return list(em.iter_segment_frames(path, active=True))


def fold(frames, num_slots):
    """Rebuild a real ExtentAllocator from a WAL frame prefix."""
    replay = em.replay_records(frames, None, num_slots=num_slots)
    alloc = ExtentAllocator(EXTENT, num_slots)
    index = {}
    for entry in replay.entries:
        index[entry.storage_key.decode("utf-8")] = ExtentRef(
            entry.extent_id, entry.offset, entry.length, entry.generation
        )
    alloc._generations = list(replay.generations)
    alloc._index = index
    alloc._next_slot = 0
    return alloc


def seed_dead_slot0(backend, pool=None):
    """Make slot 0 full but hold only a small live head, with tail room later.

    Real cache traffic creates exactly this shape: a large key written once
    into the oldest slot, then overwritten so its bytes die in place while the
    live head stays behind.  Returns (head_keys, head_values).
    """
    keys = ["F1", "h0", "h1", "h2"]
    values = [bytes_of(1, 14000), bytes_of(10, 500), bytes_of(11, 500), bytes_of(12, 500)]
    assert backend.batch_set(keys, [bytearray(v) for v in values])
    # Overwrite F1: 14000 B no longer fits slot 0, so it moves to slot 1 and
    # slot 0 keeps only the 1500 B live head (+ dead 14000 B region).
    assert backend.batch_set(["F1"], [bytearray(bytes_of(99, 14000))])
    return ["h0", "h1", "h2"], values[1:]


def fill_middle_and_reclaim(backend, *, page=5000, n=9):
    """Fill the middle slots leaving tail room, then force the wrap.

    Returns (ok, write_layout, post_layout).
    """
    keys = [f"g{i}" for i in range(n)]
    values = [bytearray(bytes_of(100 + i, page)) for i in range(n)]
    ok = backend.batch_set(keys, values)
    return ok


# --------------------------------------------------------------------------- #
# A. existing F1 reproducer: head survives wrap/reclaim
# --------------------------------------------------------------------------- #
def test_A(tmp):
    backend = make_backend(tmp, model="A")
    pool = ZCPool([14000, 500, 500, 500, 14000, 5000, 5000, 5000, 5000,
                   5000, 5000, 5000, 5000, 5000])
    backend.register_mem_pool_host(pool)
    head_keys = ["F1", "h0", "h1", "h2"]
    head_vals = [bytes_of(1, 14000), bytes_of(10, 500), bytes_of(11, 500), bytes_of(12, 500)]
    for i, v in enumerate(head_vals):
        pool.fill(i, v)
    # seed slot 0 (head) + overwrite F1 into slot 1
    ok1 = backend.batch_set_v1(head_keys, [0, 1, 2, 3])
    pool.fill(4, bytes_of(99, 14000))
    ok2 = backend.batch_set_v1(["F1"], [4])
    # fill the middle slots; g6 wraps into full slot 0 -> reclaim victim slot 0
    gindices = list(range(5, 14))
    for j, idx in enumerate(gindices):
        pool.fill(idx, bytes_of(100 + j, 5000))
    ok3 = backend.batch_set_v1([f"g{j}" for j in range(9)], gindices)
    hits = backend.batch_exists(["h0", "h1", "h2"], None)
    exact = all(read_equal(backend, k, v) for k, v in zip(["h0", "h1", "h2"], head_vals[1:]))
    refs = {k: backend._allocator.lookup(backend._storage_key(k)) for k in ("h0", "h1", "h2")}
    relocated = all(r is not None and r.extent_id != 0 for r in refs.values())
    refs_safe = {
        k: (None if r is None else (r.extent_id, r.offset, r.generation))
        for k, r in refs.items()
    }
    record(
        "A_f1_reproducer",
        bool(ok1 and ok2 and ok3) and hits == 3 and exact and relocated,
        ok_seed=ok1, ok_rewrite=ok2, ok_fill=ok3,
        batch_exists=hits, bytes_exact=exact,
        refs=refs_safe,
    )
    backend.close()


# --------------------------------------------------------------------------- #
# B. multi-node/multi-key victim: live refs relocate, dead/stale refs do not
# --------------------------------------------------------------------------- #
def test_B(tmp):
    backend = make_backend(tmp, model="B")
    head_keys, head_vals = seed_dead_slot0(backend)
    # inject a stale accounting entry: present in _slot_keys but with an old
    # generation in the index (a dead ref lookup would reject).
    alloc = backend._allocator
    stale_key = backend._storage_key("stale")
    live = alloc._index[backend._storage_key("h0")]
    alloc._index[stale_key] = ExtentRef(live.extent_id, live.offset, live.length, live.generation - 1)
    alloc._slot_keys[live.extent_id].add(stale_key)
    ok = fill_middle_and_reclaim(backend)
    moved = {k: alloc.lookup(backend._storage_key(k)) for k in ("h0", "h1", "h2")}
    all_live = all(r is not None and r.extent_id != 0 for r in moved.values())
    stale_absent = alloc.lookup(stale_key) is None
    # the relocation WAL batch must contain exactly the 3 live head keys
    frames = active_frames(backend)
    reloc_keys = set()
    for f in frames:
        if f.frame_type == em.FRAME_SET:
            for e in em.decode_set_payload(f.payload).entries:
                k = e.storage_key.decode()
                if k in (backend._storage_key("h0"), backend._storage_key("h1"),
                         backend._storage_key("h2"), stale_key):
                    reloc_keys.add(k)
    no_stale_wal = stale_key not in reloc_keys
    exact = all(read_equal(backend, k, v) for k, v in zip(("h0", "h1", "h2"), head_vals))
    moved_safe = {
        k: (None if r is None else (r.extent_id, r.offset, r.generation))
        for k, r in moved.items()
    }
    record(
        "B_multi_key_victim",
        ok and all_live and stale_absent and no_stale_wal and exact,
        ok=ok, all_live=all_live, stale_absent=stale_absent,
        no_stale_wal=no_stale_wal, bytes_exact=exact,
        refs=moved_safe,
    )
    backend.close()


# --------------------------------------------------------------------------- #
# C. generation: stale old-generation refs fail; new refs resolve exactly
# --------------------------------------------------------------------------- #
def test_C(tmp):
    backend = make_backend(tmp, model="C")
    head_keys, head_vals = seed_dead_slot0(backend)
    alloc = backend._allocator
    old_refs = {k: alloc.lookup(backend._storage_key(k)) for k in ("h0", "h1", "h2")}
    old_gens = {k: (None if r is None else r.generation) for k, r in old_refs.items()}
    old_victim = None if old_refs["h0"] is None else old_refs["h0"].extent_id
    ok = fill_middle_and_reclaim(backend)
    new_refs = {k: alloc.lookup(backend._storage_key(k)) for k in ("h0", "h1", "h2")}
    new_ok = all(
        r is not None and r.generation == alloc._generations[r.extent_id]
        for r in new_refs.values()
    )
    old_invalid = all(
        alloc.verify([backend._storage_key(k)], [old_refs[k]]) == [False]
        for k in ("h0", "h1", "h2")
    )
    new_verify = all(
        alloc.verify([backend._storage_key(k)], [new_refs[k]]) == [True]
        for k in ("h0", "h1", "h2")
    )
    old_gen_is_lower = all(
        new_refs[k] is not None and new_refs[k].generation >= old_gens[k] for k in new_refs
    )
    victim_bumped = old_victim is not None and alloc._generations[old_victim] > 0
    new_safe = {
        k: (None if r is None else (r.extent_id, r.offset, r.generation))
        for k, r in new_refs.items()
    }
    record(
        "C_generation",
        ok and new_ok and old_invalid and new_verify and victim_bumped,
        ok=ok, new_gen_matches=new_ok, stale_verify_false=old_invalid,
        new_verify_true=new_verify, victim_generation_bumped=victim_bumped,
        old_gens=old_gens,
        new_refs=new_safe,
    )
    backend.close()


# --------------------------------------------------------------------------- #
# D. crash matrix: before relocation commit / after commit before retire /
#    after retire+reuse
# --------------------------------------------------------------------------- #
def test_D(tmp):
    backend = make_backend(tmp, model="D")
    num_slots = backend._allocator.num_slots
    head_keys, head_vals = seed_dead_slot0(backend)
    skey = {k: backend._storage_key(k) for k in ("h0", "h1", "h2")}
    pre = active_frames(backend)
    pre_len = len(pre)
    ok = fill_middle_and_reclaim(backend)
    frames = active_frames(backend)
    # locate the relocation SET + BATCH_COMMIT (the frames immediately before
    # the first DROP_SLOT of this reclaim) and the retirement/reuse region.
    drop_seqs = [f.seq for f in frames if f.frame_type == em.FRAME_DROP_SLOT]
    first_drop = drop_seqs[0] if drop_seqs else None
    reloc_set = max(
        (f.seq for f in frames
         if f.frame_type == em.FRAME_SET
         and any(e.storage_key.decode() in skey.values()
                 and e.extent_id != 0
                 for e in em.decode_set_payload(f.payload).entries)),
        default=None,
    )
    reloc_commit = min(
        (f.seq for f in frames
         if f.frame_type == em.FRAME_BATCH_COMMIT and reloc_set is not None
         and f.seq > reloc_set),
        default=None,
    )
    before = [f for f in frames if reloc_set is None or f.seq < reloc_set]
    after_commit = [f for f in frames if first_drop is None or f.seq < first_drop]
    after_retire = list(frames)
    a_before = fold(before, num_slots)
    a_commit = fold(after_commit, num_slots)
    a_retire = fold(after_retire, num_slots)
    # before commit: the old victim refs are authoritative (and the victim is
    # still at its original generation).
    before_ok = all(
        a_before.lookup(skey[k]) is not None
        and a_before.lookup(skey[k]).extent_id == 0
        for k in skey
    )
    # after relocation commit, before retirement: the new committed refs win.
    commit_ok = all(
        a_commit.lookup(skey[k]) is not None
        and a_commit.lookup(skey[k]).extent_id != 0
        for k in skey
    )
    # after retirement+reuse: only new refs are reachable; no ref points at
    # the retired victim generation.
    retire_ok = all(
        a_retire.lookup(skey[k]) is not None
        and a_retire.lookup(skey[k]).extent_id != 0
        and a_retire.lookup(skey[k]).generation == a_retire._generations[a_retire.lookup(skey[k]).extent_id]
        for k in skey
    )
    # the relocated refs must never point at overwritten victim bytes
    no_victim_exposure = all(
        a_retire.lookup(skey[k]) is not None
        and a_retire.lookup(skey[k]).extent_id != 0
        for k in skey
    )
    record(
        "D_crash_matrix",
        ok and before_ok and commit_ok and retire_ok and no_victim_exposure,
        ok=ok, pre_frames=pre_len, reloc_set=reloc_set, reloc_commit=reloc_commit,
        first_drop=first_drop, before_commit_old_authoritative=before_ok,
        after_commit_new_wins=commit_ok, after_retire_only_new=retire_ok,
        no_victim_exposure=no_victim_exposure,
    )
    backend.close()


# --------------------------------------------------------------------------- #
# E. checkpoint + WAL replay: latest relocated refs win
# --------------------------------------------------------------------------- #
def test_E(tmp):
    backend = make_backend(tmp, model="E")
    head_keys, head_vals = seed_dead_slot0(backend)
    ok = fill_middle_and_reclaim(backend)
    checkpoint_ok = backend.checkpoint()
    # one more ordinary write after the checkpoint, then a crash-style close
    assert backend.batch_set(["post"], [bytearray(bytes_of(200, 1000))])
    manifest = em.read_manifest(backend._manifest_path)
    manifest_has_head = all(
        any(e.storage_key.decode() == backend._storage_key(k) for e in manifest.entries)
        for k in ("h0", "h1", "h2")
    )
    backend._constructor_complete = False
    backend.close()
    reopened = make_backend(tmp, model="E")
    reopened_ok = all(reopened.exists(k) for k in ("h0", "h1", "h2"))
    exact = all(read_equal(reopened, k, v) for k, v in zip(("h0", "h1", "h2"), head_vals))
    refs = {k: reopened._allocator.lookup(reopened._storage_key(k)) for k in ("h0", "h1", "h2")}
    latest = all(
        r is not None
        and r.generation == reopened._allocator._generations[r.extent_id]
        and r.extent_id != 0
        for r in refs.values()
    )
    refs_safe = {
        k: (None if r is None else (r.extent_id, r.offset, r.generation))
        for k, r in refs.items()
    }
    reopened.close()
    record(
        "E_checkpoint_replay",
        ok and checkpoint_ok and manifest_has_head and reopened_ok and exact and latest,
        ok=ok, checkpoint=checkpoint_ok, manifest_has_head=manifest_has_head,
        reopened_ok=reopened_ok, bytes_exact=exact, latest_refs_win=latest,
        refs=refs_safe,
    )


# --------------------------------------------------------------------------- #
# F. no-capacity case: fail closed without corrupting/reusing the victim
# --------------------------------------------------------------------------- #
def test_F(tmp):
    backend = make_backend(tmp, model="F")
    # 80 KiB of 1000 B pages into a 64 KiB file: the wrap batch has no
    # destination capacity for the victim's live 16 KiB.
    for start in range(0, 60, 20):
        keys = [f"k{i:04d}" for i in range(start, start + 20)]
        values = [bytearray(bytes_of(i, PAGE)) for i in range(start, start + 20)]
        assert backend.batch_set(keys, values)
    victim_keys = [f"k{i:04d}" for i in range(16)]
    victim_before = {k: backend._allocator.lookup(backend._storage_key(k)) for k in victim_keys}
    frames_before = len(active_frames(backend))
    keys = [f"k{i:04d}" for i in range(60, 80)]
    values = [bytearray(bytes_of(i, PAGE)) for i in range(60, 80)]
    refused = backend.batch_set(keys, values) is False
    victim_after = {k: backend._allocator.lookup(backend._storage_key(k)) for k in victim_keys}
    victim_intact = victim_before == victim_after and all(v is not None for v in victim_after.values())
    used_unchanged = backend._allocator.used_bytes == 60 * PAGE
    new_absent = not backend.exists("k0060")
    new_frames = active_frames(backend)[frames_before:]
    no_drop = not any(f.frame_type == em.FRAME_DROP_SLOT for f in new_frames)
    no_reloc = not any(
        f.frame_type == em.FRAME_SET
        and any(e.storage_key.decode() in {backend._storage_key(k) for k in victim_keys}
                for e in em.decode_set_payload(f.payload).entries)
        for f in new_frames
    )
    backend.close()
    # reopen: the failed write left no durable trace
    reopened = make_backend(tmp, model="F")
    reopened_intact = all(reopened.exists(k) for k in victim_keys)
    reopened.close()
    record(
        "F_no_capacity_fail_closed",
        refused and victim_intact and used_unchanged and new_absent and no_drop
        and no_reloc and reopened_intact,
        refused=refused, victim_intact=victim_intact, used_unchanged=used_unchanged,
        new_absent=new_absent, no_drop_frame=no_drop, no_relocation_frame=no_reloc,
        reopened_intact=reopened_intact,
    )


# --------------------------------------------------------------------------- #
# G. byte exactness: relocated KV + Mamba payloads identical
# --------------------------------------------------------------------------- #
def test_G(tmp):
    backend = make_backend(tmp, model="G")
    kv = PgPool(500)
    mamba = PgPool(500)
    backend.register_mem_host_pool_v2(kv, PoolName.KV)
    backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)
    kv_val = bytes_of(31, 500)
    mam_val = bytes_of(37, 500)
    kv.fill(0, kv_val)
    mamba.fill(0, mam_val)
    # victim slot 0: big dead filler + KV page + Mamba component + head page
    assert backend.batch_set(
        ["F1", "kv0", "head"],
        [bytearray(bytes_of(1, 13000)), bytearray(kv_val), bytearray(bytes_of(12, 800))],
    )
    assert backend.batch_set_v2(
        [PoolTransfer(name=PoolName.MAMBA, host_indices=[0], keys=["mam0"], hit_policy=None)]
    )[PoolName.MAMBA] == [True]
    assert backend.batch_set(["F1"], [bytearray(bytes_of(99, 13000))])  # moves to slot 1
    ok = fill_middle_and_reclaim(backend, page=5000, n=8)
    # read back through the real v2 surface
    kv_read = PgPool(500)
    mamba_read = PgPool(500)
    backend.register_mem_host_pool_v2(kv_read, PoolName.KV)
    backend.register_mem_host_pool_v2(mamba_read, PoolName.MAMBA)
    got = backend.batch_get_v2(
        [
            PoolTransfer(name=PoolName.KV, host_indices=[0], keys=["kv0"], hit_policy=None),
            PoolTransfer(name=PoolName.MAMBA, host_indices=[0], keys=["mam0"], hit_policy=None),
        ]
    )
    kv_exact = got[PoolName.KV] == [True] and bytes(kv_read._pages[0]) == kv_val
    mam_exact = got[PoolName.MAMBA] == [True] and bytes(mamba_read._pages[0]) == mam_val
    # components survive the move (checkpoint records them per key)
    components_ok = (
        backend._components.get(backend._storage_key("kv0"))
        == em.component_from_pool_name(PoolName.KV)
        and backend._components.get(backend._component_key(PoolName.MAMBA, "mam0"))
        == em.component_from_pool_name(PoolName.MAMBA)
    )
    refs = {
        "kv0": backend._allocator.lookup(backend._storage_key("kv0")),
        "mam0": backend._allocator.lookup(backend._component_key(PoolName.MAMBA, "mam0")),
    }
    relocated = all(r is not None and r.extent_id != 0 for r in refs.values())
    refs_safe = {
        k: (None if r is None else (r.extent_id, r.offset, r.generation))
        for k, r in refs.items()
    }
    record(
        "G_byte_exactness_hybrid",
        ok and kv_exact and mam_exact and components_ok and relocated,
        ok=ok, kv_exact=kv_exact, mamba_exact=mam_exact,
        components_preserved=components_ok, relocated=relocated,
        refs=refs_safe,
    )
    backend.close()


def main():
    only = sys.argv[1:] or ["A", "B", "C", "D", "E", "F", "G"]
    tests = {"A": test_A, "B": test_B, "C": test_C, "D": test_D,
             "E": test_E, "F": test_F, "G": test_G}
    for name in only:
        tmp = tempfile.mkdtemp(prefix=f"optionc_{name}_")
        try:
            tests[name](tmp)
        except Exception as exc:  # keep the matrix going; record the failure
            import traceback
            record(f"{name}_ERROR", False, error=repr(exc),
                   tb=traceback.format_exc()[-600:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    RESULTS["failures"] = FAILURES
    out = os.environ.get("OPTIONC_OUT", f"/tmp/opencode/f1-optionC-scratch-20260917/verify_{os.path.basename(os.environ.get('OPTIONC_TREE','tree'))}.json")
    with open(out, "w") as fh:
        json.dump(RESULTS, fh, indent=2, default=str)
    print("WROTE", out)
    print("FAILURES", FAILURES)


if __name__ == "__main__":
    main()
