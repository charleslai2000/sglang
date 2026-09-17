#!/usr/bin/env python3
import sys
import time

sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")

from gguf import GGUFReader

from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
from sglang.srt.model_loader.weight_utils import gguf_quant_weights_iterator
from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_config

path = sys.argv[1]
t = time.time()
config = build_gguf_config(path)
print(f"[{time.time()-t:.1f}s] config built")
t = time.time()
name_map = build_qwen35_name_map(config)
print(f"[{time.time()-t:.1f}s] map built n={len(name_map)}")
t = time.time()
reader = GGUFReader(path)
print(f"[{time.time()-t:.1f}s] reader built n={len(reader.tensors)}")
expected = sum(
    1
    for tensor in reader.tensors
    if tensor.name in name_map and tensor.tensor_type.name != "F32"
)
print("expected type-pass entries:", expected)
del reader
t = time.time()
it = gguf_quant_weights_iterator(path, name_map)
count = 0
for _ in range(expected + 3):
    item = next(it)
    count += 1
    if count <= 3 or count > expected:
        print(f"  entry {count}: {item[0]}")
print(f"[{time.time()-t:.1f}s] drained {count} entries")
it.close()
print("done")
