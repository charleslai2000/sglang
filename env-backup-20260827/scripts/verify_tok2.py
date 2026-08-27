import json, os
os.environ["HF_HUB_OFFLINE"]="1"
os.environ["TRANSFORMERS_OFFLINE"]="1"
from transformers import AutoTokenizer
MODEL="/model"
tk=AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
def enc(s): return len(tk.encode(s, add_special_tokens=False))
dc=json.load(open("/tmp/p3-cold.payload.json"))
content=dc["messages"][0]["content"]
print("docC content_chars", len(content))
print("docC prompt_tokens", enc(content))
import re
m=re.search(r"\n\nQuestion: ", content)
body=content[:m.start()]; question=content[m.start():]
print("docC body_tokens", enc(body), "question_tokens", enc(question))
print("docC body+question", enc(body)+enc(question))
l2=json.load(open("/tmp/t5-leg200.json"))
print("leg200 prompt_tokens", enc(l2["messages"][0]["content"]))
