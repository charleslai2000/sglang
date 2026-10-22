#!/usr/bin/env python3
"""Compare one audited service Forward's exact fixed-token slice with pinned HF Oracle."""
import json,sys
from pathlib import Path
import torch
base=Path(sys.argv[1]);fid=sys.argv[2];rid=sys.argv[3];offset=int(sys.argv[4]);oracle_path=Path(sys.argv[5]);out=Path(sys.argv[6]);prefix=f'{base.name}.{fid}.'
load=lambda n:torch.load(base.parent/(prefix+n),map_location='cpu',weights_only=True)
oracle=torch.load(oracle_path,map_location='cpu',weights_only=True);identity=json.loads((base.parent/'verified-capture.json').read_text());oi=json.loads((oracle_path.parent/'oracle-audit.json').read_text());ids=[6974,886,2822,13315,1003,506,7217,236761];pos=list(range(1,9))
if identity.get('status')!='COMPLETE' or identity.get('forward_id')!=fid or identity.get('rid')!=rid or identity.get('input_ids')!=ids or identity.get('positions')!=pos or identity.get('input_token_offset')!=offset or identity.get('model_identity',{}).get('model_revision')!='6cd26aaa2357fb2bad8c51699a7558a4d1a965bb' or identity.get('model_identity',{}).get('model_sha256')!='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d':raise RuntimeError('capture identity mismatch')
if oi.get('model_safetensors_sha256')!='19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d' or oi.get('transformers_version')!='5.12.1':raise RuntimeError('Oracle identity mismatch')
records=[load(f'layer_output.{i}') for i in range(42)]+[load('prenorm'),load('finalnorm'),load('logits')]
assert all(r.get('forward_id')==fid and r.get('rid')==[rid] and r['forward_mode']=='EXTEND' for r in records)
assert all(r['input_ids'].tolist()==identity['forward_input_ids'] and r['positions'].tolist()==identity['forward_positions'] for r in records)
assert all(torch.isfinite(r['output']).all() for r in records)
sl=lambda r:r['output'].float()[offset:offset+len(ids)]
assert all(r['input_ids'].tolist()[offset:offset+len(ids)]==ids and r['positions'].tolist()[offset:offset+len(pos)]==pos for r in records)
logits=load('logits')['output'].float();assert logits.shape==(1,262144)
layers=oracle['hidden_states'];get=(lambda i:layers[f'h{i+1}'].float().squeeze(0)) if isinstance(layers,dict) else (lambda i:layers[i+1].float().squeeze(0))
report={'status':'NUMERICS_COMPLETE','capture_integrity_status':identity['status'],'verified_artifact_hashes':identity['artifact_sha256'],'forward_id':fid,'rid':rid,'input_ids':ids,'positions':pos,'input_token_offset':offset,'oracle_identity':{'model_revision':oi['model_revision'],'model_sha256':oi['model_safetensors_sha256'],'transformers_version':oi['transformers_version'],'oracle_artifact_sha256':oi['oracle_artifact_sha256']},'layers':[]}
for i,r in enumerate(records[:42]):
 val=sl(r);ref=get(i);d=val-ref;report['layers'].append({'layer':i,'max_abs':d.abs().max().item(),'mean_abs':d.abs().mean().item(),'rmse':d.square().mean().sqrt().item(),'rel_l2':(d.norm()/ref.norm()).item()})
for name,ref in [('prenorm',oracle['layer41_prenorm'].float().squeeze(0)),('finalnorm',oracle['final_norm_hidden_states'].float().squeeze(0))]:
 d=sl(load(name))-ref;report[name]={'max_abs':d.abs().max().item(),'mean_abs':d.abs().mean().item(),'rmse':d.square().mean().sqrt().item(),'rel_l2':(d.norm()/ref.norm()).item()}
ref=oracle['logits_last_token'].float().reshape(1,-1);last=logits[-1:];d=last-ref;report['logits']={'numel':last.numel(),'max_abs':d.abs().max().item(),'mean_abs':d.abs().mean().item(),'rmse':d.square().mean().sqrt().item(),'rel_l2':(d.norm()/ref.norm()).item()};report['greedy']={'service':int(last.argmax(-1).item()),'oracle':int(ref.argmax(-1).item())};report['top10_id_set_equal']=set(torch.topk(last.flatten(),10).indices.tolist())==set(torch.topk(ref.flatten(),10).indices.tolist());tol=oi['tolerance']['metrics'];report['tolerance']=tol;report['bf16_numeric_pass']=bool(report['logits']['max_abs']<=tol['full_vocab_logits_max_abs_error'] and report['logits']['mean_abs']<=tol['full_vocab_logits_mean_abs_error'] and report['top10_id_set_equal']==tol['top10_id_set_must_match'] and report['greedy']['service']==report['greedy']['oracle']);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'bf16_numeric_pass':report['bf16_numeric_pass'],'logits':report['logits'],'top10_id_set_equal':report['top10_id_set_equal'],'greedy':report['greedy']}))
