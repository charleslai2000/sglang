import sys, os
sys.path.insert(0, sys.argv[1])
os.environ.setdefault("CUDA_VISIBLE_DEVICES","")
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.storage.extent import extent_metadata as M
d=sys.argv[2]
cfg=HiCacheStorageConfig(extra_config={"storage_dir":d,"extent_size":"16Ki","file_size":"64Ki"},
  tp_rank=0,tp_size=1,pp_rank=0,pp_size=1,attn_cp_rank=0,attn_cp_size=1,is_mla_model=False,
  enable_storage_metrics=False,is_page_first_layout=True,model_name="testmodel")
mp=os.path.join(d,"hicache.meta_testmodel_0_1.manifest")
st=M.read_manifest(mp)
print("manifest: lsn=%d floor=%d active=%d entries=%s"%(st.checkpoint_lsn,st.wal_floor,st.wal_active_gen,[e.storage_key.decode() for e in st.entries]))
be=ExtentFileBackend(cfg)
print("allocator index keys:",sorted(be._allocator._index.keys()))
print("batch_get:",[ (k, g is not None) for k,g in zip(["a0","b0","a1","b1"], be.batch_get(["a0","b0","a1","b1"]))])
print("exists:", [(k,be.exists(k)) for k in ["a0","b0"]])
