"""e24 mamba sidecar cross-thread visibility probe.

Extends the coordinator's commit self-probe to the actual failing pool: the
MAMBA component key written via batch_set_v2 (backup thread) then queried via
batch_exists_v2 with a TRAILING_PAGES sidecar (prefetch thread), plus the KV
v1 multi-batch write -> v2 query across threads.  Reproduces the EXACT live
flow shape.
"""
import os
import sys
import tempfile
import threading
import time

REPO = "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache"
sys.path.insert(0, os.path.join(REPO, "python"))
sys.path.insert(0, os.path.join(REPO, "test"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "teb", os.path.join(REPO, "test/registered/unit/mem_cache/test_extent_file_backend_unit.py"),
)
teb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(teb)

from sglang.srt.mem_cache.hicache_storage import (
    PoolName, PoolTransfer, PoolHitPolicy,
)

tmpdir = tempfile.mkdtemp(prefix="e24_mamba_")
backend = teb.ExtentFileBackend(
    teb._make_config(
        model_name="qwen3.5-9b-gptq",
        extra_config={"storage_dir": tmpdir, "extent_size": "16Ki", "file_size": "256Mi"},
    )
)
kv = teb._PagePool(1000, slots=4096)
mamba = teb._PagePool(1000, slots=4096)
backend.register_mem_host_pool_v2(kv, PoolName.KV)
backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

def tfer(name, keys, indices=None, hp=None):
    return PoolTransfer(name=name, host_indices=indices if indices is not None else list(range(len(keys))), keys=list(keys), hit_policy=hp)

_refhash_page_hashes = teb._refhash_page_hashes
page_size = 1
seed_hex = "9d373db168e3e6a03e12ea791ce33b00590b4652dd4618889639c8095ac017f7"

# node writes 2048 pages (multi-batch, like node29). Register mamba for last page.
n_node = 2048
chain = _refhash_page_hashes(list(range(100, 100+n_node)), seed_hex, page_size)
result = {}

# WRITE on one thread (backup thread)
def do_write():
    # v1 multi-batch KV
    for i in range(0, n_node, 1024):
        ok = backend.batch_set(chain[i:i+1024], [bytearray(b"x"*1000) for _ in range(1024)])
        assert ok
    # mamba v2 for last page
    assert backend.batch_set_v2([tfer(PoolName.MAMBA, [chain[-1]])])[PoolName.MAMBA] == [True]
    result["write_done"] = True

t = threading.Thread(target=do_write)
t.start(); t.join()

print("KV present (v2 no sidecar):", backend.batch_exists_v2(chain, []).kv_hit_pages)
print("mamba last-page key registered:",
      backend._allocator.lookup(chain[-1] + ".mamba" + backend.config_suffix) is not None)
print("generations:", backend._allocator._generations[:3])

# QUERY on another thread (prefetch thread) with mamba trailing sidecar
def do_query():
    r = backend.batch_exists_v2(
        chain,
        [tfer(PoolName.MAMBA, ["__placeholder__"], hp=PoolHitPolicy.TRAILING_PAGES)],
    )
    result["query"] = (r.kv_hit_pages, {getattr(k,"value",k): v for k,v in r.extra_pool_hit_pages.items()})

q = threading.Thread(target=do_query)
q.start(); q.join()
print("CROSS-THREAD mamba-sidecar query:", result["query"])

# advance unrelated writes (new extents) then re-query cross-thread
for i in range(0, 4000, 8):
    backend.batch_set(["u%05d"%i for i in range(8)], [bytearray(b"u"*1000) for _ in range(8)])
def do_query2():
    r = backend.batch_exists_v2(
        chain,
        [tfer(PoolName.MAMBA, ["__placeholder__"], hp=PoolHitPolicy.TRAILING_PAGES)],
    )
    result["query2"] = (r.kv_hit_pages, {getattr(k,"value",k): v for k,v in r.extra_pool_hit_pages.items()})
q2 = threading.Thread(target=do_query2)
q2.start(); q2.join()
print("AFTER unrelated writes (cross-thread):", result["query2"])
print("KV present now:", backend.batch_exists_v2(chain, []).kv_hit_pages)
backend.close()
