import numpy as np, json
from safetensors import safe_open
P='/data/models/omnicoder-9b-gptq-int4/'
f=sorted(__import__('glob').glob(P+'*.safetensors'))[0]
names=[]
with safe_open(f, framework='pt') as fh:
    names=list(fh.keys())
    def med(suffix):
        vals=[]
        for n in names:
            if n.endswith(suffix) and 'layers.' in n:
                vals.append(fh.get_tensor(n).float().numpy().ravel())
        if not vals: return None,0
        v=np.concatenate(vals)
        return np.percentile(v,50), v.size
    for suf in ['.input_layernorm.weight','.post_attention_layernorm.weight',
                '.self_attn.q_norm.weight','.self_attn.k_norm.weight',
                '.linear_attn.norm.weight','model.norm.weight','.linear_attn.dt_bias']:
        m,n = med(suf)
        print(f'  M2 {suf:36s} median={m if m is None else round(float(m),4)}  n={n}')
