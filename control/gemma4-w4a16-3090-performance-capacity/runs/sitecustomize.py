# Install only the run-scoped W4A16 attention import override.
import importlib.util
from pathlib import Path

_root = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
_spec = importlib.util.spec_from_file_location(
    "w4a16_runtime_override",
    _root / "control/gemma4-w4a16-3090-performance-capacity/runs/runtime_override.py",
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
