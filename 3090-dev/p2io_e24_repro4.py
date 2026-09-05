"""e24 deterministic repro #4: partial-query mamba sidecar clamp.

Live d48b8c91 case: node57 wrote 1458 KV pages + 1 mamba key (its last page
hash).  A LATER query recomputes a LONGER chain (11858 tokens) whose first
1458 pages match node57 but extend past it (absent pages).

Expected correct behavior: kv_pages=1458 (present prefix), mamba trailing=1
checks the last PRESENT page hash (== node57's last page, which IS
registered) -> boundary=1458 -> kv_hit_pages=1458.

We verify whether the mamba read key (query page at last-present position)
matches the write-side registered mamba key.
"""
import os
import sys
import tempfile

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

# Load the refhash oracle used by the round-trip test
_refhash_page_hashes = teb._refhash_page_hashes

tmpdir = tempfile.mkdtemp(prefix="e24_v4_")
backend = teb.ExtentFileBackend(
    teb._make_config(
        model_name="qwen3.5-9b-gptq",
        extra_config={"storage_dir": tmpdir, "extent_size": "16Ki", "file_size": "64Mi"},
    )
)
kv = teb._PagePool(1000, slots=4000)
mamba = teb._PagePool(1000, slots=4000)
backend.register_mem_host_pool_v2(kv, PoolName.KV)
backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

def transfer(name, keys, indices=None, hp=None):
    return PoolTransfer(name=name, host_indices=indices if indices is not None else list(range(len(keys))), keys=list(keys), hit_policy=hp)

page_size = 1
seed_hex = "9d373db168e3e6a03e12ea791ce33b00590b4652dd4618889639c8095ac017f7"

# node57: 1458 pages written
n_write = 1458
span_write = list(range(100, 100 + n_write * page_size))
write_chain = _refhash_page_hashes(span_write, seed_hex, page_size)
print("write_chain len:", len(write_chain))

# write KV (v1 batch_set = node57's full chain)
assert backend.batch_set(write_chain, [bytearray(b"x"*1000) for _ in write_chain])
# write mamba: BACKUP_STORAGE keys=[node.hash_value[-1]]
assert backend.batch_set_v2([transfer(PoolName.MAMBA, [write_chain[-1]])])[PoolName.MAMBA] == [True]
print("mamba write key:", write_chain[-1][:16], "registered:",
      backend._allocator.lookup(write_chain[-1] + ".mamba" + backend.config_suffix) is not None)

# query: longer chain (11858 tokens) whose first 1458 pages == node57 chain
n_query = 11858
span_query = list(range(100, 100 + n_query * page_size))
query_chain = _refhash_page_hashes(span_query, seed_hex, page_size)
print("query_chain len:", len(query_chain))
print("query[0:2]==write[0:2]:", query_chain[:2] == write_chain[:2])
print("query[1457]==write[1457] (mamba key pos):", query_chain[1457] == write_chain[1457])

# how many present in KV
def present(chain):
    return next((i for i in range(len(chain)) if backend._allocator.lookup(chain[i]+backend.config_suffix) is None), len(chain))
print("KV present prefix:", present(query_chain))

# batch_exists_v2 with mamba trailing sidecar (live PREFETCH placeholder shape)
r = backend.batch_exists_v2(
    query_chain,
    [transfer(PoolName.MAMBA, ["__placeholder__"], hp=PoolHitPolicy.TRAILING_PAGES)],
)
print("RESULT kv_hit_pages:", r.kv_hit_pages, "extra:", {
    getattr(k, "value", k): v for k, v in r.extra_pool_hit_pages.items()})
backend.close()
