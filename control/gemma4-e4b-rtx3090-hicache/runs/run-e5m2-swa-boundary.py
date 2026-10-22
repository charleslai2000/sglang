#!/usr/bin/env python3
"""Run matched BF16/E5M2 deterministic prefills at SWA 512 boundary lengths."""
import hashlib,json,os,time,urllib.request
from pathlib import Path
import torch
base=Path(os.environ['GEMMA4_RUN_OUT']);ids=[6974,886,2822,13315,1003,506,7217,236761]
urls={'e5m2':'http://127.0.0.1:31039/v1/completions','bf16':'http://127.0.0.1:31040/v1/completions'}
def post(url,payload):
 req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=600).read())
rows=[]
for n in [510,511,512,513,514]:
 g=torch.Generator().manual_seed(20261022+n);prompt=torch.randint(1,262000,(n,),generator=g).tolist();prompt[:8]=ids;per=base/f'n{n}';per.mkdir(exist_ok=True);req={'prompt':prompt,'max_tokens':1,'temperature':0.0};outs={}
 for mode,url in urls.items():
  (per/f'{mode}-request.json').write_text(json.dumps(req)+'\n');resp=post(url,req);(per/f'{mode}-response.json').write_text(json.dumps(resp,indent=2)+'\n');rid=resp.get('meta_info',{}).get('id',resp.get('id'));deadline=time.time()+60;capt=None
  while time.time()<deadline:
   for f in (base/mode).glob(f'forward.*.manifest'):
    m=json.loads(f.read_text())
    if m.get('rid')==[rid] and m.get('input_ids',[])[-n:]==prompt and int(m.get('positions',[])[-1])==n:capt=m;break
   if capt:break
   time.sleep(.2)
  if capt is None:raise RuntimeError(f'missing {mode} target capture at {n}')
  p=base/mode/f"forward.{capt['forward_id']}.logits";r=torch.load(p,weights_only=True);outs[mode]={'logits':r['output'].float()[-1:],'rid':rid,'forward_id':capt['forward_id'],'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 d=outs['e5m2']['logits']-outs['bf16']['logits'];x={'tokens':n,'e5m2_rid':outs['e5m2']['rid'],'bf16_rid':outs['bf16']['rid'],'e5m2_forward_id':outs['e5m2']['forward_id'],'bf16_forward_id':outs['bf16']['forward_id'],'e5m2_logits_sha256':outs['e5m2']['artifact_sha256'],'bf16_logits_sha256':outs['bf16']['artifact_sha256'],'max_abs':d.abs().max().item(),'mean_abs':d.abs().mean().item(),'rmse':d.square().mean().sqrt().item(),'relative_l2':(d.norm()/outs['bf16']['logits'].norm()).item(),'greedy_e5m2':int(outs['e5m2']['logits'].argmax(-1)),'greedy_bf16':int(outs['bf16']['logits'].argmax(-1))};x['greedy_equal']=x['greedy_e5m2']==x['greedy_bf16'];rows.append(x);(per/'comparison.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x))
(base/'summary.json').write_text(json.dumps({'status':'MEASURED','cases':rows},indent=2)+'\n')
