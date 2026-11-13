#!/usr/bin/env python3
"""Compare matched E5M2/BF16 per-layer outputs for all captured boundary lengths."""
import json,torch,sys
from pathlib import Path
root=Path(sys.argv[1]); out=[]
for n in (510,511,512,513,514):
 d=root/f'n{n}'; c=json.loads((d/'comparison.json').read_text()); ids=json.loads((d/'e5m2-request.json').read_text())['prompt']; layers=[]
 for i in range(42):
  xs=[]
  for mode in ('bf16','e5m2'):
   f=root/mode/f"forward.{c[mode+'_forward_id']}.layer_output.{i}"
   if not f.exists(): raise SystemExit(f'missing {f}')
   r=torch.load(f,weights_only=True)
   if r['input_ids'].tolist()!=ids or r['layer']!=i or r['forward_mode']!='EXTEND': raise SystemExit(f'identity/boundary mismatch {f}')
   xs.append(r['output'].float())
  delta=xs[1][-1]-xs[0][-1]; layers.append({'layer':i,'max_abs':float(delta.abs().max()),'mean_abs':float(delta.abs().mean()),'rmse':float(delta.square().mean().sqrt()),'rel_l2':float(delta.norm()/xs[0][-1].norm())})
 out.append({'tokens':n,'top_errors':sorted(layers,key=lambda x:x['rel_l2'],reverse=True)[:8],'layers':layers})
(root/'layer-error-analysis.json').write_text(json.dumps(out,indent=2)+'\n')
for row in out: print(row['tokens'],[(x['layer'],round(x['rel_l2'],5),round(x['max_abs'],4)) for x in row['top_errors']])
