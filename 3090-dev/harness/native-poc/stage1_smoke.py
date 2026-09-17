#!/usr/bin/env python3
"""Stage 1 smoke: build/import the PoC extension into the frozen v1.1 python.

Reads:  /tmp/opencode/l3-native-poc-20260916/src/rust (independent worktree).
Writes: the rust_extensions cache under SGLANG_CACHE_DIR (scratch); nothing
        under /opt or the repo tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WORKTREE = Path("/tmp/opencode/l3-native-poc-20260916")
sys.path.insert(0, "/opt/sglang/local-prod-v1.1-candidate/src/python")

import sglang  # noqa: E402

assert sglang.__file__.startswith("/opt/sglang/local-prod-v1.1-candidate/src/python/"), (
    "identity landmine: sglang resolved to the stale workspace copy: "
    f"{sglang.__file__}"
)
print("sglang.__file__ =", sglang.__file__)

from sglang.srt.rust_extensions.loader import load_rust_extension  # noqa: E402

module = load_rust_extension(
    "sglang.srt.rust_extensions._l3poc",
    mode="force",
    workspace=WORKTREE / "src" / "rust",
)

print("module.__file__      =", getattr(module, "__file__", None))
print("module.__spec__.name =", module.__spec__.name)
print("module.__name__      =", module.__name__)
print("dir(module)          =", sorted(n for n in dir(module) if not n.startswith("__")))

assert module.FRAME_MAGIC == 0x484D3146
assert module.FORMAT_VERSION == 1
assert module.FRAME_HEADER_SIZE == 26
assert module.FRAME_SET == 1 and module.FRAME_BATCH_COMMIT == 2 and module.FRAME_GROUP_COMMIT == 3

# crc32c known vector.
assert module.crc32c(b"123456789") == 0xE3069283, hex(module.crc32c(b"123456789"))
print("crc32c(b'123456789') = 0x%08X" % module.crc32c(b"123456789"))

frame = module.encode_frame(1, 7, b"abc")
print("encode_frame(1,7,b'abc') =", frame.hex(), "len", len(frame))

print("STAGE1_SMOKE_OK")
