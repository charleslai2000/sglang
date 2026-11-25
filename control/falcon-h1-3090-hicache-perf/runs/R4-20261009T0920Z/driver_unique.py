import json,requests
from transformers import AutoTokenizer
base='http://127.0.0.1:30126';s=requests.Session();out='/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R4-20261009T0920Z/'
tok=AutoTokenizer.from_pretrained('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4',trust_remote_code=True)
def prompt(i):
 # Session identity occurs before any shared body, so no common FULL/MAMBA checkpoint prefix.
 txt=f'SessionKey{i:05d} starts a separate conversation. ' + (f'case{i:05d} azure cedar orbit violet meadow ' * 80)
 return tok.encode(txt,add_special_tokens=False)[:300]
def snap(tag):
 m=s.get(base+'/metrics',timeout=20).text
 pats=['prefill_effective_tokens_total','cached_tokens_total','hicache_host_used_tokens','hicache_host_total_tokens','hicache_mamba_host_usable_tokens','hicache_backup_tokens_total','backuped_tokens_total','prefetched_tokens_total','load_back_tokens_total','load_back_bytes_total','evicted_tokens_total','hicache_dropped_tokens_total']
 rows=[x for x in m.splitlines() if not x.startswith('#') and any(p in x for p in pats)]
 open(out+tag+'.metrics','w').write('\n'.join(rows)+'\n');print('METRICS',tag,'\n'+'\n'.join(rows),flush=True)
def gen(ids,n,tag):
 d=s.post(base+'/generate',json={'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':n,'ignore_eos':True},'return_cached_tokens_details':True},timeout=300).json()
 if 'error' in d: raise RuntimeError(d)
 m=d['meta_info']; row={'tag':tag,'prompt_tokens':m.get('prompt_tokens'),'completion_tokens':m.get('completion_tokens'),'cached_tokens':m.get('cached_tokens'),'details':m.get('cached_tokens_details'),'output_ids':d.get('output_ids'),'e2e':m.get('e2e_latency')}
 with open(out+'unique_requests.jsonl','a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='output_ids'}),flush=True);return row
snap('unique_baseline');tgt=prompt(90001);print('unique target prompt len',len(tgt),flush=True);ref=gen(tgt,270,'unique_target_reference');snap('unique_after_target')
for i in range(24):
 gen(prompt(i),270,f'unique_pressure_{i:02d}')
 if i%2==1: snap(f'unique_pressure_{i+1:02d}')
snap('unique_before_revisit');again=gen(tgt,270,'unique_target_revisit');print('UNIQUE_TARGET_OUTPUT_EQUAL',ref['output_ids']==again['output_ids'],flush=True);snap('unique_after_revisit')
