#!/usr/bin/env python3
import glob,json,os,statistics
root=os.path.dirname(__file__)
for cfg in ('gpu-only','gpu-host'):
 print('\n'+cfg)
 rows={}
 for f in glob.glob(root+f'/*-{cfg}-t*/*/*/result.jsonl'):
  d=json.loads(open(f).readline()); parts=f.split(os.sep); run=parts[-4]; case=parts[-3]; conc=int(parts[-2][1:]);details=[x for x in (d.get('cached_tokens_details') or []) if isinstance(x,dict)]
  entry=rows.setdefault((case,conc),[])
  entry.append({'run':run,'req_s':d['request_throughput'],'input_tps':d['input_throughput'],'output_tps':d['output_throughput'],'ttft_p50':d['median_ttft_ms'],'ttft_p95':d['p95_ttft_ms'],'tpot_p50':d['median_tpot_ms'],'tpot_p95':d['p95_tpot_ms'],'e2e_p50':d['median_e2e_latency_ms'],'e2e_p95':d['p95_e2e_latency_ms'],'completed':d['completed'],'errors':sum(bool(x) for x in d.get('errors',[])),'effective_concurrency':d['concurrency'],'device_hit_tokens':sum(x.get('device',0) for x in details),'host_hit_tokens':sum(x.get('host',0) for x in details),'storage_hit_tokens':sum(x.get('storage',0) for x in details)})
 for key,vals in sorted(rows.items()):
  for v in vals:print(key,v)
  if len(vals)>=2:print(key,'means', {k:statistics.mean(x[k] for x in vals) for k in ('req_s','input_tps','output_tps','ttft_p95','tpot_p50','e2e_p95')}, 'stdev', {k:statistics.stdev(x[k] for x in vals) for k in ('req_s','input_tps','output_tps')})
