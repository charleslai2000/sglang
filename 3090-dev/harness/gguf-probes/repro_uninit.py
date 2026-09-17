import torch, torch.nn as nn
from torch.nn.parameter import UninitializedParameter

class P(UninitializedParameter):
    cls_to_become = nn.Parameter

with torch.device("meta"):
    p = P(requires_grad=False)
print("uninit meta:", p.device, type(p).__name__)
try:
    p.materialize((4, 8), dtype=torch.uint8)
    print("materialize default OK ->", p.device, p.dtype, p.shape)
except Exception as e:
    print("materialize default FAIL", type(e).__name__, e)

with torch.device("meta"):
    q = P(requires_grad=False)
try:
    q.materialize((4, 8), device="cpu", dtype=torch.uint8)
    print("materialize cpu OK ->", q.device, q.dtype, q.shape)
    q.data.copy_(torch.zeros(4,8,dtype=torch.uint8))
    print("copy OK")
except Exception as e:
    print("materialize cpu FAIL", type(e).__name__, e)

# swap_tensors with uninitialized
with torch.device("meta"):
    r = P(requires_grad=False)
try:
    torch.utils.swap_tensors(r, nn.Parameter(torch.zeros(4,8,dtype=torch.uint8), requires_grad=False))
    print("swap uninit OK ->", r.device, type(r).__name__, r.shape)
except Exception as e:
    print("swap uninit FAIL", type(e).__name__, e)
