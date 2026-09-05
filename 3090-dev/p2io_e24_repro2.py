"""e24 deterministic repro: multi-batch v1 write -> exists count.

Reproduces the live e7m defect hypothesis: node29 wrote 2048 KV pages in
2 x 1024 STORAGE_BATCH_SIZE batches, but the read-side only finds 1024
pages present.  Uses the real MHA host pool (same as TestExtentV1ZeroCopy)
and the real engine _page_backup loop.

PRINTS the number of pages found after a 2048-page multi-batch write.
"""
import os
import sys

REPO = "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache"
sys.path.insert(0, os.path.join(REPO, "python"))
sys.path.insert(0, os.path.join(REPO, "test"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "teb",
    os.path.join(REPO, "test/registered/unit/mem_cache/test_extent_file_backend_unit.py"),
)
teb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(teb)

from unittest import mock
from sglang.srt.mem_cache.pool_host import base

# Real MHA host pool (torch) with the same budget mock as the test class.
mock.patch.object(
    base.psutil,
    "virtual_memory",
    return_value=mock.Mock(available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64 * (1024**3)),
).start()

from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost

PAGE_SIZE = 2
LAYER_NUM = 2
HEAD_NUM = 2
HEAD_DIM = 4

tmpdir = teb.tempfile.mkdtemp(prefix="e24_v1_")
backend = teb.ExtentFileBackend(
    teb._make_config(
        extra_config={"storage_dir": tmpdir, "extent_size": "16Ki", "file_size": "64Mi"}
    )
)
device_pool = MHATokenToKVPool(
    size=3000 * PAGE_SIZE, page_size=PAGE_SIZE, dtype=__import__("torch").float16,
    head_num=HEAD_NUM, head_dim=HEAD_DIM, layer_num=LAYER_NUM, device="cpu",
    enable_memory_saver=False,
)
host_pool = MHATokenToKVPoolHost(
    device_pool=device_pool, host_to_device_ratio=2.0, host_size=0,
    page_size=PAGE_SIZE, layout="page_first", pin_memory=False,
    device="cpu", allocator_type="default",
)
backend.register_mem_pool_host(host_pool)

def host_indices(num_pages):
    return __import__("torch").arange(num_pages * PAGE_SIZE, dtype=__import__("torch").int64)

def fill(p):
    import torch
    ps = PAGE_SIZE
    host_pool.kv_buffer[0, p * ps : (p + 1) * ps] = float(p + 1)
    host_pool.kv_buffer[1, p * ps : (p + 1) * ps] = float(p + 100)

n_pages = 2048
# fill all pages
for p in range(n_pages):
    fill(p)

keys = teb.ExtentBackendTestBase._make_keys(teb.ExtentBackendTestBase, n_pages)

# engine _page_backup loop with STORAGE_BATCH_SIZE=1024
STORAGE_BATCH_SIZE = 1024
indices_all = host_indices(n_pages)
for i in range(0, n_pages, STORAGE_BATCH_SIZE):
    batch = keys[i : i + STORAGE_BATCH_SIZE]
    bi = indices_all[i * PAGE_SIZE : (i + len(batch)) * PAGE_SIZE]
    ok = backend.batch_set_v1(batch, bi, None)
    print(f"batch {i}-{i+len(batch)} all ok: {all(ok)}")

print("batch_exists full:", backend.batch_exists(keys))
print("kv_pages v2 no-sidecar:", backend.batch_exists_v2(keys, []).kv_hit_pages)
backend.close()
