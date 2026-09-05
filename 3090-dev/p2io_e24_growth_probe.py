"""e24 root-cause probe: mamba BACKUP_STORAGE registers node.hash_value[-1]
at WRITE time.  A node that GROWS (appends pages) after its mamba state was
backed up has a NEW last page whose mamba key was never registered.

Query side TRAILING_PAGES(1) checks present(_component_key(MAMBA,
query_chain[kv_pages-1])) -- the query's LAST PRESENT page.  When the node
grew, the query's last-present page (new last page) != registered mamba key
(old last page) -> boundary=0 -> clamp to 0 even though ALL KV present.

Simulates: write node with 1024 pages + mamba key for page 1023.  Then node
grows to 2048 pages (KV pages 1024..2047 written), but mamba key for page
2047 was NEVER written (BACKUP_STORAGE only wrote it when node was 1024).
Query the full 2048-page chain -> last-present page 2047, mamba missing.
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
page_size = 1
seed_hex = "9d373db168e3e6a03e12ea791ce33b00590b4652dd4618889639c8095ac017f7"

tmpdir = tempfile.mkdtemp(prefix="e24_growth_")
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

full = _refhash_page_hashes(list(range(100, 100+2048)), seed_hex, page_size)

# Phase 1: node is 1024 pages. KV + mamba(KEY=page1023) written.
assert backend.batch_set(full[:1024], [bytearray(b"x"*1000) for _ in range(1024)])
assert backend.batch_set_v2([tfer(PoolName.MAMBA, [full[1023]])])[PoolName.MAMBA] == [True]
print("phase1: mamba key registered for page1023:", full[1023][:16])
print("  query 1024-chain:", backend.batch_exists_v2(full[:1024], [tfer(PoolName.MAMBA,["__placeholder__"],hp=PoolHitPolicy.TRAILING_PAGES)]).kv_hit_pages)

# Phase 2: node GROWS to 2048. KV 1024..2047 written, but mamba NOT rewritten
# (BACKUP_STORAGE won't re-run for grown pages).
assert backend.batch_set(full[1024:2048], [bytearray(b"x"*1000) for _ in range(1024)])
print("\nphase2: node grew to 2048. mamba key still only page1023.")
print("  KV present:", backend.batch_exists_v2(full, []).kv_hit_pages)
print("  page2047 mamba key registered:",
      backend._allocator.lookup(full[2047] + ".mamba" + backend.config_suffix) is not None)
r = backend.batch_exists_v2(full, [tfer(PoolName.MAMBA,["__placeholder__"],hp=PoolHitPolicy.TRAILING_PAGES)])
print("  mamba-sidecar kv_hit:", r.kv_hit_pages, "extra:", {getattr(k,"value",k):v for k,v in r.extra_pool_hit_pages.items()})
backend.close()
