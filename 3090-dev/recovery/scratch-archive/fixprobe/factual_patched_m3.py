import json, urllib.request, re
BASE="http://127.0.0.1:30164"
Q=[("Paris",  "What is the capital of France? Answer with only the city name."),
   ("Tokyo",  "What is the capital of Japan? Answer with only the city name."),
   ("Rome",   "What is the capital of Italy? Answer with only the city name."),
   ("42",     "What is 7 times 6? Answer with only the number."),
   ("42",     "What is 12 plus 30? Answer with only the number."),
   ("81",     "What is 9 times 9? Answer with only the number."),
   ("7",      "How many days are in a week? Answer with only the number."),
   ("blue",   "What color is the sky on a clear day? Answer with one word.")]
def chat(user,n=24):
    p={"model":"x","messages":[{"role":"user","content":user}],"temperature":0,"max_tokens":n}
    req=urllib.request.Request(BASE+"/v1/chat/completions",data=json.dumps(p).encode(),
        headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=300) as r:
        b=json.loads(r.read().decode())
    return b["choices"][0]["message"].get("content") or ""
ok=0
for exp,u in Q:
    try:
        c=chat(u)
    except Exception as e:
        print(f"  ERR {e}"); continue
    hit = bool(re.search(r'(?<![0-9])'+re.escape(exp)+r'(?![0-9])', c, re.I))
    ok+=hit
    print(f"  exp={exp:6s} hit={hit!s:5s} out={c[:90]!r}")
print(f"SCORE {ok}/{len(Q)}")
