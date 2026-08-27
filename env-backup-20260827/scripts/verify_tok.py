import json, os
os.environ["HF_HUB_OFFLINE"]="1"
os.environ["TRANSFORMERS_OFFLINE"]="1"
from transformers import AutoTokenizer
MODEL="/model"
tk=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
def enc(s): return len(tk.encode(s, add_special_tokens=False))
# doc C
dc=json.load(open("/opt/b0-data/p3-cold.payload.json"))
content=dc["messages"][0]["content"]
print("docC content_chars", len(content))
print("docC prompt_tokens", enc(content))
import re
m=re.search(r"\n\nQuestion: ", content)
body=content[:m.start()]; question=content[m.start():]
print("docC body_tokens", enc(body), "question_tokens", enc(question))
# leg200
l2=json.load(open("/opt/b0-data/t5-leg200.json"))
print("leg200 prompt_tokens", enc(l2["messages"][0]["content"]))
# check tokenizer files present
import glob
print("tok files:", [os.path.basename(x) for x in glob.glob("/model/*") if "tok" in x.lower() or "vocab" in x.lower() or x.endswith(".json")][:10])
