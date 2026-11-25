#!/usr/bin/env python3
import glob,json,os
root=os.path.dirname(__file__)
for cfg in ('gpu-only','gpu-host'):
 print('\n'+cfg)
 rows=[]
 for f in glob.glob(root+f'/*-{cfg}-*-trial1.jsonl'):
  d=json.loads(open(f).readline());errors=sum(bool(x) for x in d.get('errors',[]));details=[x for x in (d.get('cached_tokens_details') or []) if isinstance(x,dict)]
  device=sum(x.get('device',0) for x in details);host=sum(x.get('host',0) for x in details);storage=sum(x.get('storage',0) for x in details)
  name=os.path.basename(f).split(cfg+'-')[1].split('-trial')[0];case,conc=name.rsplit('-c',1)
  rows.append((case,int(conc),d.get('completed'),d.get('request_throughput'),d.get('input_throughput'),d.get('output_throughput'),d.get('p95_ttft_ms'),d.get('median_tpot_ms'),d.get('p95_e2e_latency_ms'),d.get('concurrency'),errors,device,host,storage))
 for case in ('p-heavy','d-heavy','long-context'):
  for r in sorted((x for x in rows if x[0]==case),key=lambda x:x[1]):print(case,*[round(x,2) if isinstance(x,float) else x for x in r[1:]])
