"""Shared strict loader for the PoC extension (frozen v1.1 identity enforced)."""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE = Path("/tmp/opencode/l3-native-poc-20260916")
FROZEN_SRC = "/opt/sglang/local-prod-v1.1-candidate/src/python"


def load_poc():
    if FROZEN_SRC not in sys.path:
        sys.path.insert(0, FROZEN_SRC)
    import sglang

    if not sglang.__file__.startswith(FROZEN_SRC + "/"):
        raise SystemExit(
            "identity landmine: sglang resolved outside frozen v1.1: "
            f"{sglang.__file__}"
        )
    from sglang.srt.rust_extensions.loader import load_rust_extension

    module = load_rust_extension(
        "sglang.srt.rust_extensions._l3poc",
        mode="force",
        workspace=WORKTREE / "src" / "rust",
    )
    assert module.__file__.startswith(str(WORKTREE)), module.__file__
    return module
