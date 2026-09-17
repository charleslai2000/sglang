"""Sweep every non-quantized GGUF tensor role for a converter-time transform.
Compare M3 (27B GGUF, raw) vs M2 (9B HF gptq) / M1 (9B HF w4a16) for the same role.
A constant offset/scale/negation shows up as a distributional shift."""
import numpy as np, gguf, glob, json
from safetensors import safe_open

GG='/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf'
r=gguf.GGUFReader(GG)
QUANT={int(gguf.GGMLQuantizationType.F32),int(gguf.GGMLQuantizationType.F16),int(gguf.GGMLQuantizationType.BF16)}
print("=== M3 non-quantized (F32/F16/BF16) tensors ===")
rows=[]
for t in r.tensors:
    if int(t.tensor_type) in QUANT:
        a=np.asarray(t.data).ravel()
        rows.append((t.name, str(t.tensor_type).split('.')[-1], a.size, float(a.min()), float(a.mean()), float(a.max())))
for n,dt,sz,mi,me,ma in rows:
    print(f"  {n:55s} {dt:5s} n={sz:8d} min={mi:+.4f} mean={me:+.4f} max={ma:+.4f}")
print(f"total non-quantized: {len(rows)}")

# HF 9B reference roles
def hf_roles(d):
    idx=json.load(open(d+'/model.safetensors.index.json'))['weight_map']
    files={}
    for n,f in idx.items(): files.setdefault(f,[]).append(n)
    out={}
    for f,names in files.items():
        with safe_open(d+'/'+f, framework='pt') as fh:
            for n in names:
                try:
                    w=fh.get_tensor(n).float().numpy().ravel()
                except Exception: continue
                out.setdefault(n,[]).append(w)
    return {k:np.concatenate(v) for k,v in out.items()}

for lab,d in [('M1','/data/models/qwen35-9b-w4a16'),('M2','/data/models/omnicoder-9b-gptq-int4')]:
    print(f"\n=== {lab} HF-format 1-D / norm-like roles (sample) ===")
    roles=hf_roles(d)
    for k in sorted(roles):
        if any(s in k for s in ['in_proj_a','in_proj_b','dt_bias','A_log','norm.weight']) and 'layers.' in k:
            v=roles[k]
            print(f"  ...{k.split('layers.')[0]}layers.N.{k.split('layers.')[1].split('.',1)[1]:45s} n={v.size:7d} min={v.min():+.4f} mean={v.mean():+.4f} max={v.max():+.4f}")
            break
    # aggregate per role across layers
    agg={}
    import re
    for k,v in roles.items():
        m=re.search(r'layers\.\d+\.(.*)', k)
        role=m.group(1) if m else k
        role=re.sub(r'^\d+\.','',role)
        agg.setdefault(role,[]).append(v)
    for role in ['linear_attn.in_proj_a.weight','linear_attn.in_proj_b.weight','linear_attn.dt_bias','linear_attn.norm.weight','input_layernorm.weight','self_attn.q_norm.weight','self_attn.k_norm.weight']:
        if role in agg:
            v=np.concatenate(agg[role])
            print(f"  {role:40s} n={v.size:8d} min={v.min():+.4f} mean={v.mean():+.4f} max={v.max():+.4f}")
