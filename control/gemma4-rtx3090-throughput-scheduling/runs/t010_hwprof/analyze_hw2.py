"""Hardware-window analysis of the nsys capture: no per-range kernel attribution.
Kernels are merged into contiguous GPU-active spans; each span is classified by
kernel composition (prefill vs decode) and joined with the GPU-metrics series."""
import sqlite3, collections, json, statistics as st
db=sqlite3.connect("nsys/gemma4.sqlite"); c=db.cursor()
S={i:v for i,v in c.execute("select id,value from StringIds")}
K=[(s,e,S.get(n,"?"),r,ss,gx) for s,e,n,r,ss,gx in c.execute(
 "select start,end,demangledName,registersPerThread,staticSharedMemory,gridX from CUPTI_ACTIVITY_KIND_KERNEL where end>start order by start")]
# merge into GPU-active spans (gap > 1.0 ms starts a new span)
spans=[]; cur=[K[0][0],K[0][1],[]]
for s,e,n,r,ss,gx in K:
    if s-cur[1] > 1_000_000: spans.append(tuple(cur)); cur=[s,e,[]]
    cur[1]=max(cur[1],e); cur[2].append((s,e,n,r,ss,gx))
spans.append(tuple(cur))
def cls(kernels):
    names=[k[2] for k in kernels]
    ext=any(n.startswith("_fwd_kernel") and not n.startswith("_fwd_kernel_stage") for n in names)
    dec=any("grouped_kernel_stage1" in n for n in names)
    return "prefill" if ext and not dec else ("decode" if dec else "other")
# GPU metrics
mid={m:i for i,m in c.execute("select metricId,metricName from TARGET_INFO_GPU_METRICS")}
series=collections.defaultdict(list)
for ts,mi,v in c.execute("select timestamp,metricId,value from GPU_METRICS where metricId in (%s)" %
        ",".join(str(mid[m]) for m in ("SMs Active [Throughput %]","SM Issue [Throughput %]","Tensor Active [Throughput %]",
            "DRAM Read Bandwidth [Throughput %]","DRAM Write Bandwidth [Throughput %]","GPU Active [Throughput %]",
            "GPC Clock Frequency [MHz]","Compute Warps in Flight [Throughput %]"))):
    series[mi].append((ts,v))
for mi in series: series[mi].sort()
def avg(mi,s,e):
    xs=[v for t,v in series[mi] if s<=t<=e]
    return st.mean(xs) if xs else None
out=[]
for s,e,kernels in spans:
    busy=sum(min(e2,e)-max(s2,s) for s2,e2,*_ in kernels)
    out.append(dict(start=s,end=e,dur_ms=(e-s)/1e6,busy_ms=busy/1e6,n=len(kernels),cls=cls(kernels),
        sm_active=avg(mid["SMs Active [Throughput %]"],s,e), sm_issue=avg(mid["SM Issue [Throughput %]"],s,e),
        tensor=avg(mid["Tensor Active [Throughput %]"],s,e), dram_r=avg(mid["DRAM Read Bandwidth [Throughput %]"],s,e),
        dram_w=avg(mid["DRAM Write Bandwidth [Throughput %]"],s,e), gpu=avg(mid["GPU Active [Throughput %]"],s,e),
        clock=avg(mid["GPC Clock Frequency [MHz]"],s,e), warps=avg(mid["Compute Warps in Flight [Throughput %]"],s,e),
        top=collections.Counter(k[2][:34] for k in kernels).most_common(3)))
agg=collections.defaultdict(list)
for r in out: agg[r["cls"]].append(r)
print(f"spans={len(out)}  kernel total busy={sum(k[1]-k[0] for k in K)/1e9:.2f}s")
for k,v in agg.items():
    def m(f):
        xs=[r[f] for r in v if r[f] is not None]; return st.mean(xs) if xs else float('nan')
    print(f"{k:8s} n={len(v):3d} dur={sum(r['dur_ms'] for r in v)/1000:7.2f}s busy={sum(r['busy_ms'] for r in v)/1000:6.2f}s "
          f"duty={100*sum(r['busy_ms'] for r in v)/sum(r['dur_ms'] for r in v):5.1f}% SMsActive={m('sm_active'):5.1f}% SMissue={m('sm_issue'):5.1f}% "
          f"Tensor={m('tensor'):5.1f}% DRAMr={m('dram_r'):5.1f}% DRAMw={m('dram_w'):5.1f}% GPU={m('gpu'):5.1f}% clk={m('clock'):6.0f}MHz warps={m('warps'):5.1f}%")
# kernel table
kt=c.execute("""select demangledName,count(*),sum(end-start) d,avg(registersPerThread),max(staticSharedMemory),
  max(gridX),max(blockX) from CUPTI_ACTIVITY_KIND_KERNEL where end>start group by demangledName order by d desc limit 18""").fetchall()
print("\nTOP KERNELS (whole capture)")
tot=sum(k[1]-k[0] for k in K)
for n,cnt,d,r,ss,gx,bx in kt:
    print(f"{d/1e6:8.1f}ms {100*d/tot:5.1f}% {cnt:7d} regs={float(r):4.0f} smem={ss:6d} gridX={gx:4d} blk={bx:4d}  {S.get(n,'?')[:78]}")
print()
print("PREFILL SPANS (marlin gridX ~= tokens/128)")
for r in out:
    if r["cls"]!="prefill": continue
    print(f"  dur={r['dur_ms']:8.1f}ms busy={r['busy_ms']:8.1f}ms duty={100*r['busy_ms']/r['dur_ms']:5.1f}% SMs={r['sm_active']:5.1f}% "
          f"issue={r['sm_issue']:4.1f}% tensor={r['tensor']:5.1f}% dramR={r['dram_r']:5.1f}% dramW={r['dram_w']:5.1f}% "
          f"warps={r['warps']:4.1f}% gpu={r['gpu']:5.1f}% n={r['n']}")
print()
print("DECODE SPANS by busy (top 12)")
for r in sorted([r for r in out if r['cls']=='decode'], key=lambda x:-x['busy_ms'])[:12]:
    print(f"  dur={r['dur_ms']:8.2f}ms busy={r['busy_ms']:8.2f}ms SMs={r['sm_active']:5.1f}% issue={r['sm_issue']:4.1f}% "
          f"tensor={r['tensor']:5.1f}% dramR={r['dram_r']:5.1f}% dramW={r['dram_w']:5.1f}% warps={r['warps']:4.1f}% gpu={r['gpu']:5.1f}% n={r['n']}")
json.dump(out, open("hw_spans.json","w"), indent=1)
