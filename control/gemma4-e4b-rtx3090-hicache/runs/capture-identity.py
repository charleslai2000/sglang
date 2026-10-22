#!/usr/bin/env python3
"""Attach immutable model identity to one raw Forward capture without overwriting it."""
import argparse,hashlib,json,os,sys
from pathlib import Path
import torch
ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--forward-id',required=True);ap.add_argument('--model',required=True);ap.add_argument('--model-revision',required=True);a=ap.parse_args();base=Path(a.base); sha=hashlib.sha256(Path(a.model).read_bytes()).hexdigest();identity={'model_revision':a.model_revision,'model_sha256':sha};manifest=base.parent/f'{base.name}.{a.forward_id}.manifest'
if not manifest.is_file():raise SystemExit('missing model-forward manifest')
m=json.loads(manifest.read_text());
if m.get('status')!='COMPLETE' or m.get('forward_id')!=a.forward_id:raise SystemExit('manifest identity/status mismatch')
expected={f'{base.name}.{a.forward_id}.layer_output.{i}' for i in range(42)}|{f'{base.name}.{a.forward_id}.prenorm',f'{base.name}.{a.forward_id}.finalnorm',f'{base.name}.{a.forward_id}.logits'}
if {p.name for p in base.parent.glob(f'{base.name}.{a.forward_id}.*') if p.is_file() and '.tmp.' not in p.name and not p.name.endswith('.tmp')} != expected|{manifest.name}:raise SystemExit('raw artifact set incomplete or has unexpected files')
raw=[]
for name in sorted(expected):
 p=base.parent/name;r=torch.load(p,map_location='cpu',weights_only=True)
 if r.get('forward_id')!=a.forward_id or r.get('rid')!=m.get('rid') or r.get('forward_mode')!=m.get('forward_mode') or r.get('input_ids').tolist()!=m.get('input_ids') or r.get('positions').tolist()!=m.get('positions'):raise SystemExit(f'raw artifact identity mismatch: {name}')
 if r.get('model_identity') is not None:raise SystemExit(f'already has model identity: {name}')
 raw.append((p,r))
for p,r in raw:
 r['model_identity']=identity;t=p.with_name(p.name+f'.identity.tmp.{os.getpid()}');torch.save(r,t)
 if t.exists():os.replace(t,p)
 sidecar=p.with_name(p.name+'.sha256')
 if sidecar.exists():raise SystemExit(f'refuse sidecar overwrite: {sidecar}')
 with sidecar.open('x') as f:f.write(hashlib.sha256(p.read_bytes()).hexdigest()+'\\n');f.flush();os.fsync(f.fileno())
m['model_identity']=identity
mt=manifest.with_name(manifest.name+f'.identity.tmp.{os.getpid()}')
with mt.open('x') as f:json.dump(m,f,sort_keys=True);f.flush();os.fsync(f.fileno())
os.replace(mt,manifest)
for name in sorted(expected):
 p=base.parent/name;sha256=hashlib.sha256(p.read_bytes()).hexdigest();side=base.parent/(name+'.sha256');print(name,sha256)
print(json.dumps({'forward_id':a.forward_id,'model_identity':identity,'artifact_count':len(expected),'raw_status':'COMPLETE'}))
