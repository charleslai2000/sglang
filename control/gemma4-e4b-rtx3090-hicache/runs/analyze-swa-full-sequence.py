#!/usr/bin/env python3
"""Fail-closed exact-ID/position all-token layer and logits analysis for N=510..514."""
import hashlib,json,sys,torch
from pathlib import Path
root=Path(sys.argv[1]); out=[]
for n in (510,511,512,513,514):
 d=root/f'n{n}'; comp=json.loads((d/'comparison.json').read_text()); ids=json.loads((d/'bf16-request.json').read_text())['prompt']; oracle=torch.load(root/f'oracle-layers-n{n}.pt',map_location='cpu',weights_only=True)
 assert oracle['input_ids']==ids and len(ids)==n
 for m in ('bf16','e5m2'):
  manifest=json.loads((root/m/f"forward.{comp[m+'_forward_id']}.manifest").read_text())
  assert manifest['input_ids']==ids and manifest['positions']==list(range(1,n+1)),(n,m,'manifest identity')
  assert manifest['forward_id']==comp[m+'_forward_id'] and manifest['rid']==[comp[m+'_rid']]
 row={'n':n,'input_ids_sha256':hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest(),'position_start_end':[1,n],'hf_top2':[(int(i),float(oracle['logits'][i])) for i in torch.topk(oracle['logits'],2).indices],'layers':[],'logits':{}}
 for mode in ('bf16','e5m2'):
  logitsrec=torch.load(root/mode/f"forward.{comp[mode+'_forward_id']}.logits",map_location='cpu',weights_only=True)
  logits=logitsrec['output'].float()[-1].flatten();ref=oracle['logits'].float();delta=logits-ref;v,ix=torch.topk(logits,2);row['logits'][mode]={'top2':[(int(i),float(logits[i])) for i in ix],'top2_margin':float(v[0]-v[1]),'greedy':int(ix[0]),'oracle_errors':{'max_abs':float(delta.abs().max()),'mean_abs':float(delta.abs().mean()),'rmse':float(delta.square().mean().sqrt()),'rel_l2':float(delta.norm()/ref.norm())}}
  per=[]
  for layer in range(41):
   cap=torch.load(root/mode/f"forward.{comp[mode+'_forward_id']}.layer_output.{layer}",map_location='cpu',weights_only=True)
   assert cap['input_ids'].tolist()==ids and cap['positions'].tolist()==oracle['positions'].tolist() and cap['layer']==layer and cap['rid']==[comp[mode+'_rid']]
   x=cap['output'].float();h=oracle['hidden_states'][layer+1][0].float();assert x.shape==h.shape,(n,mode,layer,x.shape,h.shape)
   diff=x-h;per.append({'layer':layer,'last':{'max_abs':float(diff[-1].abs().max()),'mean_abs':float(diff[-1].abs().mean()),'rmse':float(diff[-1].square().mean().sqrt()),'rel_l2':float(diff[-1].norm()/h[-1].norm())},'all':{'max_abs':float(diff.abs().max()),'mean_abs':float(diff.abs().mean()),'rmse':float(diff.square().mean().sqrt()),'rel_l2':float(diff.norm()/h.norm())}})
  row['layers'].append({'mode':mode,'per_layer':per,'largest_last_rel':sorted(per,key=lambda x:x['last']['rel_l2'],reverse=True)[:8],'largest_all_rel':sorted(per,key=lambda x:x['all']['rel_l2'],reverse=True)[:8]})
 out.append(row)
(root/'full-sequence-layer-analysis.json').write_text(json.dumps(out,indent=2)+'\n')
for r in out:
 print('N',r['n'],'HFtop2',r['hf_top2'])
 for mode in ('bf16','e5m2'):
  d=r['logits'][mode];print(' ',mode,'top2',d['top2'],'margin',d['top2_margin'],'greedy',d['greedy'],'oracle',d['oracle_errors'])
  lay=next(x for x in r['layers'] if x['mode']==mode)
  print('  LAST top',[(x['layer'],round(x['last']['rel_l2'],5)) for x in lay['largest_last_rel'][:5]],'ALL top',[(x['layer'],round(x['all']['rel_l2'],5)) for x in lay['largest_all_rel'][:5]])
