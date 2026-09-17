"""Prove the qwen35 GGUF carries a +1.0 offset on the Gemma-style norms.

Method: pooled distribution comparison (HF 9B reference vs the 27B GGUF) and a
shift-fit that measures which constant shift s best matches the two
distributions (mean |quantile difference|). Also per-LAYER-INDEX means (layers
0..31 exist in both) so pooling bias cannot manufacture the result.
"""
import json, numpy as np, gguf
from safetensors import safe_open

HF='/data/models/qwen35-9b-w4a16/'
idx=json.load(open(HF+'model.safetensors.index.json'))['weight_map']
files={}
for n,f in idx.items(): files.setdefault(f,set()).add(n)

def hf_by_layer(suffix, nl=32):
    out={}
    for f,names in files.items():
        want=[n for n in names if n.endswith(suffix)]
        if not want: continue
        with safe_open(HF+f, framework='pt') as fh:
            for n in want:
                li=int(n.split('.layers.')[1].split('.')[0])
                out.setdefault(li,[]).append(fh.get_tensor(n).float().numpy().ravel())
    return {k:np.concatenate(v) for k,v in sorted(out.items())}

ROLES={
 'input_layernorm':'.input_layernorm.weight',
 'post_attention_norm':'.post_attention_layernorm.weight',
 'q_norm':'.self_attn.q_norm.weight',
 'k_norm':'.self_attn.k_norm.weight',
 'ssm_norm':'.linear_attn.norm.weight',
}
GGUF={ 'input_layernorm':'attn_norm.weight','post_attention_norm':'post_attention_norm.weight',
       'q_norm':'attn_q_norm.weight','k_norm':'attn_k_norm.weight','ssm_norm':'ssm_norm.weight'}
OUT={'ssm_norm':'ssm_norm.weight'}
readers={}
for lab,p in [('M3','/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf'),
              ('M4','/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf')]:
    readers[lab]={t.name:t for t in gguf.GGUFReader(p).tensors}
def gguf_by_layer(lab,suffix):
    out={}
    for n,t in readers[lab].items():
        if n.startswith('blk.') and n.endswith('.'+suffix):
            li=int(n.split('.')[1])
            out.setdefault(li,[]).append(np.asarray(t.data,dtype=np.float64).ravel())
    return {k:np.concatenate(v) for k,v in sorted(out.items())}
def gguf_final(lab,suffix):
    for n,t in readers[lab].items():
        if not n.startswith('blk.') and n.endswith(suffix):
            return np.asarray(t.data,dtype=np.float64).ravel()
    return None

P=[0,1,5,25,50,75,95,99,100]
print('=== pooled percentiles; shift-fit s* minimising mean|q_gguf - (q_hf + s)| ===')
for role,suf in ROLES.items():
    hf={k:v for k,v in hf_by_layer(suf).items()}
    hp=np.percentile(np.concatenate(list(hf.values())),P)
    for lab in readers:
        gl=gguf_by_layer(lab,GGUF[role]); gp=np.percentile(np.concatenate(list(gl.values())),P)
        best=None
        for s in np.arange(-0.5,1.75,0.05):
            d=float(np.mean(np.abs(gp-(hp+s))))
            if best is None or d<best[1]: best=(round(float(s),2),d)
        # per-layer-index mean shift (layers 0..31)
        shifts=[]
        for li in range(32):
            if li in hf and li in gl:
                shifts.append(float(gl[li].mean()-hf[li].mean()))
        print(f'{role:20s} {lab}  best_shift={best[0]:+.2f} (resid {best[1]:.4f}) | '
              f'per-layer mean-shift: mean={np.mean(shifts):+.4f} std={np.std(shifts):.4f} '
              f'min={np.min(shifts):+.4f} max={np.max(shifts):+.4f}')
    print(f'{"":20s} HF  pct={np.round(hp,3)}')
    for lab in readers:
        gp=np.percentile(np.concatenate(list(gguf_by_layer(lab,GGUF[role]).values())),P)
        print(f'{"":20s} {lab}  pct={np.round(gp,3)}')

# final norm
say=json.load(open('/data/models/qwen35-9b-w4a16/model.safetensors.index.json'))['weight_map']
hf_final=None
for n,f in say.items():
    if n.endswith('model.norm.weight'):
        with safe_open(HF+f, framework='pt') as fh: hf_final=fh.get_tensor(n).float().numpy().ravel()
hp=np.percentile(hf_final,P)
print('=== output_norm (final norm) ===')
print(f'{"":20s} HF  pct={np.round(hp,3)}')
for lab in readers:
    gp=np.percentile(gguf_final(lab,'output_norm.weight'),P)
    best=min(((round(float(s),2), float(np.mean(np.abs(gp-(hp+s))))) for s in np.arange(-0.5,1.75,0.05)), key=lambda x:x[1])
    print(f'{"":20s} {lab}  pct={np.round(gp,3)}  best_shift={best[0]:+.2f} (resid {best[1]:.4f})')
