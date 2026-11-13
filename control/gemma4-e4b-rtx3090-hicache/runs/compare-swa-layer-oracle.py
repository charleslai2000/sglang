#!/usr/bin/env python3
"""Compare service residual boundaries to exact-position HF hidden states."""
import torch,json,sys
from pathlib import Path
root=Path(sys.argv[1]);out=[]
for n in (510,511,512,513,514):
 hf=torch.load(root/f'oracle-layers-n{n}.pt',weights_only=True);ids=hf['input_ids'];c=json.loads((root/f'n{n}/comparison.json').read_text());layers=[]
 for i in range(42):
  row={'layer':i}
  for mode in ('bf16','e5m2'):
   f=torch.load(root/mode/f"forward.{c[mode+'_forward_id']}.layer_output.{i}",weights_only=True)
   if f['input_ids'].tolist()!=ids or f['positions'].tolist()!=hf['positions'].tolist():raise SystemExit(f'identity mismatch {n=} {i=} {mode}')
   if i==41:
    row[mode]={'comparison_note':'layer41 SGLang tap is pre-final-norm; HF last hidden state is post-final-norm'};continue
   x=f['output'].float()[-1];h=hf['hidden_states'][i+1][0,-1].float();d=x-h
   row[mode]={'max_abs':float(d.abs().max()),'mean_abs':float(d.abs().mean()),'rmse':float(d.square().mean().sqrt()),'rel_l2':float(d.norm()/h.norm())}
  layers.append(row)
 out.append({'tokens':n,'layers':layers,'largest_bf16_rel':sorted([x for x in layers if 'rel_l2' in x.get('bf16',{})],key=lambda x:x['bf16']['rel_l2'],reverse=True)[:8],'largest_e5m2_rel':sorted([x for x in layers if 'rel_l2' in x.get('e5m2',{})],key=lambda x:x['e5m2']['rel_l2'],reverse=True)[:8]})
(root/'layer-oracle-analysis.json').write_text(json.dumps(out,indent=2)+'\n')
for r in out:print('N',r['tokens'],'BF16',[(x['layer'],round(x['bf16']['rel_l2'],4)) for x in r['largest_bf16_rel'][:5]],'E5M2',[(x['layer'],round(x['e5m2']['rel_l2'],4)) for x in r['largest_e5m2_rel'][:5]])
