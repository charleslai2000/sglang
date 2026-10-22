#!/usr/bin/env python3
"""Select exactly one complete fixed-input EXTEND Forward by raw UUID-bound layer record."""
import json,sys
from pathlib import Path
import torch
base=Path(sys.argv[1]);rid=sys.argv[2];ids=[6974,886,2822,13315,1003,506,7217,236761];positions=list(range(1,9));found=[]
for p in base.parent.glob(f'{base.name}.*.layer_output.0'):
 try:r=torch.load(p,map_location='cpu',weights_only=True)
 except Exception:continue
 if r.get('rid')!=[rid] or r.get('forward_mode')!='EXTEND':continue
 actual_ids=r.get('input_ids').tolist();actual_pos=r.get('positions').tolist()
 if actual_ids==ids and actual_pos==positions:
  offset=0
 elif actual_ids[-len(ids):]==ids and actual_pos[-len(ids):]==positions:
  offset=len(actual_ids)-len(ids)
 else:continue
 fid=r.get('forward_id')
 if not isinstance(fid,str) or p.name!=f'{base.name}.{fid}.layer_output.0':continue
 required=[*(f'{base.name}.{fid}.layer_output.{i}' for i in range(42)),f'{base.name}.{fid}.prenorm',f'{base.name}.{fid}.finalnorm',f'{base.name}.{fid}.logits',f'{base.name}.{fid}.manifest']
 if all((base.parent/n).is_file() for n in required):found.append((fid,offset))
if len(found)!=1:raise SystemExit(f'expected exactly one complete target Forward, got {len(found)}')
print(found[0][0],found[0][1])
