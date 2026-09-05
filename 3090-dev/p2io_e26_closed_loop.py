"""Minimal deterministic closed loop: 2048-page node, two 1024-batch
batch_set_v1 writes (the live engine _page_backup split), batch_exists must
return 2048, batch_get_v1 must byte-compare identical.

Also exports the three-way diagnostic the coordinator asked for:
  - write keys (0..2047)
  - query keys (0..2047)
  - index hit bitmap (per-key present in allocator index)

Four-branch verdict:
  - query keys only 1024          -> query-generation bug
  - query has 2048 but index only first 1024 -> second-batch commit bug
  - index has 2048 but exists returns 1024   -> prefix-scan bug
  - all 2048 PASS                 -> problem is upstream (UnifiedRadix node/prefix)
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import torch

from sglang.srt.mem_cache.pool_host import base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (
    ExtentFileBackend,
)

PAGE_SIZE = 2
LAYER_NUM = 2
HEAD_NUM = 2
HEAD_DIM = 4
PAGE_BYTES = 2 * LAYER_NUM * PAGE_SIZE * HEAD_NUM * HEAD_DIM * 2  # fp16


def _make_config(tmpdir):
    return HiCacheStorageConfig(
        extra_config={
            "storage_dir": tmpdir,
            "extent_size": "64Mi",
            "file_size": "512Mi",
        },
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name="testmodel",
    )


def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e26_loop_")
    N = 2048  # pages
    budget_patch = mock.patch.object(
        base.psutil,
        "virtual_memory",
        return_value=mock.Mock(
            available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64 * (1024**3)
        ),
    )
    budget_patch.start()
    backend = None
    try:
        device_pool = MHATokenToKVPool(
            size=N * PAGE_SIZE,
            page_size=PAGE_SIZE,
            dtype=torch.float16,
            head_num=HEAD_NUM,
            head_dim=HEAD_DIM,
            layer_num=LAYER_NUM,
            device="cpu",
            enable_memory_saver=False,
        )
        host_pool = MHATokenToKVPoolHost(
            device_pool=device_pool,
            host_to_device_ratio=2.0,
            host_size=0,
            page_size=PAGE_SIZE,
            layout="page_first",
            pin_memory=False,
            device="cpu",
            allocator_type="default",
        )
        backend = ExtentFileBackend(_make_config(tmpdir))
        backend.register_mem_pool_host(host_pool)
        from sglang.srt.mem_cache.hicache_storage import PoolName, PoolTransfer

        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)

        # Fill the host pool with distinct k/v values per page.
        ps = PAGE_SIZE
        for p in range(N):
            host_pool.kv_buffer[0, p * ps : (p + 1) * ps] = float(p + 1)
            host_pool.kv_buffer[1, p * ps : (p + 1) * ps] = float(p + 100)
        expected = host_pool.kv_buffer.clone()

        def flat_bytes(page_idx):
            page = host_pool.kv_buffer[:, page_idx * ps : (page_idx + 1) * ps]
            return page.flatten().view(torch.uint8).numpy().tobytes()

        def host_indices(num_pages, offset=0):
            # Real engine: batch b uses host_indices[b*ps:(b+num_pages)*ps].
            return torch.arange(offset, offset + num_pages * ps, dtype=torch.int64)

        # ---- WRITE: two 1024-batches (live _page_backup split) ----
        keys_all = [f"k{i:04d}" for i in range(N)]
        batch1 = keys_all[:1024]
        batch2 = keys_all[1024:]
        ok1 = backend.batch_set_v1(batch1, host_indices(1024, offset=0))
        ok2 = backend.batch_set_v1(batch2, host_indices(1024, offset=1024 * ps))
        print(f"batch_set_v1[0:1024] ok: {all(ok1)} ({len(ok1)})")
        print(f"batch_set_v1[1024:2048] ok: {all(ok2)} ({len(ok2)})")

        # ---- EXPORT 1: write keys ----
        print(f"write_keys: {len(keys_all)} (0..{N - 1})")

        # ---- EXPORT 2: query keys (full 0..2047) ----
        query_keys = keys_all
        print(f"query_keys: {len(query_keys)} (0..{N - 1})")

        # ---- EXPORT 3: index hit bitmap ----
        with backend._lock:
            bitmap = [
                backend._allocator.lookup(backend._storage_key(k)) is not None
                for k in keys_all
            ]
        present = sum(bitmap)
        print(f"index hit bitmap: {present}/{N} present")
        if present < N:
            first_missing = next(i for i, b in enumerate(bitmap) if not b)
            print(f"first missing index: {first_missing}")

        # ---- batch_exists ----
        exists_count = backend.batch_exists(query_keys)
        print(f"batch_exists(query 0..{N - 1}) = {exists_count}")

        # ---- batch_get_v1 byte compare ----
        read_keys = query_keys
        got = backend.batch_get_v1(read_keys, host_indices(N, offset=0))
        bad = [i for i, ok in enumerate(got) if not ok]
        byte_mismatch = []
        if not bad:
            # batch_get_v1 reads into the host pool; compare against expected.
            for i in range(N):
                cur = flat_bytes(i)
                exp = expected[:, i * ps : (i + 1) * ps].flatten().view(torch.uint8).numpy().tobytes()
                if cur != exp:
                    byte_mismatch.append(i)
        print(f"batch_get_v1 ok count: {N - len(bad)}/{N}, failed: {bad[:5]}")
        print(f"byte-mismatch pages: {len(byte_mismatch)} {byte_mismatch[:5]}")

        # ---- four-branch verdict ----
        if len(query_keys) < N:
            verdict = "BRANCH 1: query keys only 1024 -> query-generation bug"
        elif present < N:
            verdict = (
                "BRANCH 2: index only first "
                f"{present} -> second-batch commit bug"
            )
        elif exists_count < N:
            verdict = (
                f"BRANCH 3: index has {present} but exists returns "
                f"{exists_count} -> prefix-scan bug"
            )
        else:
            verdict = (
                "BRANCH 4: all 2048 PASS -> problem is upstream "
                "(UnifiedRadix node/prefix construction)"
            )
        print(f"VERDICT: {verdict}")
        print(f"CLOSED LOOP PASS: {exists_count == N and not bad and not byte_mismatch}")

        # ---- v2 surface (live read path) closed loop ----
        # Re-fill pool with distinct values (v1 get wrote back into pool).
        for p in range(N):
            host_pool.kv_buffer[0, p * ps : (p + 1) * ps] = float(p + 1)
            host_pool.kv_buffer[1, p * ps : (p + 1) * ps] = float(p + 100)
        expected = host_pool.kv_buffer.clone()

        def transfer(keys, indices, name=PoolName.KV):
            return PoolTransfer(
                name=name,
                host_indices=indices,
                keys=list(keys),
                hit_policy=None,
            )

        # Write via v2 in two 1024-batches (live batch_set_v2 split).
        ok1 = backend.batch_set_v2([transfer(batch1, host_indices(1024, 0))])[PoolName.KV]
        ok2 = backend.batch_set_v2([transfer(batch2, host_indices(1024, 1024 * ps))])[PoolName.KV]
        print(f"v2 batch_set_v2[0:1024] ok: {all(ok1)}")
        print(f"v2 batch_set_v2[1024:2048] ok: {all(ok2)}")

        res = backend.batch_exists_v2(query_keys, pool_transfers=[])
        print(f"v2 batch_exists_v2(query 0..2047) = {res.kv_hit_pages}")

        got2 = backend.batch_get_v2([transfer(query_keys, host_indices(N, 0))])[PoolName.KV]
        bad2 = [i for i, ok in enumerate(got2) if not ok]
        mismatch2 = []
        if not bad2:
            for i in range(N):
                cur = flat_bytes(i)
                exp = expected[:, i * ps : (i + 1) * ps].flatten().view(torch.uint8).numpy().tobytes()
                if cur != exp:
                    mismatch2.append(i)
        print(f"v2 batch_get_v2 ok count: {N - len(bad2)}/{N}, failed: {bad2[:5]}")
        print(f"v2 byte-mismatch pages: {len(mismatch2)} {mismatch2[:5]}")
        print(
            f"V2 CLOSED LOOP PASS: {res.kv_hit_pages == N and not bad2 and not mismatch2}"
        )
    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
