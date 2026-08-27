F="/sgl-workspace/sglang/python/sglang/srt/mem_cache/unified_radix_cache.py"
s=open(F).read()
import re
lines=s.split("\n")
print("=== lines 37-60 (after imports) ===")
for i in range(36,60):
    print(i+1, repr(lines[i]))
print("=== exact unfinished insert anchor (8-space) ===")
a="        result = self.insert(insert_params)\n\n        # Match prefix"
print("count:", s.count(a))
print("=== exact finished insert anchor (12-space) ===")
b="            result = self.insert(insert_params)\n\n            # Free unaligned tail (+ deferred truncation tail)"
print("count:", s.count(b))
print("=== count 'result = self.insert(insert_params)' total ===", s.count("result = self.insert(insert_params)"))
print("=== logger def ===")
for i,l in enumerate(lines):
    if "logger" in l and ("=" in l) and i<60:
        print(i+1, repr(l))
