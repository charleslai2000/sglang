import json, os
from transformers import AutoTokenizer
md="/data/models/qwen35-9b-w4a16"
tok=AutoTokenizer.from_pretrained(md, trust_remote_code=False)
print("tokenizer class", type(tok).__name__, "has_chat_template", bool(getattr(tok,'chat_template',None)))
print("len(chat_template)", len(getattr(tok,'chat_template','') or ''))
ct=open(os.path.join(md,"chat_template.jinja")).read()
print("jinja len", len(ct))
msgs=[{"role":"user","content":"Hello there, this is a test."}]
try:
    s=tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, chat_template=ct, enable_thinking=False)
    print("RENDER:", repr(s[:300]))
    ids=tok(s, add_special_tokens=False)["input_ids"]
    print("ids len", len(ids))
except Exception as e:
    print("err", repr(e))
