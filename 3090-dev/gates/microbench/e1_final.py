#!/usr/bin/env python3
"""E1 final CPU-only microbenchmark (frozen v1). No GPU, no server, no ports."""
from __future__ import annotations
import gc, json, os, statistics, sys, threading, time, faulthandler
faulthandler.dump_traceback_later(300, exit=True)
assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
import torch
assert not torch.cuda.is_available()
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.storage.extent.extent_file_backend import _page_byte_view
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

def _p(m): print(m, file=sys.stderr, flush=True)

NUM_MAMBA_LAYERS=24; TEMPORAL_SHAPE=(32,128,128); CONV_SHAPE=(8192,3)
KV_LAYER_NUM=8; KV_HEAD_NUM=4; KV_HEAD_DIM=256; KV_DTYPE=torch.float8_e4m3fn
KV_BATCH=1024; CRC_PAYLOAD=122_920; CRC_AVG_FRAME=42_659

R={"meta":{"torch":torch.__version__,"cuda":torch.cuda.is_available(),
          "torch_threads":torch.get_num_threads(),"switchinterval":sys.getswitchinterval(),
          "cpus":os.cpu_count()},
   "geometry":{},"alone":{},"corun":{}}

class O: pass
def make_mamba():
    mc=O(); mc.temporal=torch.zeros((NUM_MAMBA_LAYERS,1)+TEMPORAL_SHAPE,dtype=torch.float32)
    mc.conv=[torch.zeros((NUM_MAMBA_LAYERS,1)+CONV_SHAPE,dtype=torch.bfloat16)]
    dp=O(); dp.num_mamba_layers=NUM_MAMBA_LAYERS; dp.mamba_cache=mc; dp.size=2; dp.device="cpu"
    return MambaPoolHost(dp,1.0,0,pin_memory=False,device="cpu",layout="page_first")
def make_kv():
    dp=O(); dp.layer_num=KV_LAYER_NUM; dp.head_num=KV_HEAD_NUM; dp.head_dim=KV_HEAD_DIM
    dp.store_dtype=KV_DTYPE; dp.size=KV_BATCH+1; dp.start_layer=0; dp.end_layer=KV_LAYER_NUM; dp.device="cpu"
    return MHATokenToKVPoolHost(dp,1.0,0,page_size=1,layout="page_first",pin_memory=False,device="cpu")

def stats(xs):
    s=sorted(xs); n=len(s)
    pct=lambda p: s[min(n-1,int(p*n))]
    return {"n":n,"min_ms":min(s)/1e6,"p25_ms":pct(.25)/1e6,"median_ms":statistics.median(s)/1e6,
            "p75_ms":pct(.75)/1e6,"p95_ms":pct(.95)/1e6,"max_ms":max(s)/1e6,
            "mean_ms":statistics.fmean(s)/1e6,"raw_ms":[x/1e6 for x in xs]}

class Busy(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True); self.stop=False; self.ready=threading.Event()
        self.reset()
    def reset(self):
        self.iters=0; self.max_gap_ns=0; self.sum_ns=0
        self.stalls={2_000_000:0,4_000_000:0,5_000_000:0,6_000_000:0,10_000_000:0,
                     50_000_000:0,100_000_000:0}
    def run(self):
        n=1; last=time.perf_counter_ns(); self.ready.set()
        while not self.stop:
            n=n+1; now=time.perf_counter_ns(); d=now-last
            if d>self.max_gap_ns: self.max_gap_ns=d
            self.sum_ns+=d
            st=self.stalls
            for th in st:
                if d>=th: st[th]+=1
            self.iters+=1; last=now
    def snap(self):
        return {"iters":self.iters,"max_gap_ms":self.max_gap_ns/1e6,
                "mean_gap_us":(self.sum_ns/self.iters/1e3) if self.iters else 0,
                "stalls_ge":{f"{k//1_000_000}ms":v for k,v in self.stalls.items()}}

