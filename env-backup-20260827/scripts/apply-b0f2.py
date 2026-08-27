#!/usr/bin/env python3
"""Apply B0-F2 scheduler checkpoint-boundary split patch to schedule_policy.py.

Two exact, count-verified replacements:
  1. Extend the runtime_context import to pull in mamba_extra_buffer_enabled
     and mamba_checkpoint_grid (both confirmed to exist in runtime_context.py).
  2. Insert the last-chunk track-point split block between the `new_len = min(...)`
     line and the `req.set_extend_range(...)` line inside add_chunked_req ONLY
     (the `)` immediately preceding `truncated = ...` is unique to that function).
"""
import sys

PATH = "/sgl-workspace/sglang/python/sglang/srt/managers/schedule_policy.py"

with open(PATH, "r") as f:
    src = f.read()

# ---- Replacement 1: import ----
old_import = "from sglang.srt.runtime_context import get_disagg\n"
new_import = (
    "from sglang.srt.runtime_context import (\n"
    "    get_disagg,\n"
    "    mamba_checkpoint_grid,\n"
    "    mamba_extra_buffer_enabled,\n"
    ")\n"
)
assert src.count(old_import) == 1, f"import anchor count={src.count(old_import)} (expected 1)"
src = src.replace(old_import, new_import, 1)

# ---- Replacement 2: insertion block (unique to add_chunked_req) ----
old_body = (
    "        )\n"
    "        truncated = cand_extend_input_len > _rem_tokens\n"
    "        new_len = min(cand_extend_input_len, _rem_tokens)\n"
    "        req.set_extend_range(len(req.prefix_indices), len(req.prefix_indices) + new_len)\n"
)
new_body = (
    "        )\n"
    "        truncated = cand_extend_input_len > _rem_tokens\n"
    "        new_len = min(cand_extend_input_len, _rem_tokens)\n"
    "        # B0-F2: last-chunk track-point split. When the scheduled extend would\n"
    "        # overshoot the last mamba track point inside it, cut once at that point:\n"
    "        # the checkpoint chunk ends on a canonical FP32 track write (committed via\n"
    "        # the stash next iteration), the leftover tail (< track_interval) runs as\n"
    "        # the next chunk. Only fires for the final (non-truncated) chunk; the\n"
    "        # 2048-aligned middle chunks always end on the track grid and are untouched.\n"
    "        if not truncated and mamba_extra_buffer_enabled():\n"
    "            base = len(req.prefix_indices)\n"
    "            grid = mamba_checkpoint_grid(self.tree_cache.page_size)\n"
    "            last_track = base + (new_len // grid) * grid\n"
    "            if last_track > base and last_track < base + new_len:\n"
    "                new_len = last_track - base\n"
    "                truncated = True  # the tail becomes the next chunk (one extra forward)\n"
    "        req.set_extend_range(len(req.prefix_indices), len(req.prefix_indices) + new_len)\n"
)
assert src.count(old_body) == 1, f"body anchor count={src.count(old_body)} (expected 1)"
src = src.replace(old_body, new_body, 1)

with open(PATH, "w") as f:
    f.write(src)

print("PATCH_APPLIED_OK")
print("import count now:", src.count("mamba_checkpoint_grid"))
print("block count now:", src.count("B0-F2: last-chunk track-point split"))
