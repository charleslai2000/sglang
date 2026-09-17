import torch, torch.nn as nn
with torch.device("meta"):
    p = nn.Parameter(torch.empty(3, 4))
setattr(p, "weight_loader", lambda *a, **k: "orig")
setattr(p, "is_gguf_weight", True)
setattr(p, "data_container", [])
torch.utils.swap_tensors(p, nn.Parameter(torch.zeros(3, 4)))
print("device", p.device, "attrs", getattr(p, "weight_loader"), getattr(p,"is_gguf_weight"), getattr(p,"data_container"))
print("copy ok:", end=" ")
p.data.copy_(torch.ones(3,4)); print(float(p.sum()))
