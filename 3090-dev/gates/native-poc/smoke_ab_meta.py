import hashlib, os, shutil, tempfile
from pathlib import Path
from unittest import mock

def make_cfg(d, name="metatest"):
    from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
    return HiCacheStorageConfig(
        extra_config={"storage_dir": d, "extent_size": "16Ki", "file_size": "64Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True,
        model_name=name,
    )

def build_pool():
    import torch
    from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
    from sglang.srt.mem_cache.pool_host import base
    from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
    budget = mock.patch.object(
        base.psutil, "virtual_memory",
        return_value=mock.Mock(available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64*(1024**3)))
    budget.start()
    PAGE_SIZE, LAYER_NUM, HEAD_NUM, HEAD_DIM = 2, 2, 2, 4
    device_pool = MHATokenToKVPool(size=PAGE_SIZE*2, page_size=PAGE_SIZE, dtype=torch.float16,
        head_num=HEAD_NUM, head_dim=HEAD_DIM, layer_num=LAYER_NUM, device="cpu",
        enable_memory_saver=False)
    host_pool = MHATokenToKVPoolHost(device_pool=device_pool, host_to_device_ratio=2.0,
        host_size=0, page_size=PAGE_SIZE, layout="page_first", pin_memory=False,
        device="cpu", allocator_type="default")
    return budget, host_pool, torch

def run(d, native):
    if native:
        os.environ["SGLANG_L3_NATIVE_WRITE_PATH"] = "1"
    else:
        os.environ.pop("SGLANG_L3_NATIVE_WRITE_PATH", None)
    from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
    from sglang.srt.mem_cache.hicache_storage import PoolName, PoolTransfer
    budget, host_pool, torch = build_pool()
    be = ExtentFileBackend(make_cfg(str(d)))
    be.register_mem_host_pool_v2(host_pool, PoolName.KV)
    n = host_pool.page_num
    ps = host_pool.page_size
    for p in range(n):
        host_pool.kv_buffer[0, p*ps:(p+1)*ps] = float(p+1)
        host_pool.kv_buffer[1, p*ps:(p+1)*ps] = float(p+100)
    keys = [f"k{i:04d}" for i in range(n)]
    idx = torch.arange(n*ps, dtype=torch.int64)
    res = be.batch_set_v2([PoolTransfer(name=PoolName.KV, host_indices=idx, keys=keys)])
    assert res[PoolName.KV] == [True]*n, res
    wal = Path(be._storage_dir) / f"hicache.meta{be.config_suffix}.wal.0"
    data = Path(be._storage_dir) / f"hicache.data{be.config_suffix}"
    wb = wal.read_bytes(); db = data.read_bytes()
    nreg = len(getattr(be, "_native_registered_arenas", ()))
    be.close(); budget.stop()
    os.environ.pop("SGLANG_L3_NATIVE_WRITE_PATH", None)
    return wb, db, n, nreg

root = Path(tempfile.mkdtemp(prefix="l3abm_"))
da = root/"a"; db_ = root/"b"; da.mkdir(); db_.mkdir()
wa, dda, n, nrega = run(da, False)
wb, ddb, _, nregb = run(db_, True)
print("pages", n)
print("wal sha A", hashlib.sha256(wa).hexdigest()[:32], "B", hashlib.sha256(wb).hexdigest()[:32])
print("wal equal", wa == wb, len(wa), len(wb))
print("data equal", dda == ddb, len(dda), len(ddb))
print("registered arenas A", nrega, "B", nregb)
shutil.rmtree(root, ignore_errors=True)
