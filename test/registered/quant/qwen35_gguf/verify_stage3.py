"""Stage 3: config / name-map / tokenizer sanity checks (no GPU, no serving).

Verifies:
  1. GGUF metadata reads and the native config builds with expected dims.
  2. name map covers all 851 tensors, no missing/unexpected/collisions.
  3. native tokenizer (from GGUF) parity vs downloaded tokenizer.json
     on Chinese/English/digits/special tokens.
"""

import json
import sys

MODEL = "/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf"
TOKJSON = "/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/tokenizer.json"

failures = []


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def main():
    # ---- 1. metadata + config ----
    from gguf import GGUFReader
    from sglang.srt.configs.qwen35_gguf import build_qwen35_gguf_config

    reader = GGUFReader(MODEL)
    tensors = list(reader.tensors)
    check("851 tensors in GGUF", len(tensors) == 851, f"got {len(tensors)}")

    meta = {k: f.contents() for k, f in reader.fields.items()}
    cfg = build_qwen35_gguf_config(MODEL)
    text = cfg.text_config
    check("64 layers", text.num_hidden_layers == 64, str(text.num_hidden_layers))
    check(
        "48 GDN linear layers (16 full)",
        text.num_hidden_layers - (text.num_hidden_layers // text.full_attention_interval)
        == 48,
        f"full_interval={text.full_attention_interval}",
    )
    check("vocab_size > 0", text.vocab_size > 0, str(text.vocab_size))
    check("head_dim", text.head_dim > 0, str(text.head_dim))
    check(
        "rope partial_rotary_factor in (0,1]",
        0 < text.partial_rotary_factor <= 1,
        str(text.partial_rotary_factor),
    )
    print("  config summary:", {
        "hidden": text.hidden_size,
        "layers": text.num_hidden_layers,
        "heads": text.num_attention_heads,
        "kv_heads": text.num_key_value_heads,
        "head_dim": text.head_dim,
        "linear_kv_heads": (text.linear_num_key_heads, text.linear_num_value_heads),
        "state_dim": text.linear_key_head_dim,
        "vocab": text.vocab_size,
        "full_interval": text.full_attention_interval,
    })

    # ---- 2. name map ----
    from sglang.srt.model_loader.qwen35_gguf import build_qwen35_name_map

    name_map = build_qwen35_name_map(cfg)
    names = {t.name for t in tensors}
    missing = set(name_map) - names
    missing.discard("output.weight")  # tied embedding legitimately omits it
    unexpected = names - set(name_map)
    check("name_map no missing tensors", not missing, sorted(missing)[:10])
    check("name_map no unexpected tensors", not unexpected, sorted(unexpected)[:10])
    targets = list(name_map.values())
    check("name_map target uniqueness (no collision)", len(set(targets)) == len(targets))
    check("name_map covers all 851", len(name_map) == len(names) or (len(name_map) + 1) == len(names) and "output.weight" in (names - set(name_map)), f"map={len(name_map)} names={len(names)}")

    # ---- 3. tokenizer parity ----
    from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_tokenizer

    native = build_gguf_tokenizer(MODEL)
    ref_json = json.load(open(TOKJSON))
    ref_vocab = ref_json["model"]["vocab"]

    # reference vocab -> id
    ref_vid = {tok: idx for idx, tok in enumerate(ref_vocab)}
    # native encode strings
    def native_ids(s):
        return native.encode(s, add_special_tokens=False)

    # Build a reference tokenizer from tokenizer.json to compare encodings
    from tokenizers import Tokenizer as TK

    ref_tk = TK.from_str(json.dumps(ref_json))
    ref_ids = ref_tk.encode("").ids  # not meaningful; use native vocab mapping instead

    # Compare vocab coverage
    native_vocab = native.get_vocab()
    missing_from_native = [t for t in list(ref_vid)[:20000] if t not in native_vocab and t]
    print("  native vocab size:", len(native_vocab), "ref vocab size:", len(ref_vid))

    probes = [
        ("english", "What is the capital of France?"),
        ("chinese", "中国的首都是哪里？"),
        ("digits", "17 * 23 = 391"),
        ("mixed", "hello 世界 123"),
        ("code", "def f(x): return x**2 + 1"),
    ]
    for label, text in probes:
        n_ids = native_ids(text)
        # reference: use ref tokenizer to encode same string
        r_ids = ref_tk.encode(text).ids
        check(f"tokenizer parity [{label}] same ids", n_ids == r_ids,
              f"native={n_ids} ref={r_ids}")

    # special token ids
    def vid(token):
        return ref_vid.get(token)
    for tok in ["<|endoftext|>", "<|im_start|>", "<|im_end|>", "<|fim_prefix|>",
                "<|fim_suffix|>", "<|fim_middle|>", "<|jailbreak|>", "<|fim_pad|>",
                "<|repo_name|>", "<|file_sep|>"]:
        nid = native.convert_tokens_to_ids(tok)
        rid = vid(tok)
        check(f"special token [{tok}] id parity", nid == rid,
              f"native={nid} ref={rid}")

    print()
    if failures:
        print(f"STAGE3 FAIL: {len(failures)} checks failed")
        sys.exit(1)
    print("STAGE3 ALL PASS")


if __name__ == "__main__":
    main()
