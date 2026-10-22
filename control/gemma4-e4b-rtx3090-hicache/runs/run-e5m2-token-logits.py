#!/usr/bin/env python3
"""Capture E5M2 pre-sampling logits rows for an auditable exact-token comparison."""
import json,os
from pathlib import Path
import torch

def main():
 out=Path(os.environ['GEMMA4_RUN_OUT']);raw=Path('/data/sglang-hicache/gemma4/runs/targeted-bf16-logits-fixed-same-run/oracle-positions-1-8-all-layers.pt');oracle=torch.load(raw,map_location='cpu',weights_only=True);ids=oracle['input_ids'].reshape(-1).tolist();request={'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':1}}
 (out/'request.json').write_text(json.dumps(request)+'\n')
 import urllib.request
 req=urllib.request.Request('http://127.0.0.1:31038/generate',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
 response=json.loads(urllib.request.urlopen(req,timeout=300).read());(out/'response.json').write_text(json.dumps(response,indent=2)+'\n');rid=response['meta_info']['id']; files=sorted(out.glob(f'forward.*.logits'))
 good=[]
 for p in files:
  r=torch.load(p,map_location='cpu',weights_only=True)
  if r.get('rid')==[rid] and r.get('forward_mode')=='EXTEND' and r.get('input_ids').tolist()[-len(ids):]==ids and r.get('positions').tolist()[-len(ids):]==list(range(1,9)):good.append((p,r))
 if len(good)!=1:raise SystemExit(f'expected exactly one E5M2 target logits artifact, got {len(good)}')
 p,r=good[0]; logits=r['output'].float()[-1:];ref=oracle['logits_last_token'].float().reshape(1,-1);d=logits-ref;delta=d.abs();top=lambda x:set(torch.topk(x.flatten(),10).indices.tolist());tol={'max_abs':8.0,'mean_abs':0.5,'top10_equal':True,'greedy_equal':True};m={'status':'E5M2_NUMERICS_MEASURED','rid':rid,'forward_id':r.get('forward_id'),'input_ids':ids,'positions':[1,2,3,4,5,6,7,8],'logits_shape':list(logits.shape),'max_abs':delta.max().item(),'mean_abs':delta.mean().item(),'rmse':d.square().mean().sqrt().item(),'relative_l2':(d.norm()/ref.norm()).item(),'top10_id_set_equal':top(logits)==top(ref),'greedy_service':int(logits.argmax(-1).item()),'greedy_oracle':int(ref.argmax(-1).item()),'bf16_baseline':{'max_abs':0.4347810745,'mean_abs':0.0604655854,'top10_equal':True,'greedy':108},'predeclared_diagnostic_thresholds':tol};m['e5m2_numeric_pass']=bool(m['max_abs']<=tol['max_abs'] and m['mean_abs']<=tol['mean_abs'] and m['top10_id_set_equal'] and m['greedy_service']==m['greedy_oracle']);(out/'numerical-comparison.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
if __name__=='__main__':main()
