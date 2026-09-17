"""Pytest plugin: serve the *real* pre-fix extent_file_backend source text.

Used only to demonstrate the regression test fails on the unfixed code without
toggling the live candidate tree. The injected file is the exact pre-fix
content reconstructed from the applied diff.
"""
import importlib.util
import sys

_NAME = "sglang.srt.mem_cache.storage.extent.extent_file_backend"
_PATH = "/tmp/opencode/orig_extent_file_backend.py"
if _NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(_NAME, _PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = mod
    spec.loader.exec_module(mod)
    assert "sglang.srt.mem_cache.storage.extent" in sys.modules
