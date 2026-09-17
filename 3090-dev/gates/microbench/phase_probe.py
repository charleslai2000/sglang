import os, sys, time, threading
os.environ.setdefault("CUDA_VISIBLE_DEVICES","")
import torch
def log(m): print(m, file=sys.stderr, flush=True)
t0=time.time(); log("importing...")
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.storage.extent.extent_file_backend import _page_byte_view
from sglang.srt.mem_cache.storage.extent import extent_metadata as em
log(f"imports done {time.time()-t0:.2f}s")
NUM=24; T=(32,128,128); C=(8192,3)
class O: pass
mc=O(); mc.temporal=torch.zeros((NUM,1)+T,dtype=torch.float32); mc.conv=[torch.zeros((NUM,1)+C,dtype=torch.bfloat16)]
dp=O(); dp.num_mamba_layers=NUM; dp.mamba_cache=mc; dp.size=2; dp.device="cpu"
log("constructing mamba pool...")
mp=MambaPoolHost(dp,1.0,0,pin_memory=False,device="cpu",layout="page_first")
log("mamba pool ok")
t0=time.time(); p=mp.get_data_page(1); log(f"mamba get_data_page once {time.time()-t0:.3f}s bytes={p.numel()}")
def bench(n):
    xs=[]
    for _ in range(n):
        t=time.perf_counter_ns(); mp.get_data_page(1); xs.append(time.perf_counter_ns()-t)
    xs.sort(); log(f"mamba x{n}: min={xs[0]/1e6:.2f} med={xs[len(xs)//2]/1e6:.2f} max={xs[-1]/1e6:.2f} ms")
bench(5)
dp2=O(); dp2.layer_num=8; dp2.head_num=4; dp2.head_dim=256; dp2.store_dtype=torch.float8_e4m3fn
dp2.size=1025; dp2.start_layer=0; dp2.end_layer=8; dp2.device="cpu"
log("constructing kv pool...")
kp=MHATokenToKVPoolHost(dp2,1.0,0,page_size=1,layout="page_first",pin_memory=False,device="cpu")
log("kv pool ok")
def benchkv(n):
    xs=[]; vs=[]
    for _ in range(n):
        t=time.perf_counter_ns(); vals=[kp.get_data_page(i,flat=True) for i in range(1024)]; xs.append(time.perf_counter_ns()-t)
        t=time.perf_counter_ns(); _=[_page_byte_view(v) for v in vals]; vs.append(time.perf_counter_ns()-t)
    xs.sort(); vs.sort(); log(f"kv x{n}: getdata min={xs[0]/1e6:.2f} med={xs[len(xs)//2]/1e6:.2f} max={xs[-1]/1e6:.2f}; views med={vs[len(vs)//2]/1e6:.3f} max={vs[-1]/1e6:.3f} ms")
benchkv(3)
payload=bytes(bytearray((i*37+11)&0xFF for i in range(122920)))
t0=time.time(); c=em.crc32c(payload); log(f"crc once {time.time()-t0:.4f}s crc={c:x}")
t0=time.time()
for _ in range(3): em.crc32c(payload)
log(f"crc x3 {time.time()-t0:.4f}s")
log("PHASE PROBE DONE")
