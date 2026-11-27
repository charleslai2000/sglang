"""Segment every scheduler.run_batch range from the nsys capture and report
per-range and per-phase GPU facts. Kernel rows are sorted by start so the
bisect window is valid."""
import sqlite3, collections, bisect, statistics as st, json
db=sqlite3.connect("nsys/gemma4.sqlite"); c=db.cursor()
S={i:v for i,v in c.execute("select id,value from StringIds")}
kr=list(c.execute("""select start,end,demangledName,registersPerThread,staticSharedMemory,
 dynamicSharedMemory,gridX,gridY,gridZ,blockX,blockY,blockZ from CUPTI_ACTIVITY_KIND_KERNEL
 where end>start order by start"""))
K=[(s,e,S.get(n,n),r,ss,ds,gx,gy,gz,bx,by,bz) for s,e,n,r,ss,ds,gx,gy,gz,bx,by,bz in kr]
starts=[k[0] for k in K]
R=sorted((s,e) for s,e,t in c.execute("select start,end,textId from NVTX_EVENTS where end is not null and textId is not null")
         if S.get(t)=="scheduler.run_batch")
def win(s,e):
    i=bisect.bisect_left(starts,s); o=[]
    while i<len(K) and K[i][0]<e: o.append(K[i]); i+=1
    return o
rows=[]
for i,(s,e) in enumerate(R):
    ks=win(s,e); busy=sum(k[1]-k[0] for k in ks)
    fwd=max((k[6] for k in ks if (k[2] or "").startswith("_fwd_kernel")), default=0)
    marlin=max((k[6] for k in ks if "marlin" in (k[2] or "").lower()), default=0)
    grid=collections.Counter(k[2][:26] for k in ks).most_common(3)
    rows.append(dict(i=i,s=s,e=e,dur=(e-s)/1e6,busy=busy/1e6,n=len(ks),fwdgx=fwd,marlin_m=marlin,top=grid))
for r in rows:
    print(f"{r['i']:3d} dur={r['dur']:8.2f}ms busy={r['busy']:8.2f}ms ({100*r['busy']/r['dur']:5.1f}%) n={r['n']:5d} fwdgx={r['fwdgx']:5d} marlinM={r['marlin_m']:4d} {[t[0] for t in r['top']]}")
json.dump(rows, open("range_index.json","w"), indent=1)
