import json, urllib.request
BASE="http://127.0.0.1:30164"
def gen(text, n=8, topk=20):
    p={"text":text,"sampling_params":{"temperature":0,"max_new_tokens":n},
       "return_logprob":True,"logprob_start_len":0,"top_logprobs_num":topk}
    req=urllib.request.Request(BASE+"/generate",data=json.dumps(p).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=300) as r:
        return json.loads(r.read().decode())
def first_top(tag, prompt):
    b=gen(prompt,1,20)
    mi=b.get("meta_info",{})
    tl=mi.get("input_token_logprobs") or []
    # first generated token distribution
    gen_lp=mi.get("output_token_logprobs") or []
    top=mi.get("output_top_logprobs") or mi.get("top_logprobs") or []
    print(f"[{tag}] prompt={prompt!r}")
    print(f"   greedy_next={b.get('text')!r} lp={gen_lp[0][0] if gen_lp else None}")
    if top:
        t0=top[0]
        print("   top20:", [(x[1], round(x[0],2)) for x in t0[:20]])
    else:
        print("   keys in meta:", list(mi.keys()))
for tag,p in [("capital","The capital of France is"),
              ("count","1 2 3 4 5"),
              ("germany","The capital of Germany is"),
              ("color","The sky is")]:
    try: first_top(tag,p)
    except Exception as e: print(tag,"ERR",type(e).__name__,e)
