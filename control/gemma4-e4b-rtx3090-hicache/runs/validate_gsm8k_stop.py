#!/usr/bin/env python3
"""Validate SGLang stop responses against the official lm-eval first-match filter."""
import json, os, re, subprocess, sys, time
from pathlib import Path
import requests
from transformers import AutoTokenizer
ROOT=Path('/home/ubuntu/workspaces/3rdparty/sglang-hicache'); DATA=Path('/data/sglang-hicache/gemma4'); OUT=DATA/'runs/20261026T-gsm8k-stop-validation'; MODEL=DATA/'model'; PORT=31205
OUT.mkdir(parents=True,exist_ok=True); MAX_TOKENS=int(os.environ.get('GSM8K_DIAG_MAX_TOKENS','512')); VENV='/home/ubuntu/venvs/sglang-3090'
env=os.environ.copy(); env.update(PYTHONNOUSERSITE='1',PYTHONPATH=f'{ROOT}/control/gemma4-e4b-rtx3090-hicache/runs:{ROOT}/python:{DATA}/aot-sm86-build:{ROOT}/3rdparty/sglang/python/sglang/kernels/aot/python',LD_LIBRARY_PATH=f'{VENV}/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64')
cmd=[f'{VENV}/bin/python','-m','sglang.launch_server','--model-path',str(MODEL),'--trust-remote-code','--host','127.0.0.1','--port',str(PORT),'--context-length','8192','--max-running-requests','1','--mem-fraction-static','.94','--disable-radix-cache','--kv-cache-dtype','bf16','--attention-backend','triton','--cuda-graph-max-bs-decode','1','--skip-server-warmup','--log-level','info']
with (OUT/'server.log').open('w') as log:
 p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  for _ in range(240):
   if p.poll() is not None: raise RuntimeError(f'server exited {p.returncode}')
   try:
    if requests.get(f'http://127.0.0.1:{PORT}/health',timeout=2).ok: break
   except requests.RequestException: pass
   time.sleep(2)
  else: raise TimeoutError('server readiness')
  tok=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=True); docs=[json.loads(x) for x in (DATA/'runs/gsm8k-prepare-20261026/data/test.jsonl').read_text().splitlines()]; shots=docs[:5]; rows=[]
  for i,d in enumerate(docs[5:17],5):
   prompt=''.join(f"Question: {s['question']}\nAnswer: {s['answer']}\n\n" for s in shots)+f"Question: {d['question']}\nAnswer:"; ids=[tok.bos_token_id]+tok.encode(prompt,add_special_tokens=False); stops=['Question:','</s>','<|im_end|>',tok.decode(tok.eos_token_id)]
   r=requests.post(f'http://127.0.0.1:{PORT}/v1/completions',json={'prompt':ids,'model':'gemma4','max_tokens':MAX_TOKENS,'temperature':0.0,'top_p':1.0,'stop':stops,'return_token_ids':True},timeout=600); r.raise_for_status(); c=r.json()['choices'][0]; text=c['text']; tids=c.get('token_ids') or []; decoded=tok.decode(tids,skip_special_tokens=False); match=c.get('matched_stop')
   stop_piece=tok.decode([match],skip_special_tokens=False) if isinstance(match,int) else (match or '')
   # Since stop token IDs are excluded from output_ids, rendered text must be taken
   # from response.text; matched_stop identifies the server-side boundary.
   pred=re.findall(r'#### (\-?[0-9\.\,]+)',text)
   rows.append({'doc_id':i,'requested_stop':stops,'finish_reason':c.get('finish_reason'),'matched_stop':match,'response_text':text,'response_token_ids':tids,'decoded_response_ids':decoded,'stop_piece':stop_piece,'max_tokens':MAX_TOKENS,'score_input':pred[0] if pred else '[invalid]','question_leakage':'Question:' in text})
  summary={'n':len(rows),'all_finish_stop':all(x['finish_reason']=='stop' for x in rows),'all_matched_stop_recognized':all(x['matched_stop'] in stops or isinstance(x['matched_stop'],int) for x in rows),'no_question_leakage':all(not x['question_leakage'] for x in rows),'strict_first_extractor_reproduced':all(x['score_input']==((re.findall(r'#### (\-?[0-9\.\,]+)',x['response_text']) or ['[invalid]'])[0]) for x in rows),'rows':[{'doc_id':x['doc_id'],'finish_reason':x['finish_reason'],'matched_stop':x['matched_stop'],'score_input':x['score_input'],'text_tail':x['response_text'][-65:]} for x in rows]}
  (OUT/'probe.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False)+'\n');(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
 finally:
  p.terminate()
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:p.kill();p.wait()
