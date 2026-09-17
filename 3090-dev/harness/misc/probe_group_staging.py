"""Group contract under relocation: staged bytes/reservations are not touched.

5 x 16 KiB slots.  Slot 0 is the circular-reclaim victim (full, small live
head).  A group stages a page in slot 2 (reserved but invisible).  The fill
plan touches {0,3,4}; the only free destination is slot 1, so relocation must
skip the staged slot and the staged bytes must survive the commit.
"""
import os
import shutil
import tempfile

import sglang

from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolName,
    PoolTransfer,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

TREE = os.environ["OPTIONC_TREE"]
assert TREE in sglang.__file__, sglang.__file__


class PgPool:
    def __init__(self, page_bytes, slots=64):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return bytearray(self._page_bytes)

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index][:] = data_page


def mk(tmp, model):
    return ExtentFileBackend(HiCacheStorageConfig(
        extra_config={"storage_dir": tmp, "extent_size": "16Ki", "file_size": "80Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1, attn_cp_rank=0, attn_cp_size=1,
        is_mla_model=False, enable_storage_metrics=False, is_page_first_layout=True,
        model_name=model))


def bob(i, n):
    return bytes([i % 251]) * n


def main():
    tmp = tempfile.mkdtemp(prefix="probe_group_")
    b = mk(tmp, "grp")
    kv = PgPool(500)
    b.register_mem_host_pool_v2(kv, PoolName.KV)
    try:
        assert b.batch_set(
            ["F1", "h0", "h1", "h2"],
            [bytearray(bob(1, 14000)), bytearray(bob(10, 500)),
             bytearray(bob(11, 500)), bytearray(bob(12, 500))])
        assert b.batch_set(["F1"], [bytearray(bob(99, 14000))])  # F1 -> slot 1
        assert b.batch_set([f"g{i}" for i in range(3)],
                           [bytearray(bob(100 + i, 5000)) for i in range(3)])  # slot 2
        # stage a group member: cursor is at slot 2 -> staged ref in slot 2
        staged_val = bob(70, 500)
        kv._pages[0][:] = staged_val
        group = b.open_group()
        assert b.batch_set_v2(
            [PoolTransfer(name=PoolName.KV, host_indices=[0], keys=["g_staged"], hit_policy=None)],
            group_id=group,
        )[PoolName.KV] == [True]
        assert b._staged_slots() == {2}, b._staged_slots()
        assert not b.exists("g_staged")
        # fill the rest; the last page wraps into full slot 0 -> reclaim
        assert b.batch_set([f"g{i}" for i in range(3, 12)],
                           [bytearray(bob(100 + i, 5000)) for i in range(3, 12)])
        print("victim 0 bumped:", b._allocator._generations[0] > 0)
        refs = {k: b._allocator.lookup(b._storage_key(k)) for k in ("h0", "h1", "h2")}
        off_victim = all(r is not None and r.extent_id != 0 for r in refs.values())
        print("head relocated off slot 0:", off_victim,
              {k: (r.extent_id, r.offset) for k, r in refs.items()})
        print("head relocated to slot 1 (staged slot 2 skipped):",
              all(r.extent_id == 1 for r in refs.values()))
        assert b.commit_group(group)
        got = PgPool(500)
        b.register_mem_host_pool_v2(got, PoolName.KV)
        res = b.batch_get_v2([PoolTransfer(name=PoolName.KV, host_indices=[0], keys=["g_staged"], hit_policy=None)])
        staged_ok = res[PoolName.KV] == [True] and bytes(got._pages[0]) == staged_val
        print("staged bytes exact after commit:", staged_ok)
        head_ok = all(b.get(k, bytearray(500)) is not None for k in ("h0", "h1", "h2"))
        print("GROUP_STAGING_PROBE_DONE", staged_ok and head_ok and off_victim)
    finally:
        b.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
