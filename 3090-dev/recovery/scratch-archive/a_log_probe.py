import json, sys, numpy as np
import gguf
from safetensors import safe_open

idx = json.load(open('/data/models/qwen35-9b-w4a16/model.safetensors.index.json'))['weight_map']
# collect per-layer A_log stats from the HF 9B reference
hf_files = {}
hf_vals = []
for n, f in idx.items():
    if n.endswith('linear_attn.A_log'):
        hf_files.setdefault(f, []).append(n)
for f, names in hf_files.items():
    with safe_open('/data/models/qwen35-9b-w4a16/'+f, framework='pt') as fh:
        for n in sorted(names, key=lambda s:int(s.split('.')[3])):
            t = fh.get_tensor(n).float().numpy()
            hf_vals.append(t)
hf = np.concatenate(hf_vals).astype(np.float64)
print('=== HF 9B (M1) linear_attn.A_log reference ===')
print('n=%d  min=%.4f max=%.4f mean=%.4f std=%.4f' % (hf.size, hf.min(), hf.max(), hf.mean(), hf.std()))
print('quantiles 0/1/25/50/75/99/100%%: %s' % np.round(np.percentile(hf,[0,1,25,50,75,99,100]),4))
print('all<0 fraction: %.4f' % (hf<0).mean())
print('neg-exp(A_log) range: min=%.4f max=%.4f' % ((-np.exp(hf)).min(), (-np.exp(hf)).max()))
print()

for label,path in [('M3','/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf'),
                   ('M4','/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf')]:
    r = gguf.GGUFReader(path)
    vals = []
    for t in r.tensors:
        if t.name.endswith('.ssm_a'):
            vals.append(np.asarray(t.data, dtype=np.float64).ravel())
    raw = np.concatenate(vals)
    print(f'=== {label} GGUF blk.*.ssm_a (raw) ===')
    print('n=%d  min=%.4f max=%.4f mean=%.4f std=%.4f  all<0=%s' % (raw.size, raw.min(), raw.max(), raw.mean(), raw.std(), bool((raw<0).all())))
    print('quantiles 0/1/25/50/75/99/100%%: %s' % np.round(np.percentile(raw,[0,1,25,50,75,99,100]),4))
    lg = np.log(-raw)
    print('  log(-raw): min=%.4f max=%.4f mean=%.4f std=%.4f' % (lg.min(), lg.max(), lg.mean(), lg.std()))
    print('  quantiles: %s' % np.round(np.percentile(lg,[0,1,25,50,75,99,100]),4))
    print('  vs HF A_log: mean diff=%.4f' % (lg.mean()-hf.mean()))
    print('  if NOT transformed (raw used as A_log): -exp(raw) min=%.4f max=%.4f' % ((-np.exp(raw)).min(), (-np.exp(raw)).max()))
    print()
