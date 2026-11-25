#!/usr/bin/env python3
import json,pathlib,statistics,sys,re,collections
root=pathlib.Path(__file__).parent
rows=json.loads((root/'client-B0-summary.json').read_text())
for c in [1,8,16,24,32]:
 r=[x for x in rows if x['concurrency']==c]
 print(f"c{c}: TPS mean={statistics.mean(x['output_tps'] for x in r):.2f} stdev={statistics.stdev(x['output_tps'] for x in r):.2f} samples="+'/'.join(f"{x['output_tps']:.2f}" for x in r)+f"; TTFTp50={statistics.mean(x['server_ttft_p50_s'] for x in r):.3f}s TPOTp50={statistics.mean(x['server_tpot_p50_s'] for x in r)*1000:.3f}ms ReqP95={statistics.mean(x['request_latency_p95_s'] for x in r):.3f}s ReqP99={statistics.mean(x['request_latency_p99_s'] for x in r):.3f}s")
log=(root/'server.log').read_text(errors='replace').splitlines(); ct=collections.Counter(); graph=collections.Counter(); max_r=collections.Counter()
for l in log:
 if 'Decode batch,' not in l: continue
 m=re.search(r'#running-req: (\d+)',l); g=re.search(r'cuda graph: (True|False)',l)
 if m: ct[int(m.group(1))]+=1
 if m and g: graph[g.group(1)]+=1; max_r[g.group(1)]=max(max_r[g.group(1)],int(m.group(1)))
print('decode active batch histogram',json.dumps(dict(sorted(ct.items())))); print('decode graph counter',dict(graph),'max active by graph',dict(max_r)); print('failed/ooms',sum(' 5' in l and 'HTTP' in l for l in log),sum(bool(re.search(r'(?i)out of memory|oom|cuda error',l)) for l in log))
