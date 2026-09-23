"""Corrected decisive probe: node19 last=cb3d0866 at chain[2], node22 last
at chain[8] (unknown hash, simulate present as X22). Test TRAILING(placeholder)
boundary scan behavior when node19-last IS present at chain[2].

Live signature is kv_hit=0 ALWAYS. If node19's mamba key (chain[2]) is present,
TRAILING(placeholder) must find boundary>=3 -> kv_hit=3 at minimum, and add
mamba:3 to sidecar_hits. Live NEVER shows a mamba entry -> chain[2] not found
-> either ALL_PAGES or node19's mamba key absent from index.
"""
import os, sys, tempfile, shutil
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
import torch
from sglang.srt.mem_cache.pool_host import base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig, PoolName, PoolTransfer, PoolHitPolicy,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

NODE19_LAST = "cb3d0866ae2f84e097a306d0f1d6da46b3169c8a40010d611f899b65869cb200"
NODE22_LAST = "9999" + "a"*60  # simulate node22 last (chain[8]), present

def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_dec2_")
    bp = mock.patch.object(base.psutil, "virtual_memory",
        return_value=mock.Mock(available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64*(1024**3)))
    bp.start()
    backend = None
    try:
        N = 64
        device_pool = MHATokenToKVPool(size=N, page_size=1, dtype=torch.float16,
            head_num=2, head_dim=8, layer_num=1, device="cpu", enable_memory_saver=False)
        host_pool = MHATokenToKVPoolHost(device_pool=device_pool, host_to_device_ratio=2.0,
            host_size=0, page_size=1, layout="page_first", pin_memory=False, device="cpu",
            allocator_type="default")
        cfg = HiCacheStorageConfig(extra_config={"storage_dir": tmpdir, "extent_size": "64Mi",
            "file_size": "512Mi", "max_size": "20G", "min_free_space": "10G"},
            tp_rank=0, tp_size=1, pp_rank=0, pp_size=1, attn_cp_rank=0, attn_cp_size=1,
            is_mla_model=False, enable_storage_metrics=False, is_page_first_layout=True,
            model_name="testmodel")
        backend = ExtentFileBackend(cfg)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(host_pool, PoolName.MAMBA)
        for p in range(N):
            host_pool.kv_buffer[0, p] = float(p+1)
            host_pool.kv_buffer[1, p] = float(p+100)

        # query chain 0..8, KV all present, mamba at chain[2] and chain[8]
        chain = [f"k{i:02d}" for i in range(9)]
        chain[2] = NODE19_LAST
        chain[8] = NODE22_LAST
        backend.batch_set_v1(chain, torch.arange(9, dtype=torch.int64))
        backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
            host_indices=torch.tensor([50], dtype=torch.int64),
            keys=[NODE19_LAST], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
            host_indices=torch.tensor([51], dtype=torch.int64),
            keys=[NODE22_LAST], hit_policy=PoolHitPolicy.TRAILING_PAGES)])

        # Scenario A: live PREFETCH shape, TRAILING, keys=["__placeholder__"]
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=["__placeholder__"], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        print(f"A TRAILING(placeholder): kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # Scenario B: node19's mamba key ABSENT from index (only KV present)
        # -> remove mamba key for node19, keep node22
        # (simulate: node19 mamba write key mismatch)
        backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
            host_indices=torch.tensor([52], dtype=torch.int64),
            keys=[NODE22_LAST], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        # rebuild fresh backend without node19's mamba write:
        # Instead: check what boundary scan does when chain[2] not present but chain[8] present
        # (i.e. node19's mamba write key mismatch, node22's correct)
        backend.close()
        backend = ExtentFileBackend(cfg)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(host_pool, PoolName.MAMBA)
        backend.batch_set_v1(chain, torch.arange(9, dtype=torch.int64))
        # only node22 mamba key present (chain[8])
        backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
            host_indices=torch.tensor([51], dtype=torch.int64),
            keys=[NODE22_LAST], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=["__placeholder__"], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        print(f"B TRAILING(placeholder) chain[2] mamba absent, chain[8] present: kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # Scenario C: only node19 mamba key present (chain[2]), node22 absent
        backend.close()
        backend = ExtentFileBackend(cfg)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(host_pool, PoolName.MAMBA)
        backend.batch_set_v1(chain, torch.arange(9, dtype=torch.int64))
        backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
            host_indices=torch.tensor([50], dtype=torch.int64),
            keys=[NODE19_LAST], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=["__placeholder__"], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        print(f"C TRAILING(placeholder) chain[2] present, chain[8] absent: kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")
    finally:
        if backend is not None:
            backend.close()
        bp.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
