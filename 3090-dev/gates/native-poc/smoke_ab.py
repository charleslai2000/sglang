import hashlib, os, shutil, tempfile
from pathlib import Path

def make_cfg(d):
    from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
    return HiCacheStorageConfig(
        extra_config={"storage_dir": d, "extent_size": "16Ki", "file_size": "64Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True,
        model_name="testmodel",
    )

def run(d, native):
    if native:
        os.environ["SGLANG_L3_NATIVE_WRITE_PATH"] = "1"
    else:
        os.environ.pop("SGLANG_L3_NATIVE_WRITE_PATH", None)
    from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
    be = ExtentFileBackend(make_cfg(str(d)))
    vals = [bytes([i % 251]) * 1000 for i in range(6)]
    keys = [f"k{i:04d}" for i in range(6)]
    ok = be.batch_set(keys, vals)
    assert ok, "batch_set failed"
    ok2 = be.batch_set(["z1","z2"], [bytes([9])*1000, bytes([8])*1000])
    assert ok2
    wal = Path(be._storage_dir) / f"hicache.meta{be.config_suffix}.wal.0"
    data = Path(be._storage_dir) / f"hicache.data{be.config_suffix}"
    wb = wal.read_bytes(); db = data.read_bytes()
    stats = be.stats_snapshot()
    be.close()
    os.environ.pop("SGLANG_L3_NATIVE_WRITE_PATH", None)
    return wb, db, stats

root = Path(tempfile.mkdtemp(prefix="l3ab_"))
da = root/"a"; db_ = root/"b"; da.mkdir(); db_.mkdir()
wa, dda, sa = run(da, False)
wb, ddb, sb = run(db_, True)
print("wal sha A", hashlib.sha256(wa).hexdigest())
print("wal sha B", hashlib.sha256(wb).hexdigest())
print("wal equal", wa == wb, "lens", len(wa), len(wb))
# data files are 64Ki sparse; compare nonzero extents by hashing
print("data equal", dda == ddb, "lens", len(dda), len(ddb))
print("stats A", {k: sa[k] for k in ("pwrites","bytes_written","wal_active_bytes")})
print("stats B", {k: sb[k] for k in ("pwrites","bytes_written","wal_active_bytes")})
shutil.rmtree(root, ignore_errors=True)
