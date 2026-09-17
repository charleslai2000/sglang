import sys
sys.path.insert(0,"/opt/sglang/local-prod-v1.1-candidate/src/python")
import torch
sys.path.insert(0,"/tmp/opencode/qwen35-gguf-20260916")
from sglang.srt.layers.linear import MergedColumnParallelLinear
from sglang.srt.layers.quantization.gguf import GGUFConfig, GGUFLinearMethod
from qwen35_gguf_validate import _init_cpu_dist
_init_cpu_dist()

with torch.device("cpu"):
    layer = MergedColumnParallelLinear(input_size=8, output_sizes=[4,4], bias=False,
                                       quant_config=GGUFConfig(), prefix="t")
print("qweight type:", type(layer.qweight).__name__, "is_gguf_weight", getattr(layer.qweight,"is_gguf_weight",None))
qm = layer.quant_method
print("quant_method", type(qm).__name__, "params_dtype", getattr(qm, "params_dtype", None))
# simulate _load_gguf_dense_shard for two F32 shards
layer.qweight.data_container.append(torch.zeros(4, 8, dtype=torch.float32))
layer.qweight.data_container.append(torch.zeros(4, 8, dtype=torch.float32))
layer.qweight.shard_id_map = {0:0, 1:1}
layer.qweight.shard_id = [0,1]
layer.qweight_type.shard_weight_type = {0:0, 1:0}  # 0 == F32
qm._create_padded_weight_param(layer)
print("after pad: qweight dtype", layer.qweight.dtype, "shape", tuple(layer.qweight.shape))
x = torch.zeros(2, 8, dtype=torch.bfloat16)
try:
    y = x @ layer.qweight.T
    print("forward matmul OK", y.dtype)
except Exception as e:
    print("forward matmul FAIL:", type(e).__name__, str(e)[:140])
