"""Focused probe: does reclaim relocation preserve the F1 head with real paths?"""
import hashlib
import os
import shutil
import sys
import tempfile

import sglang

TREE = os.environ["OPTIONC_TREE"]
assert sglang.__file__.startswith(TREE), sglang.__file__

from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

EXTENT = 16 * 1024
FILE = 64 * 1024


def cfg(extra=None, model="probe"):
    base = {
        "tp_rank": 0, "tp_size": 1, "pp_rank": 0, "pp_size": 1,
        "attn_cp_rank": 0, "attn_cp_size": 1, "is_mla_model": False,
        "enable_storage_metrics": False, "is_page_first_layout": True,
        "model_name": model,
    }
    base["extra_config"] = {"storage_dir": extra, "extent_size": "16Ki", "file_size": "64Ki"}
    return HiCacheStorageConfig(**base)


def page(tag, n):
    return bytearray((tag.to_bytes(4, "little") * ((n // 4) + 1))[:n])


def layout(backend):
    out = []
    for s in range(backend._allocator.num_slots):
        if backend._allocator._slot_keys[s] or backend._allocator._cursors[s]:
            out.append((s, backend._allocator._cursors[s],
                        len(backend._allocator._slot_keys[s]),
                        backend._allocator._slot_bytes[s]))
    return out


def head():
    tmp = tempfile.mkdtemp(prefix="probe_reloc_")
    b = ExtentFileBackend(cfg(tmp))
    try:
        # slot 0: big dead filler + the head pages p0,p1,p2 (small live)
        keys = ["F1", "p0", "p1", "p2", "F2"]
        vals = [page(1, 14000), page(10, 500), page(11, 500), page(12, 500), page(2, 800)]
        print("seed", b.batch_set(keys, vals))
        # overwrite F1 -> cannot fit slot0, lands in slot1, leaves slot0 dead space
        print("rewrite F1", b.batch_set(["F1"], [page(99, 14000)]))
        print("after rewrite layout", layout(b))
        # fill slots 1..3 with 5000B pages (tail room ~1.4KiB each)
        fill_keys = [f"g{i}" for i in range(9)]
        fill_vals = [page(100 + i, 5000) for i in range(9)]
        print("fill", b.batch_set(fill_keys, fill_vals))
        print("layout before wrap", layout(b), "next", b._allocator._next_slot)
        # page that overflows slot3 and re-enters full slot0 -> reclaim victim
        print("wrap write", b.batch_set(["wrap0"], [page(200, 5000)]))
        print("layout after wrap", layout(b), "next", b._allocator._next_slot)
        chain = ["p0", "p1", "p2"]
        print("batch_exists head", b.batch_exists(chain, None), "/", len(chain))
        print("exists", [b.exists(k) for k in chain])
        for k, v in zip(keys[:4], vals[:4]):
            got = b.get(k, bytearray(len(v)))
            print("byte-exact", k, bytes(got) == bytes(v))
        # Check the victim slot's generation bumped and p* moved out
        refs = {k: b._allocator.lookup(b._storage_key(k)) for k in chain}
        print("relocated refs", {k: (r.extent_id, r.offset, r.generation) for k, r in refs.items()})
    finally:
        b.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    head()
