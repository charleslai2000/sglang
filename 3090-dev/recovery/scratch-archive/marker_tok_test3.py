import os, random, json
from transformers import AutoTokenizer
md="/data/models/qwen35-9b-w4a16"
ct=open(os.path.join(md,"chat_template.jinja")).read()
tok=AutoTokenizer.from_pretrained(md)
WORDS=("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
       "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee "
       "zulu quantum orbital cascade nebula vertex cipher lattice photon matrix").split()
rng=random.Random(777777)
body=" ".join(rng.choice(WORDS) for _ in range(int(12000*1.35)))
MARKER=("PHASE9-L3-LARGE-PREFIX-8842. This is a large unique prefix for L3 eviction/restore. "
        f"{body} PHASE9-L3-LARGE-PREFIX-8842 END. Reply with exactly: BIGPREFIX8842.")
msgs=[{"role":"user","content":MARKER}]
for th in (False, True):
    s=tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, chat_template=ct, enable_thinking=th)
    ids=tok(s, add_special_tokens=False)["input_ids"]
    print(f"enable_thinking={th}: rendered_len={len(s)} ids_len={len(ids)}")
    if th is False:
        json.dump(ids, open("/tmp/opencode/marker_ids_thinkFalse.json","w"))
print("target observed prompt_tokens = 23183")
