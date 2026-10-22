#!/usr/bin/env python3
"""Exercise real OpenAI completions stop, streaming, and disconnect cancellation."""
import json,time,urllib.request,urllib.error,threading,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
out=Path(os.environ['GEMMA4_RUN_OUT']);url='http://127.0.0.1:31042/v1/completions';prompt=[6974,886,2822,13315,1003,506,7217,236761]
def post(payload,timeout=300):
 req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'});return urllib.request.urlopen(req,timeout=timeout)
# Exact stop token: at this prompt greedy first token is known to be 108.
stop={'prompt':prompt,'max_tokens':8,'temperature':0.0,'stop_token_ids':[108]};t=time.perf_counter();r=json.loads(post(stop).read());stop_result={'latency_s':time.perf_counter()-t,'response':r,'pass':r.get('usage',{}).get('completion_tokens')==0 or r.get('choices',[{}])[0].get('finish_reason')=='stop'};(out/'stop-token.json').write_text(json.dumps(stop_result,indent=2)+'\n')
# Streaming contract and first-token arrival.
stream={'prompt':prompt,'max_tokens':16,'temperature':0.0,'stream':True};t=time.perf_counter();resp=post(stream);chunks=[];first=None
for line in resp:
 if line.startswith(b'data:') and b'[DONE]' not in line:
  obj=json.loads(line[5:]);chunks.append(obj)
  if first is None:first=time.perf_counter()-t
stream_result={'chunks':len(chunks),'first_chunk_s':first,'has_text_delta':any(c.get('choices',[{}])[0].get('text') for c in chunks),'has_finish':any(c.get('choices',[{}])[0].get('finish_reason') for c in chunks)};(out/'streaming.json').write_text(json.dumps(stream_result,indent=2)+'\n')
# Disconnect client while a deliberately longer decode is running; confirm service remains healthy and subsequent request works.
long={'prompt':prompt,'max_tokens':256,'temperature':0.0,'stream':True};started=threading.Event();holder={}
def disconnect():
 try:
  rr=post(long);started.set();holder['first']=rr.readline().decode(errors='replace');rr.close()
 except Exception as e:holder['error']=repr(e);started.set()
with ThreadPoolExecutor(max_workers=1) as ex:
 f=ex.submit(disconnect);started.wait(60);time.sleep(.25)
cancel={'client_disconnected':True,'first_chunk':holder.get('first'),'error':holder.get('error')};health=urllib.request.urlopen('http://127.0.0.1:31042/health',timeout=30).status;cancel['health_status_after_disconnect']=health
req={'prompt':prompt,'max_tokens':1,'temperature':0.0};cancel['subsequent_request_status']=json.loads(post(req).read()).get('choices',[{}])[0].get('finish_reason');(out/'disconnect-cancel.json').write_text(json.dumps(cancel,indent=2)+'\n')
print(json.dumps({'stop_token_pass':stop_result['pass'],'streaming':stream_result,'disconnect_cancel':cancel},indent=2))
