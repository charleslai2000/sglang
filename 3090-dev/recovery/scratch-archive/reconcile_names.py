import sys, json
SRC="/opt/sglang/local-prod-v1.1-candidate/src/python"
sys.path.insert(0,SRC)
import gguf
from gguf.constants import MODEL_ARCH
from sglang.srt.configs.qwen3_5 import Qwen3_5TextConfig
from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map

PATH="/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf"
cfg=Qwen3_5TextConfig.from_gguf(PATH)
smap=build_qwen35_name_map(cfg)

nm=gguf.get_tensor_name_map(MODEL_ARCH.QWEN35, cfg.num_hidden_layers)
ggml2hf={}
for k,(t,g) in nm.mapping.items():
    if isinstance(k,str) and k.startswith(("blk.","token_embd","output")) and "." not in k.split(".")[0]:
        ggml2hf.setdefault(g,set()).add((t.name,k))

rows=[]
agree=disagree=only_sglang=only_gguf=0
for g in sorted(smap):
    hf=smap[g]
    entries=ggml2hf.get(g,set())
    base=g
    if entries:
        if hf in {k for _,k in entries}:
            agree+=1; rows.append((g,hf,"AGREE",sorted({k for _,k in entries})[:3]))
        elif hf+".weight" in {k for _,k in entries}:
            agree+=1; rows.append((g,hf,"AGREE(+.weight)",sorted({k for _,k in entries})[:3]))
        else:
            disagree+=1; rows.append((g,hf,"DISAGREE",sorted({k for _,k in entries})[:5]))
    else:
        only_sglang+=1; rows.append((g,hf,"NO-GGUF-ENTRY",[]))

print(f"entries in sglang name map: {len(smap)}  AGREE={agree} DISAGREE={disagree} NO-GGUF-ENTRY={only_sglang}")
for r in rows:
    if r[2]!="AGREE" and r[2]!="AGREE(+.weight)":
        print("  ",r)
print()
print("--- sample agrees ---")
for r in rows[:6]: print("  ",r)
print()
# also show what gguf-py maps the interesting HF names from
for hf in ["model.layers.0.linear_attn.in_proj_b","model.layers.0.linear_attn.in_proj_qkv",
           "model.layers.0.linear_attn.dt_bias","model.layers.0.linear_attn.conv1d",
           "model.layers.0.linear_attn.norm","model.layers.0.linear_attn.out_proj",
           "model.layers.0.input_layernorm","model.layers.0.post_attention_layernorm",
           "model.layers.0.self_attn.q_proj","model.layers.0.self_attn.q_norm","model.layers.0.self_attn.k_norm",
           "model.layers.0.self_attn.o_proj","model.layers.0.mlp.gate_proj"]:
    e=nm.mapping.get(hf) or nm.mapping.get(hf+".weight")
    print(f"  {hf:48s} -> {e}")
