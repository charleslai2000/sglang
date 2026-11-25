import json,requests
from transformers import AutoTokenizer
base='http://127.0.0.1:30126'; s=requests.Session(); out='/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R4-20261009T0920Z/'
tok=AutoTokenizer.from_pretrained('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4',trust_remote_code=True)
def gen(ids,max_new,tag):
 d=s.post(base+'/generate',json={'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':max_new,'ignore_eos':True},'return_logprob':False,'return_cached_tokens_details':True},timeout=300).json()
 if 'error' in d: raise RuntimeError(d)
 m=d.get('meta_info',{}); row={'tag':tag,'input_tokens':m.get('prompt_tokens'),'output_tokens':m.get('completion_tokens'),'cached_tokens':m.get('cached_tokens'),'cached_details':m.get('cached_tokens_details'),'finish_reason':m.get('finish_reason'),'e2e':m.get('e2e_latency'),'output_ids':d.get('output_ids')}
 with open(out+'requests.jsonl','a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='output_ids'}),flush=True)
 return row
def snap(tag):
 m=s.get(base+'/metrics',timeout=20).text
 pats=['prefill_effective_tokens_total','cached_tokens_total','hicache_host_used_tokens','hicache_host_total_tokens','hicache_mamba_host_usable_tokens','hicache_backup_tokens_total','backuped_tokens_total','prefetched_tokens_total','load_back_tokens_total','load_back_bytes_total','evicted_tokens_total','hicache_dropped_tokens_total']
 rows=[x for x in m.splitlines() if not x.startswith('#') and any(n in x for n in pats)]
 open(out+tag+'.metrics','w').write('\n'.join(rows)+'\n'); print('METRICS',tag,'\n'+'\n'.join(rows),flush=True)
# Frozen tokenizer IDs, 300-token target prompt (checkpoint boundary is 256).
def prompt(i):
 text=(f'R4 conversation {i:03d}. The reference prefix is: ' + ('blue copper river lantern meadow ' * 75) + f' Session-specific tail {i:03d}.')
 ids=tok.encode(text,add_special_tokens=False)
 return ids[:300] if len(ids)>300 else ids
snap('baseline')
target=prompt(900); print('target_len',len(target),flush=True)
ref=gen(target,270,'target_reference')
snap('after_target')
# Bounded demand for distinct full checkpoints; stop on first measured backup or at 40.
for i in range(40):
 ids=prompt(i)
 r=gen(ids,270,f'pressure_{i:02d}')
 if (i+1)%2==0: snap(f'pressure_{i+1:02d}')
 if i>=15:
  m=s.get(base+'/metrics',timeout=20).text
  if 'hicache_backup_tokens_total' in m and any(float(x.split()[-1])>0 for x in m.splitlines() if 'hicache_backup_tokens_total' in x and not x.startswith('#')):
   print('STOP: positive D2H backup counter',i+1,flush=True);break
snap('before_target_revisit')
rev=gen(target,270,'target_revisit')
print('target_output_equal',ref['output_ids']==rev['output_ids'],flush=True)
snap('after_target_revisit')
