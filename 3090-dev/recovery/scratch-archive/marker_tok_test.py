import random, json
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
         "november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee "
         "zulu quantum orbital cascade nebula vertex cipher lattice photon matrix").split()
rng = random.Random(777777)
body = " ".join(rng.choice(WORDS) for _ in range(int(12000 * 1.35)))
MARKER = ("PHASE9-L3-LARGE-PREFIX-8842. This is a large unique prefix for L3 eviction/restore. "
          f"{body} PHASE9-L3-LARGE-PREFIX-8842 END. Reply with exactly: BIGPREFIX8842.")
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("/data/models/qwen35-9b-w4a16")
msgs=[{"role":"user","content":MARKER}]
for kw in ({"enable_thinking": False},):
    try:
        ids = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, **kw)
        print("apply_chat_template add_gen=True", kw, "len=", len(ids))
    except Exception as e:
        print("err", kw, repr(e))
try:
    ids2 = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, chat_template_kwargs={"enable_thinking": False})
    print("chat_template_kwargs len=", len(ids2))
except Exception as e:
    print("err2", repr(e))
