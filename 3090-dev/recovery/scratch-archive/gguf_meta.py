import gguf
for lab,p in [('M3','/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf'),
              ('M4','/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf')]:
    r=gguf.GGUFReader(p)
    print('=====',lab,'fields:',r.fields.__len__())
    for k,f in r.fields.items():
        if k.startswith('GGUF') or '.tensor' in k: continue
        try:
            v=f.contents()
            s=str(v)
        except Exception:
            v=f.parts[f.data[0]] if f.data else None; s=str(v)
        if len(s)>160: s=s[:160]+'...'
        print(f'  {k} = {s}')