def corun(name, fn, reps):
    lp=Busy(); lp.start(); lp.ready.wait(); time.sleep(0.5); base=lp.snap()
    fn()  # warm
    lp.reset(); gc.disable()
    walls=[]; cpus=[]
    for _ in range(reps):
        w=time.perf_counter_ns(); c=time.thread_time_ns()
        fn()
        cpus.append(time.thread_time_ns()-c); walls.append(time.perf_counter_ns()-w)
    gc.enable(); wsum=sum(walls)
    cont=lp.snap(); lp.stop=True; lp.join(2.0)
    R["corun"][name]={"baseline_loop":base,"contended_loop":cont,
        "contended_window_ms":wsum/1e6,"reps":reps,
        "wall":stats(walls),"thread_cpu":stats(cpus),
        "baseline_stall_rate_per_s":{k:v/0.5 for k,v in base["stalls_ge"].items()},
        "contended_stall_rate_per_s":{k:v/(wsum/1e9) for k,v in cont["stalls_ge"].items()}}

def main():
    mp=make_mamba(); kp=make_kv()
    _p("pools built")
    # geometry
    R["geometry"]["mamba_page_bytes"]=mp.get_data_page(1).numel()
    R["geometry"]["kv_page_bytes"]=kp.get_data_page(0,flat=True).numel()
    R["geometry"]["kv_batch_bytes"]=KV_BATCH*R["geometry"]["kv_page_bytes"]
    R["geometry"]["full_attention_layers"]=KV_LAYER_NUM
    R["geometry"]["mamba_layers"]=NUM_MAMBA_LAYERS

    reps=30
    for _ in range(3): mp.get_data_page(1)
    t=[]; 
    for _ in range(reps):
        s=time.perf_counter_ns(); mp.get_data_page(1); t.append(time.perf_counter_ns()-s)
    R["alone"]["mamba_get_data_page"]=stats(t)
    t=[]
    for _ in range(reps):
        s=time.perf_counter_ns(); _page_byte_view(mp.get_data_page(1)); t.append(time.perf_counter_ns()-s)
    R["alone"]["mamba_page_byte_view"]=stats(t)

    for _ in range(3): [kp.get_data_page(int(i),flat=True) for i in range(KV_BATCH)]
    b=[]; v=[]
    for _ in range(reps):
        s=time.perf_counter_ns()
        vals=[kp.get_data_page(int(i),flat=True) for i in range(KV_BATCH)]
        b.append(time.perf_counter_ns()-s)
        s=time.perf_counter_ns(); _=[_page_byte_view(x) for x in vals]; v.append(time.perf_counter_ns()-s)
    R["alone"]["kv_batch_get_data_page_1024"]=stats(b)
    R["alone"]["kv_batch_page_byte_view_1024"]=stats(v)

    payload=bytes(bytearray((i*37+11)&0xFF for i in range(CRC_PAYLOAD)))
    avg_payload=payload[:CRC_AVG_FRAME]
    key_len=(CRC_PAYLOAD-40)//KV_BATCH-23
    entries=[em.SetEntry(storage_key=b"k"*key_len,extent_id=i,offset=i*16384,length=16384,
                         generation=1,component=1) for i in range(KV_BATCH)]
    sp=em.SetPayload(group_epoch=b"\x00"*16,group_seq=0,batch_id=1,member_index=0,member_count=1,entries=entries)
    set_payload=em.encode_set_payload(sp)
    R["geometry"]["set_payload_1024_bytes"]=len(set_payload)
    c=[]; 
    for _ in range(reps):
        s=time.perf_counter_ns(); em.crc32c(payload); c.append(time.perf_counter_ns()-s)
    R["alone"]["crc32c_max_frame_122920B"]=stats(c)
    ca=[]
    for _ in range(reps):
        s=time.perf_counter_ns(); em.crc32c(avg_payload); ca.append(time.perf_counter_ns()-s)
    R["alone"]["crc32c_avg_frame_42659B"]=stats(ca)
    e=[]
    for _ in range(20):
        s=time.perf_counter_ns(); em.encode_frame(em.FRAME_SET,1,set_payload); e.append(time.perf_counter_ns()-s)
    R["alone"]["encode_frame_1024entries"]=stats(e)
    _p("alone done")

    def mamba_op():
        mp.get_data_page(1)
        _page_byte_view(mp.get_data_page(1))
    corun("mamba_page_materialise", mamba_op, 10); _p("corun mamba done")
    def kv_op():
        vals=[kp.get_data_page(int(i),flat=True) for i in range(KV_BATCH)]
        _=[_page_byte_view(x) for x in vals]
    corun("kv_batch_marshal", kv_op, 3); _p("corun kv done")
    def crc_op():
        em.crc32c(payload)
    corun("crc32c_max_frame", crc_op, 20); _p("corun crc done")

    print(json.dumps(R,indent=2))

if __name__=="__main__":
    main()
