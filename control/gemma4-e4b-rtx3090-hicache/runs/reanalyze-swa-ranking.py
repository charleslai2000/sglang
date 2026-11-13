#!/usr/bin/env python3
"""Reanalyze preserved same-run SWA boundary requests/logits: top-2 margins and rank flips."""
import json, sys, torch
from pathlib import Path
root=Path(sys.argv[1]); result=[]
for n in (510,511,512,513,514):
    d=root/f'n{n}'; c=json.loads((d/'comparison.json').read_text())
    mode_data={}
    for mode in ('e5m2','bf16'):
        matches=list(root.glob(f"{mode}/forward.{c[mode+'_forward_id']}.logits"))
        if len(matches)!=1: raise SystemExit(f"missing unique logit artifact {mode} n={n} forward={c[mode+'_forward_id']}")
        payload=torch.load(matches[0],map_location='cpu',weights_only=True)
        logits=payload['output'].float()[-1].flatten()
        ids=torch.topk(logits,10).indices.tolist()
        mode_data[mode]={'logits':logits,'top10':ids,'top2':[(int(i),float(logits[i])) for i in ids[:2]],'greedy':int(logits.argmax())}
    union=set(mode_data['e5m2']['top10']+mode_data['bf16']['top10'])
    candidates=[]
    for i in union:
        a=float(mode_data['e5m2']['logits'][i]); b=float(mode_data['bf16']['logits'][i])
        candidates.append({'id':i,'e5m2_logit':a,'bf16_logit':b,'delta':a-b,'e5m2_rank':int((mode_data['e5m2']['logits']>a).sum())+1,'bf16_rank':int((mode_data['bf16']['logits']>b).sum())+1})
    row={'tokens':n,'e5m2':{k:v for k,v in mode_data['e5m2'].items() if k!='logits'},'bf16':{k:v for k,v in mode_data['bf16'].items() if k!='logits'},'shared_top10':sorted(set(mode_data['e5m2']['top10'])&set(mode_data['bf16']['top10'])),'candidates':candidates}
    result.append(row)
(root/'ranking-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
