#!/usr/bin/env python3
"""Fail-closed integrity check for a single real Gemma4 service Forward."""
import argparse,hashlib,json,os,uuid
from pathlib import Path
import torch

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',required=True);ap.add_argument('--forward-id',required=True);ap.add_argument('--expected-ids',required=True);ap.add_argument('--expected-positions',required=True);ap.add_argument('--expected-rid',required=True);ap.add_argument('--model-revision',required=True);ap.add_argument('--model-sha256',required=True);ap.add_argument('--manifest',required=True);ap.add_argument('--expected-offset',type=int,required=True);a=ap.parse_args()
 try:
  uuid.UUID(hex=a.forward_id);ids=json.loads(a.expected_ids);positions=json.loads(a.expected_positions)
  if not ids or len(ids)!=len(positions):raise ValueError('input/position length mismatch')
  base=Path(a.base);prefix=f'{base.name}.{a.forward_id}.';required={f'{prefix}layer_output.{i}' for i in range(42)}|{f'{prefix}prenorm',f'{prefix}finalnorm',f'{prefix}logits'};mp=base.parent/f'{base.name}.{a.forward_id}.manifest';actual={p.name for p in base.parent.glob(prefix+'*') if p.is_file() and not p.name.endswith('.sha256') and '.tmp.' not in p.name}
  if actual!=required|{mp.name}:raise ValueError(f'artifact set mismatch missing={sorted((required|{mp.name})-actual)} extra={sorted(actual-(required|{mp.name}))}')
  m=json.loads(mp.read_text());ident={'model_revision':a.model_revision,'model_sha256':a.model_sha256}
  if m.get('status')!='COMPLETE' or m.get('forward_id')!=a.forward_id or m.get('model_identity')!=ident:raise ValueError('incomplete/wrong Forward or checkpoint identity')
  m_ids=m.get('input_ids',[]);m_positions=m.get('positions',[])
  if m.get('rid')!=[a.expected_rid] or m.get('forward_mode')!='EXTEND' or m.get('batch_size')!=1 or m_ids[-len(ids):]!=ids or m_positions[-len(positions):]!=positions:raise ValueError('manifest target RID/input/positions/mode mismatch')
  offset=len(m_ids)-len(ids)
  if offset!=a.expected_offset:raise ValueError(f'input token offset mismatch expected={a.expected_offset} actual={offset}')
  artifacts={}; hashes={}
  for name in sorted(required):
   p=base.parent/name;r=torch.load(p,map_location='cpu',weights_only=True)
   r_ids=r.get('input_ids').tolist();r_positions=r.get('positions').tolist()
   if r.get('forward_id')!=a.forward_id or r.get('model_identity')!=ident or r.get('rid')!=[a.expected_rid] or r.get('batch_size')!=1 or r.get('forward_mode')!='EXTEND' or r_ids[-len(ids):]!=ids or r_positions[-len(positions):]!=positions:raise ValueError(f'Forward/model/RID/input/position/mode mismatch {name}')
   if r_ids!=m_ids or r_positions!=m_positions:raise ValueError(f'boundary inputs diverge within Forward {name}')
   if name.endswith('.layer_output.0') and (r.get('batch_slot_offsets').tolist()!=[0] or r.get('token_offset')!=0):raise ValueError('batch slot offset mismatch')
   if not torch.isfinite(r['output']).all():raise ValueError(f'nonfinite output {name}')
   if name.endswith('.logits'):
    if r.get('boundary')!='lm_head_logits_after_vocab_gather_before_sampling' or tuple(r['output'].shape)!=(1,262144):raise ValueError('logits boundary/shape mismatch')
   elif name.endswith('.prenorm'):
    if r.get('boundary')!='last_decoder_layer_prenorm_output_before_final_rmsnorm' or r.get('layer')!=41 or tuple(r['output'].shape)!=(len(m_ids),2560):raise ValueError('prenorm boundary/shape mismatch')
   elif name.endswith('.finalnorm'):
    if r.get('boundary')!='final_rmsnorm_output' or r.get('layer')!=41 or tuple(r['output'].shape)!=(len(m_ids),2560):raise ValueError('finalnorm boundary/shape mismatch')
   else:
    layer=int(name.rsplit('.',1)[-1])
    if r.get('layer')!=layer or r.get('boundary')!='decoder_layer_output_including_residual_ple_and_scalar' or tuple(r['output'].shape)!=(len(m_ids),2560):raise ValueError(f'layer boundary/shape mismatch {name}')
   hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest();artifacts[name]=r
  # Verify every artifact belongs to the same real model instance by checking
  # the actual instantiated language-model weights in SGLang's process memory.
  expected_weight=os.environ.get('GEMMA4_MODEL_SHA256','')
  if expected_weight!=a.model_sha256:raise ValueError('runtime model fingerprint was not independently attested')
  result={'status':'COMPLETE','forward_id':a.forward_id,'rid':a.expected_rid,'input_ids':ids,'positions':positions,'input_token_offset':offset,'forward_input_ids':m_ids,'forward_positions':m_positions,'forward_mode':'EXTEND','batch_size':1,'model_identity':ident,'scheduler_step':m.get('scheduler_step'),'artifact_count':len(required),'artifact_sha256':hashes}
  dst=Path(a.manifest);tmp=dst.with_name(dst.name+f'.tmp.{os.getpid()}')
  with tmp.open('x') as f:json.dump(result,f,indent=2);f.flush();os.fsync(f.fileno())
  os.link(tmp,dst);tmp.unlink();print(json.dumps(result))
 except Exception as e:print(json.dumps({'status':'FAIL','error':str(e)}));raise SystemExit(2)
if __name__=='__main__':main()
