import sys
sys.path.insert(0,"/opt/sglang/local-prod-v1.1-candidate/src/python")
from sglang.srt.mem_cache.storage.extent import extent_metadata as em
p="/data/l3/local-prod-v1.1/hicache.meta_-data-models-qwen35-9b-w4a16_0_1.manifest"
st=em.read_manifest(p)
print("checkpoint_lsn",st.checkpoint_lsn,"wal_floor",st.wal_floor,"wal_active_gen",st.wal_active_gen)
print("next_slot",st.next_slot,"n_entries",len(st.entries),"n_recency",len(st.recency_order),"n_groups",len(st.groups))
print("nonempty_generations",sum(1 for g in st.generations if g),"nonempty_slot_bytes",sum(1 for b in st.slot_bytes if b>0))
print("total_slot_bytes",sum(st.slot_bytes))
