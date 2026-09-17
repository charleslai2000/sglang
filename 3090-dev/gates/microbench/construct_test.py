import os, sys, types
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
import torch
print("torch cuda avail:", torch.cuda.is_available())
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost

# ---- mamba stub device pool (real geometry, CPU stand-in) ----
NUM_MAMBA_LAYERS = 24
TEMPORAL_SHAPE = (32, 128, 128)   # (HV, V, K)
CONV_SHAPE = (8192, 3)            # (conv_dim, K-1)
class MC:
    pass
mc = MC()
# device-pool-like tensors only need correct trailing shapes + data_ptr
mc.temporal = torch.zeros((NUM_MAMBA_LAYERS, 1) + TEMPORAL_SHAPE, dtype=torch.float32)
mc.conv = [torch.zeros((NUM_MAMBA_LAYERS, 1) + CONV_SHAPE, dtype=torch.bfloat16)]
class DP:
    pass
dp = DP()
dp.num_mamba_layers = NUM_MAMBA_LAYERS
dp.mamba_cache = mc
dp.size = 4
dp.device = "cpu"
mp = MambaPoolHost(dp, host_to_device_ratio=1.0, host_size=0, pin_memory=False,
                   device="cpu", layout="page_first")
print("mamba temporal_buffer", tuple(mp.temporal_buffer.shape), mp.temporal_buffer.dtype)
print("mamba conv_buffer[0]", tuple(mp.conv_buffer[0].shape), mp.conv_buffer[0].dtype)
p = mp.get_data_page(0)
print("mamba page bytes", p.numel(), p.dtype)

# ---- kv stub device pool ----
KV_LAYER_NUM = 8
KV_HEAD_NUM = 4
KV_HEAD_DIM = 256
dp2 = DP()
dp2.layer_num = KV_LAYER_NUM
dp2.head_num = KV_HEAD_NUM
dp2.head_dim = KV_HEAD_DIM
dp2.store_dtype = torch.float8_e4m3fn
dp2.size = 4096
dp2.start_layer = 0
dp2.end_layer = KV_LAYER_NUM
dp2.device = "cpu"
hp = MHATokenToKVPoolHost(dp2, host_to_device_ratio=1.0, host_size=0, page_size=1,
                          layout="page_first", pin_memory=False, device="cpu")
print("kv_buffer", tuple(hp.kv_buffer.shape), hp.kv_buffer.dtype)
kv = hp.get_data_page(0, flat=True)
print("kv page bytes", kv.numel(), kv.dtype)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import _page_byte_view
mv = _page_byte_view(kv)
print("kv page view len", len(mv))
print("OK")
