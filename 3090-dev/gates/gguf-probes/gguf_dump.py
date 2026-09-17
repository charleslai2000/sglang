import sys, gguf, collections
path = sys.argv[1]
r = gguf.GGUFReader(path)
rows = []
for t in r.tensors:
    n = t.name
    if any(k in n for k in ("norm", "attn_norm", "output_norm", "attn_q_norm", "attn_k_norm", "ssm_norm", "ffn_norm")):
        rows.append((n, str(t.tensor_type).replace("GGML_TYPE_",""), tuple(t.shape), t.data.dtype))
rows.sort()
for n, tt, sh, dt in rows:
    print(f"{n:55s} {tt:10s} shape={sh} numpy_dtype={dt}")
print("TOTAL norm-ish:", len(rows))
print("=== tensors with 'blk.64' or blk.65 ===")
for t in r.tensors:
    if t.name.startswith(("blk.64", "blk.65", "blk.63")):
        print(t.name, str(t.tensor_type).replace("GGML_TYPE_",""), tuple(t.shape))
print("=== all distinct prefixes / general keys ===")
print("n_tensors:", len(r.tensors))
