import sys, os
TREE="/opt/sglang/local-prod-v1.1.2-candidate"
sys.path.insert(0, os.path.join(TREE,"src","python"))
from sglang.srt.mem_cache.storage.extent.extent_allocator import ExtentAllocator, ExtentRef

P=16384
def run(num_slots, extent_size, batch_pages, total_pages, label):
    alloc=ExtentAllocator(extent_size, num_slots)
    def backend_write(pages, ki):
        # replicate backend plan->relocate-feasibility->apply_drops->commit_install
        keys=[f"k{ki}_{i}" for i in range(pages)]
        lens=[P]*pages
        refs, passed, drop_events = alloc.plan_split(list(zip(keys,lens)), None)
        victim_slots={s for s,_ in drop_events}
        # victims live bytes
        victims=[(k, alloc._index[k]) for s in victim_slots for k in sorted(alloc._slot_keys[s])
                 if alloc._index.get(k) is not None and alloc._index[k].extent_id==s and alloc._index[k].generation==alloc._generations[s]]
        vbytes=sum(r.length for _,r in victims)
        dest=None
        if victims:
            excluded=set(victim_slots)
            excluded.update(r.extent_id for r in refs if r is not None)
            start=max((r.extent_id for r in refs if r is not None), default=alloc._next_slot)
            dest=alloc.plan_relocation(sorted(victim_slots), [(k,r.length) for k,r in victims], sorted(excluded), start)
        reloc_ok = (not victims) or (dest is not None)
        if not reloc_ok:
            return {"refused":True, "passed":sorted(victim_slots), "vbytes":vbytes, "nrefs":len(victims)}
        alloc.apply_drops(drop_events)
        alloc.commit_install(keys, refs)
        return {"refused":False, "passed":sorted(victim_slots), "vbytes":vbytes, "nrefs":len(victims),
                "relocated":len(victims)}
    ki=0
    first_refuse=None
    writes=0
    for start in range(0,total_pages,batch_pages):
        ki+=1
        pages=min(batch_pages, total_pages-start)
        r=backend_write(pages, ki)
        if r["refused"] and first_refuse is None:
            first_refuse=(start,r)
            print(f"{label}: First REFUSAL at page {start}: {r}")
            break
        writes+=1
    used=alloc.used_bytes
    print(f"{label}: writes={writes} used={used}/{num_slots*extent_size} slots_used={sum(1 for b in alloc._slot_bytes if b>0)} next_slot={alloc._next_slot}")
    return first_refuse

# Scenario 1: file exactly (chain slots + margin)
E=64<<20
# chain 62000 pages at 16KiB; pages per slot = 4096
chain=62000
slots_for_chain = (chain + 4095)//4096
for margin in (4,8,16):
    S=slots_for_chain+margin
    run(S,E,1024, chain + 4096*S, f"margin={margin} S={S}")
