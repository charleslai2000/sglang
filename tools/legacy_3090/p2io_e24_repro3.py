"""e24 deterministic repro #3: mamba sidecar clamp.

Mirrors the live write/read semantics EXACTLY:
  write (BACKUP_STORAGE):
    KV  -> batch_set_v1 with keys = node.hash_value (full chain)
    MAMBA -> batch_set_v2 keys=[node.hash_value[-1]] (last page hash, ".mamba" suffix)
  read (PREFETCH -> _storage_hit_query):
    batch_exists_v2(hash_value, [PoolTransfer(MAMBA, keys=["__placeholder__"], TRAILING_PAGES)])

Question: does the read-side mamba lookup key (last present query page) match the
write-side registered key (last write node page)?
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

tmpdir = tempfile.mkdtemp(prefix="e24_v2_")
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

n = 4
chain = ["h%064d" % i for i in range(n)]  # fake full-chain page hashes

def transfer(name, keys, indices=None, hp=None):
    return PoolTransfer(name=name, host_indices=indices if indices is not None else list(range(len(keys))), keys=list(keys), hit_policy=hp)

# --- write side ---
# KV via v1 batch_set (raw keys; backend applies _storage_key suffix on both sides)
assert backend.batch_set(chain, [bytearray(b"x"*1000) for _ in chain])
# MAMBA via batch_set_v2, key = last page hash (matches BACKUP_STORAGE keys=[node.hash_value[-1]])
mamba_pages = [bytearray(b"m"*1000)]
assert backend.batch_set_v2([transfer(PoolName.MAMBA, [chain[-1]])])[PoolName.MAMBA] == [True]

print("KV present:", backend.batch_exists(chain))
print("mamba component key registered:",
      backend._allocator.lookup(chain[-1] + ".mamba" + backend.config_suffix) is not None)

# --- read side ---
# no sidecar: full chain should hit
r0 = backend.batch_exists_v2(chain, [])
print("no-sidecar kv_hit:", r0.kv_hit_pages)

# with mamba TRAILING_PAGES placeholder sidecar (live PREFETCH shape)
r1 = backend.batch_exists_v2(
    chain,
    [transfer(PoolName.MAMBA, ["__placeholder__"], hp=PoolHitPolicy.TRAILING_PAGES)],
)
print("mamba-sidecar kv_hit:", r1.kv_hit_pages, "extra:", {
    getattr(k, "value", k): v for k, v in r1.extra_pool_hit_pages.items()})
backend.close()
