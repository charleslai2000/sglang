#!/usr/bin/env python3
"""Compare captured boundary service logits against exact-input HF oracle and ranks."""
import json,torch,sys
from pathlib import Path
root=Path(sys.argv[1]);out=[]
for n in (510,511,512,513,514):
 d=root/f'n{n}';c=json.loads((d/'comparison.json').read_text());o=torch.load(root/f'oracle-n{n}.pt',weights_only=True);row={'tokens':n,'oracle_greedy':o['greedy'],'oracle_top10':o['top10']}
 for mode in ('bf16','e5m2'):
  s=torch.load(root/mode/f"forward.{c[mode+'_forward_id']}.logits",weights_only=True)['output'].float()[-1].flatten();ref=o['logits'];delta=s-ref;ids=(204064,238247,90296) if n==513 else set(torch.topk(s,5).indices.tolist())|set(torch.topk(ref,5).indices.tolist());row[mode]={'greedy':int(s.argmax()),'top2':[(int(i),float(s[i])) for i in torch.topk(s,2).indices],'oracle_errors':{'max_abs':float(delta.abs().max()),'mean_abs':float(delta.abs().mean()),'rmse':float(delta.square().mean().sqrt()),'rel_l2':float(delta.norm()/ref.norm())},'candidates':{str(int(i)):{'service':float(s[i]),'oracle':float(ref[i]),'rank_service':int((s>s[i]).sum())+1,'rank_oracle':int((ref>ref[i]).sum())+1} for i in ids}}
 out.append(row)
(root/'oracle-comparison.json').write_text(json.dumps(out,indent=2)+'\n')
for r in out:
 def margin(m):
  v=torch.tensor([x[1] for x in r[m]['top2']]);return float(v[0]-v[1])
 print(r['tokens'],'oracle',r['oracle_greedy'],*((m,r[m]['greedy'],round(r[m]['oracle_errors']['rel_l2'],5),'top2_margin',margin(m)) for m in ('bf16','e5m2')))
