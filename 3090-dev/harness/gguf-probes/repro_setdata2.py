import torch, torch.nn as nn
with torch.device("meta"):
    p = nn.Parameter(torch.empty(4, dtype=torch.uint8), requires_grad=False)
print("meta:", p.device, p.dtype, "uninit:", isinstance(p, torch.nn.parameter.UninitializedParameter))
new = torch.zeros((4,), dtype=torch.uint8, device="cpu")
# approach A: swap_tensors
try:
    torch.utils.swap_tensors(p, nn.Parameter(new, requires_grad=False))
    print("swap_tensors OK ->", p.device, p.dtype, p.data_ptr())
except Exception as e:
    print("swap_tensors FAIL", type(e).__name__, e)

# approach B: setattr on module
m = nn.Module()
with torch.device("meta"):
    m.weight = nn.Parameter(torch.empty(4, dtype=torch.uint8), requires_grad=False)
setattr(m, "weight", nn.Parameter(torch.zeros((4,), dtype=torch.uint8, device="cpu"), requires_grad=False))
print("setattr OK ->", m.weight.device, m.weight.dtype)
