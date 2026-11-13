"""Run-scoped W4A16-only import override for the undefined BF16 attention experiment.

The clean HEAD^ Triton attention module is used without changing the repository
worktree or any installed package. Runtime-only via sitecustomize in this run.
"""

import importlib.abc
import importlib.util
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
MODULE = "sglang.kernels.ops.attention.extend_attention"
SOURCE = (
    ROOT
    / "control/gemma4-w4a16-3090-performance-capacity/runs/overlay_extend_attention.py"
)
EXPECTED_SHA256 = "69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e"


class _W4A16AttentionFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != MODULE:
            return None
        import hashlib

        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        if digest != EXPECTED_SHA256:
            raise ImportError(f"W4A16 clean attention overlay hash mismatch: {digest}")
        return importlib.util.spec_from_file_location(fullname, SOURCE)


sys.meta_path.insert(0, _W4A16AttentionFinder())
