import time
import torch

x = torch.randn((1024, 1024), device="cuda")
y = torch.randn_like(x)
for i in range(8):
    torch.cuda.nvtx.range_push(f"SMOKE_STEP_{i}")
    z = x @ y
    torch.cuda.synchronize()
    torch.cuda.nvtx.range_pop()
    time.sleep(0.01)
print(float(z[0, 0]))
