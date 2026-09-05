"""Decisive e28 probe: does the live signature (kv_hit_pages=0,
sidecar_hits={'kv':9}, no mamba) arise from TRAILING or only ALL_PAGES?

Uses the REAL live node boundary hashes from t38c:
  node19 (3 pages, root child):  last=cb3d0866...  (query chain[2])
  node22 (6 pages, parent=node19): last=f9f63a...   (query chain[8])

Both MAMBA keys committed (52 live mamba writes). The query chain[0..8]
has KV pages 0..8 all present (kv_pages=9).
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
NODE22_LAST = "f9f63a58852740519d5d7a850a8b6591a841ae26148e7880dce4675b75617b25"

def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_dec_")
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

        # query chain[0..8] -- KV pages all present, mamba only at 2 and 8.
        chain = [f"k{i:02d}" for i in range(9)]
        chain[2] = NODE19_LAST
        chain[8] = NODE22_LAST

        # Write KV (all 9) + MAMBA (both node last hashes) exactly as live.
        backend.batch_set_v1(chain, torch.arange(9, dtype=torch.int64))
        for last, idx in ((NODE19_LAST, 50), (NODE22_LAST, 51)):
            backend.batch_set_v2([PoolTransfer(name=PoolName.MAMBA,
                host_indices=torch.tensor([idx], dtype=torch.int64),
                keys=[last], hit_policy=PoolHitPolicy.TRAILING_PAGES)])

        # Verify both mamba keys present in index
        for nm, k in (("node19", NODE19_LAST), ("node22", NODE22_LAST)):
            sk = backend._component_key(PoolName.MAMBA, k)
            print(f"  {nm} mamba present: {backend._allocator.lookup(sk) is not None}")

        # TRAILING with live PREFETCH shape (keys=["__placeholder__"] -> trailing=1)
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=["__placeholder__"], hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        print(f"\nTRAILING(placeholder): kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # TRAILING with keys expanded to full chain (trailing=9)
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=list(chain), hit_policy=PoolHitPolicy.TRAILING_PAGES)])
        print(f"TRAILING(chain keys, trailing=9): kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # ALL_PAGES
        res = backend.batch_exists_v2(chain, [PoolTransfer(name=PoolName.MAMBA,
            host_indices=None, keys=["__placeholder__"], hit_policy=PoolHitPolicy.ALL_PAGES)])
        print(f"ALL_PAGES: kv_hit={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # The live signature (kv_hit=0, extra={'kv':9}) appears under which?
        print("\nLIVE signature = kv_hit=0, extra={'kv':9} (no mamba)")
    finally:
        if backend is not None:
            backend.close()
        bp.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
