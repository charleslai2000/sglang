#!/usr/bin/env python3
"""Run deterministic 510/511/512/513/514-token E5M2 checks against BF16 service."""
import json,os,time,urllib.request,hashlib
from pathlib import Path
import torch
from transformers import AutoTokenizer
base=Path(os.environ['GEMMA4_RUN_OUT']);base.mkdir(parents=True,exist_ok=False);ids=torch.load('/data/sglang-hicache/gemma4/runs/targeted-bf16-logits-fixed-same-run/oracle-positions-1-8-all-layers.pt',weights_only=True)['input_ids'].reshape(-1).tolist();seed=hashlib.sha256(b'gemma4-swa-e5m2-boundary-v1').digest();vocab=262000;stream=[]
while len(stream)<520:
 for b in seed:stream.append(1+(b*997+len(stream)*7919)%vocab)
stream=stream[:520]
urls={'e5m2':'http://127.0.0.1:31039/generate','bf16':'http://127.0.0.1:31040/generate'}
def post(url,payload):
 req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'});return json.loads(urllib.request.urlopen(req,timeout=600).read())
rows=[]
for n in [510,511,512,513,514]:
 prompt=stream[:n]; per=base/f'n{n}'; per.mkdir(); req={'input_ids':prompt,'sampling_params':{'temperature':0,'max_new_tokens':1}}
 outputs={}
 for mode,url in urls.items():
  (per/f'{mode}-request.json').write_text(json.dumps(req)+'\n');resp=post(url,req);(per/f'{mode}-response.json').write_text(json.dumps(resp,indent=2)+'\n');rid=resp['meta_info']['id'];deadline=time.time()+60;capture=None
  while time.time()<deadline:
   for f in sorted(per.glob(f'{mode}-forward.*.manifest')):
    m=json.loads(f.read_text())
    if m.get('rid')==[rid] and len(m.get('input_ids',[]))>=n and m['input_ids'][-n:]==prompt: capture=m;break
   if capture:break
   time.sleep(.2)
  if capture is None:raise RuntimeError(f'missing {mode} logits for n={n}, RID={rid}')
  f=per/f"{mode}-forward.{capture['forward_id']}.logits";r=torch.load(f,map_location='cpu',weights_only=True);log=r['output'].float()[-1:];outputs[mode]={'logits':log,'rid':rid,'forward_id':capture['forward_id'],'artifact':str(f)}
 d=outputs['e5m2']['logits']-outputs['bf16']['logits'];row={'tokens':n,'e5m2_rid':outputs['e5m2']['rid'],'bf16_rid':outputs['bf16']['rid'],'e5m2_forward_id':outputs['e5m2']['forward_id'],'bf16_forward_id':outputs['bf16']['forward_id'],'max_abs':d.abs().max().item(),'mean_abs':d.abs().mean().item(),'rmse':d.square().mean().sqrt().item(),'relative_l2':(d.norm()/outputs['bf16']['logits'].norm()).item(),'greedy_equal':int(outputs['e5m2']['logits'].argmax(-1))==int(outputs['bf16']['logits'].argmax(-1)),'greedy_e5m2':int(outputs['e5m2']['logits'].argmax(-1)),'greedy_bf16':int(outputs['bf16']['logits'].argmax(-1))};rows.append(row);(per/'comparison.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row))
(base/'summary.json').write_text(json.dumps({'status':'MEASURED','cases':rows},indent=2)+'\n')
