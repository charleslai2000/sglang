import json,requests
from transformers import AutoTokenizer
base='http://127.0.0.1:30126';s=requests.Session();out='/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R4-20261009T0920Z/'
tok=AutoTokenizer.from_pretrained('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4',trust_remote_code=True)
def prompt(i):
 txt=f'Separate SessionKey{i:05d}. ' + (f'case{i:05d} azure cedar orbit violet meadow ' * 80)
 return tok.encode(txt,add_special_tokens=False)[:300]
def gen(ids,n,tag):
 d=s.post(base+'/generate',json={'input_ids':ids,'sampling_params':{'temperature':0,'max_new_tokens':n,'ignore_eos':True},'return_cached_tokens_details':True},timeout=300).json()
 if 'error' in d: raise RuntimeError(d)
 m=d['meta_info'];row={'tag':tag,'prompt_tokens':m.get('prompt_tokens'),'completion_tokens':m.get('completion_tokens'),'cached_tokens':m.get('cached_tokens'),'details':m.get('cached_tokens_details'),'output_ids':d.get('output_ids'),'e2e':m.get('e2e_latency')}
 with open(out+'mamba_eviction_requests.jsonl','a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps({k:v for k,v in row.items() if k!='output_ids'}),flush=True);return row
def metrics():
 txt=s.get(base+'/metrics',timeout=20).text; names=['mamba_available_tokens','mamba_evictable_tokens','hicache_host_used_tokens','hicache_backup_tokens_total','load_back_tokens_total','evicted_tokens_total','prefill_effective_tokens_total','hicache_dropped_tokens_total']
 return [x for x in txt.splitlines() if not x.startswith('#') and any(n in x for n in names)]
print('before',*metrics(),sep='\n',flush=True)
for i in range(16,41):
 gen(prompt(i),270,f'pressure_{i:02d}')
 if i%4==3: print('snapshot',i,*metrics(),sep='\n',flush=True)
print('before_target',*metrics(),sep='\n',flush=True)
row=gen(prompt(90001),270,'target_revisit_after_more_mamba_pressure')
print('TARGET_CACHED_DETAILS',row['details'],flush=True)
print('after_target',*metrics(),sep='\n',flush=True)
