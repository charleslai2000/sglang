import os,sys,time,statistics,json
os.environ.setdefault("CUDA_VISIBLE_DEVICES","")
import torch
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.storage.extent.extent_file_backend import _page_byte_view
class O: pass
mc=O(); mc.temporal=torch.zeros((24,1,32,128,128),dtype=torch.float32); mc.conv=[torch.zeros((24,1,8192,3),dtype=torch.bfloat16)]
dp=O(); dp.num_mamba_layers=24; dp.mamba_cache=mc; dp.size=2; dp.device="cpu"
mp=MambaPoolHost(dp,1.0,0,pin_memory=False,device="cpu",layout="page_first")
dp2=O(); dp2.layer_num=8; dp2.head_num=4; dp2.head_dim=256; dp2.store_dtype=torch.float8_e4m3fn
dp2.size=1025; dp2.start_layer=0; dp2.end_layer=8; dp2.device="cpu"
kp=MHATokenToKVPoolHost(dp2,1.0,0,page_size=1,layout="page_first",pin_memory=False,device="cpu")
def med(fn,n=50,w=3):
    for _ in range(w): fn()
    xs=[]
    for _ in range(n):
        t=time.perf_counter_ns(); fn(); xs.append(time.perf_counter_ns()-t)
    xs.sort(); return {"n":n,"min_ms":xs[0]/1e6,"median_ms":statistics.median(xs)/1e6,"max_ms":xs[-1]/1e6,"raw_ms":[x/1e6 for x in xs]}
mpage=mp.get_data_page(1)
kpage=kp.get_data_page(3,flat=True)
kvvals=[kp.get_data_page(i,flat=True) for i in range(1024)]
out={
 "mamba_page_byte_view":med(lambda:_page_byte_view(mpage)),
 "kv_single_page_byte_view":med(lambda:_page_byte_view(kpage)),
 "kv_batch_1024_page_byte_view":med(lambda:[_page_byte_view(v) for v in kvvals],30),
 "mamba_op_total_getdata+view":med(lambda:_page_byte_view(mp.get_data_page(1)),30),
 "kv_op_total_1024_getdata+view":med(lambda:[_page_byte_view(v) for v in [kp.get_data_page(i,flat=True) for i in range(1024)]],20),
}
print(json.dumps(out,indent=2))
