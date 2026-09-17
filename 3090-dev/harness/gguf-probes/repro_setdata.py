import torch, torch.nn as nn
with torch.device("meta"):
    p = nn.Parameter(torch.empty(4, dtype=torch.uint8), requires_grad=False)
print("p device", p.device, p.dtype)
try:
    p.data = torch.zeros((4,), dtype=torch.uint8, device="cpu")
    print("assign ok", p.device)
except Exception as e:
    print("assign FAIL", type(e).__name__, e)
    # try to()
    q = p.to("cpu")
    print("to ok", q.device, q.dtype)
