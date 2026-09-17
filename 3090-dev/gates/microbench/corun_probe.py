import os, sys, time, threading, gc
os.environ.setdefault("CUDA_VISIBLE_DEVICES","")
import torch
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
def log(m): print(m, file=sys.stderr, flush=True)
class O: pass
# kv pool
dp=O(); dp.layer_num=8; dp.head_num=4; dp.head_dim=256; dp.store_dtype=torch.float8_e4m3fn
dp.size=1025; dp.start_layer=0; dp.end_layer=8; dp.device="cpu"
kp=MHATokenToKVPoolHost(dp,1.0,0,page_size=1,layout="page_first",pin_memory=False,device="cpu")
def kv_op():
    return [kp.get_data_page(int(i),flat=True) for i in range(1024)]

class Loop(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.stop=False; self.ready=threading.Event()
        self.iters=0; self.max_gap_ns=0; self.gaps=[]
    def run(self):
        last=time.perf_counter_ns(); self.ready.set()
        while not self.stop:
            now=time.perf_counter_ns(); d=now-last
            if d>self.max_gap_ns: self.max_gap_ns=d
            if d>2_000_000: self.gaps.append(d)
            self.iters+=1; last=now

def measure(n, threaded, gc_off):
    if gc_off: gc.disable()
    lp=Loop() if threaded else None
    if lp: lp.start(); lp.ready.wait(); time.sleep(0.5)
    kv_op()  # warm
    xs=[]; t00=time.perf_counter_ns()
    for _ in range(n):
        t=time.perf_counter_ns(); kv_op(); xs.append(time.perf_counter_ns()-t)
    win=time.perf_counter_ns()-t00
    out={"threaded":threaded,"gc_off":gc_off,"n":n,"window_ms":win/1e6,
         "min_ms":min(xs)/1e6,"med_ms":sorted(xs)[n//2]/1e6,"max_ms":max(xs)/1e6}
    if lp:
        lp.stop=True; lp.join(2.0)
        out["loop_iters"]=lp.iters; out["loop_max_gap_ms"]=lp.max_gap_ns/1e6
        out["loop_gaps_ge2ms"]=len(lp.gaps); out["loop_rate_per_s"]=lp.iters/(win/1e9)
    else:
        out["loop_iters"]=None; out["loop_max_gap_ms"]=None
        out["loop_gaps_ge2ms"]=None; out["loop_rate_per_s"]=None
    if gc_off: gc.enable()
    return out

log("A alone gc on: "+str(measure(3,False,False)))
log("B alone gc off: "+str(measure(3,False,True)))
log("C threaded gc off: "+str(measure(3,True,True)))
log("D threaded gc on: "+str(measure(3,True,False)))
log("E alone gc on again: "+str(measure(3,False,False)))
