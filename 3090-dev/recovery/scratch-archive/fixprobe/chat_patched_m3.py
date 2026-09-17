import json, urllib.request
BASE="http://127.0.0.1:30164"
def chat(user, n=64, thinking=None):
    p={"model":"x","messages":[{"role":"user","content":user}],
       "temperature":0,"max_tokens":n}
    kw={}
    if thinking is not None: kw["chat_template_kwargs"]={"enable_thinking":thinking}
    p.update(kw)
    req=urllib.request.Request(BASE+"/v1/chat/completions",data=json.dumps(p).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=300) as r:
        b=json.loads(r.read().decode())
    return b["choices"][0]["message"].get("content"), b["choices"][0].get("finish_reason")
for tag,u,n in [("capital","What is the capital of France? Answer with only the city name.",64),
                ("arith","Question: What is 17 times 3? Answer with only the number.",64),
                ("sum","What is 2 + 2? Answer with only the number.",64)]:
    for th in (False,None):
        try:
            c,fr=chat(u,n,th)
            print(f"[{tag} thinking={th}] finish={fr} -> {c!r}")
        except Exception as e:
            print(f"[{tag} thinking={th}] ERR {type(e).__name__}: {e}")
