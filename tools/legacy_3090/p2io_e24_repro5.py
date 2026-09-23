"""e24 deterministic repro #5: TRAILING_PAGES key divergence when the
written node's last page is beyond the query's present prefix.

Hypothesis (from live d48b8c91, node57): the mamba BACKUP_STORAGE write
registers ONLY keys=[node.hash_value[-1]] (the node's very last page).  The
read-side PREFETCH query carries a TRAILING_PAGES(1) sidecar that checks
present(_component_key(MAMBA, query_chain[kv_pages-1])) -- the last PRESENT
query page.

When the node has grown past the query's present prefix (the query only
sees a shorter prefix, or the node's chain is longer than what is present),
the last present page is an INTERIOR page whose mamba key was never
registered (only the node's final page was).  Result: mamba boundary=0,
final_pages=0, storage_hit=0 even though ALL KV pages are present.

Write 2048 KV pages + register mamba key ONLY for the node's LAST page
(page 2047).  Query a chain where only the first 1024 pages are present;
the mamba trailing(1) check on page 1023 must MISS -> clamp to 0.
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

_refhash_page_hashes = teb._refhash_page_hashes

tmpdir = tempfile.mkdtemp(prefix="e24_v5_")
backend = teb.ExtentFileBackend(
    teb._make_config(
        model_name="qwen3.5-9b-gptq",
        extra_config={"storage_dir": tmpdir, "extent_size": "16Ki", "file_size": "256Mi"},
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

# node writes 2048 pages; mamba registers ONLY its last page (2047)
n_node = 2048
span = list(range(100, 100 + n_node * page_size))
node_chain = _refhash_page_hashes(span, seed_hex, page_size)
assert backend.batch_set(node_chain, [bytearray(b"x"*1000) for _ in node_chain])
assert backend.batch_set_v2([transfer(PoolName.MAMBA, [node_chain[-1]])])[PoolName.MAMBA] == [True]
print("mamba write key (node last page):", node_chain[-1][:16])

# query a chain whose first 1024 pages == node's first 1024 (present), but
# page 1023 != node last page (2047).  live: only first 1024 present.
n_query = 2048
qspan = list(range(100, 100 + n_query * page_size))
q_chain = _refhash_page_hashes(qspan, seed_hex, page_size)
# make pages 1024.. absent (don't write them) -> kv_pages = 1024
# (already only wrote all 2048; so instead simulate by querying only 1024 present:
#  we wrote full node, so everything present.  To force kv_pages=1024 we need
#  pages 1024.. absent.  So write only first 1024 of a DIFFERENT longer chain.
# Redo cleanly below.)
backend.close()

# ---- clean variant: node wrote 2048, but mamba key only at last page;
# query sees only first 1024 pages present (1024..2047 absent). ----
tmpdir2 = tempfile.mkdtemp(prefix="e24_v5b_")
b2 = teb.ExtentFileBackend(
    teb._make_config(
        model_name="qwen3.5-9b-gptq",
        extra_config={"storage_dir": tmpdir2, "extent_size": "16Ki", "file_size": "256Mi"},
    )
)
kv2 = teb._PagePool(1000, slots=4000)
mamba2 = teb._PagePool(1000, slots=4000)
b2.register_mem_host_pool_v2(kv2, PoolName.KV)
b2.register_mem_host_pool_v2(mamba2, PoolName.MAMBA)

# build one continuous 2048-page chain
chain_full = _refhash_page_hashes(list(range(100, 100+2048)), seed_hex, page_size)
# write KV pages 0..1023 only (pages 1024.. absent)
assert b2.batch_set(chain_full[:1024], [bytearray(b"y"*1000) for _ in range(1024)])
# mamba key registered for node's LAST page (2047) -- as BACKUP_STORAGE does
assert b2.batch_set_v2([transfer(PoolName.MAMBA, [chain_full[-1]])])[PoolName.MAMBA] == [True]

kv_present = next((i for i in range(len(chain_full)) if b2._allocator.lookup(chain_full[i]+b2.config_suffix) is None), len(chain_full))
print("KV present prefix:", kv_present)
print("last present page hash == node last page hash:",
      chain_full[kv_present-1] == chain_full[-1])

r = b2.batch_exists_v2(
    chain_full,
    [transfer(PoolName.MAMBA, ["__placeholder__"], hp=PoolHitPolicy.TRAILING_PAGES)],
)
print("RESULT kv_hit_pages:", r.kv_hit_pages, "extra:", {
    getattr(k, "value", k): v for k, v in r.extra_pool_hit_pages.items()})
b2.close()
