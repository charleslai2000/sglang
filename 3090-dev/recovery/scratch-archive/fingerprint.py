"""Distributional fingerprint: the semantics-known-good HF 9B (M1) vs the two
27B GGUF files, for every tensor role that is stored unquantised on the HF side."""
import json, numpy as np, gguf
from safetensors import safe_open

HF='/data/models/qwen35-9b-w4a16/'
idx=json.load(open(HF+'model.safetensors.index.json'))['weight_map']
files={}
for n,f in idx.items(): files.setdefault(f,set()).add(n)

def hf_role(suffixes):
    out=[]
    for f, names in files.items():
        want=[n for n in names if any(n.endswith(s) for s in suffixes)]
        if not want: continue
        with safe_open(HF+f, framework='pt') as fh:
            for n in want:
                try: out.append(fh.get_tensor(n).float().numpy().ravel())
                except Exception: pass
    return np.concatenate(out) if out else None

ROLES = {
 'input_layernorm':      ['.input_layernorm.weight'],
 'post_attention_norm':  ['.post_attention_layernorm.weight'],
 'q_norm':               ['.self_attn.q_norm.weight'],
 'k_norm':               ['.self_attn.k_norm.weight'],
 'ssm_norm':             ['.linear_attn.norm.weight'],
 'dt_bias':              ['.linear_attn.dt_bias'],
 'conv1d':               ['.linear_attn.conv1d.weight'],
 'output_norm':          ['model.norm.weight'],
}
GGUF_ROLE = {
 'input_layernorm': 'attn_norm.weight',
 'post_attention_norm': 'post_attention_norm.weight',
 'q_norm': 'attn_q_norm.weight',
 'k_norm': 'attn_k_norm.weight',
 'ssm_norm': 'ssm_norm.weight',
 'dt_bias': 'ssm_dt.bias',
 'conv1d': 'ssm_conv1d.weight',
 'output_norm': 'output_norm.weight',
}
readers={}
for lab,p in [('M3','/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf'),
              ('M4','/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf')]:
    readers[lab]={t.name:t for t in gguf.GGUFReader(p).tensors}

print(f"{'role':22s} {'src':4s} {'n':>8s} {'mean':>10s} {'std':>10s} {'min':>10s} {'max':>10s} {'|mean|':>9s}")
for role, suffixes in ROLES.items():
    h = hf_role(suffixes)
    if h is not None:
        print(f"{role:22s} {'HF9B':4s} {h.size:8d} {h.mean():10.4f} {h.std():10.4f} {h.min():10.4f} {h.max():10.4f} {abs(h.mean()):9.4f}")
    for lab in readers:
        vals=[]
        for name,t in readers[lab].items():
            if name.startswith('blk.') and name.endswith('.'+GGUF_ROLE[role]):
                vals.append(np.asarray(t.data,dtype=np.float64).ravel())
            elif 'blk.' not in name and name.endswith(GGUF_ROLE[role]):
                vals.append(np.asarray(t.data,dtype=np.float64).ravel())
        if not vals: continue
        g=np.concatenate(vals)
        print(f"{role:22s} {lab:4s} {g.size:8d} {g.mean():10.4f} {g.std():10.4f} {g.min():10.4f} {g.max():10.4f} {abs(g.mean()):9.4f}")
    print()
