"""Optional CUDA 12.9 CUPTI User Range support for T002 profiling."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import threading
from pathlib import Path

_lock = threading.Lock()
_module = None


def _load():
    global _module
    if _module is None:
        with _lock:
            if _module is None:
                package_dir = Path(__file__).parent
                candidates = list(package_dir.glob("_cupti_range*.so"))
                if candidates:
                    native_path = candidates[0]
                    extension_name = "_cupti_range"
                else:
                    extension_name = "sglang.srt.utils.cupti_range._cupti_range"
                    spec = importlib.util.find_spec(extension_name)
                    if spec is None or spec.origin is None:
                        raise RuntimeError(
                            "T002 CUPTI extension missing; build it with "
                            "python -m sglang.srt.utils.cupti_range.build build_ext --inplace"
                        )
                    native_path = Path(spec.origin)
                spec = importlib.util.spec_from_file_location(extension_name, native_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"cannot load CUPTI extension: {native_path}")
                _module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_module)
                digest = hashlib.sha256(native_path.read_bytes()).hexdigest()
                print(
                    f"T002_CUPTI_NATIVE_LOADED path={native_path} sha256={digest}",
                    flush=True,
                )
                maps_path = Path(f"/proc/{os.getpid()}/maps")
                print(
                    "T002_CUPTI_NATIVE_MAPS\\n"
                    + "\\n".join(
                        line for line in maps_path.read_text().splitlines()
                        if any(token in line for token in (
                            "_cupti_range", "libcupti", "libnvperf", "libcudart", "libcuda"
                        ))
                    ),
                    flush=True,
                )
                os.environ["SGLANG_T002_CUPTI_NATIVE_PATH"] = str(native_path)
                os.environ["SGLANG_T002_CUPTI_NATIVE_SHA256"] = digest
    return _module


def enabled() -> bool:
    return os.environ.get("SGLANG_T002_CUPTI", "0") == "1"


def administrative_token() -> str:
    return os.environ.get("SGLANG_T002_CUPTI_TOKEN", "")


def enable() -> None:
    if enabled():
        module = _load()
        try:
            module.enable(True)
        except Exception as exc:
            print(f"T002_CUPTI_ENABLE_ERROR: {exc!r}", flush=True)
            raise


def arm_window() -> None:
    if enabled():
        _load().arm_window()


def begin(
    range_id: str,
    iteration_id: int,
    stage: str,
    batch: int,
    tokens: int,
    graph: str,
) -> None:
    if enabled():
        module = _load()
        try:
            module.begin(range_id, iteration_id, stage, batch, tokens, graph)
        except Exception as exc:
            print(f"T002_CUPTI_BEGIN_ERROR: {exc!r}", flush=True)
            raise


def end() -> None:
    if enabled():
        _load().end()


def disable() -> None:
    if _module is not None:
        _module.disable()


def end_active() -> None:
    _load().end()


def finalize():
    return _load().finalize()


def collect(scheduler, output_path: str, profile_forwards: int = 1000):
    if not enabled():
        raise RuntimeError("SGLANG_T002_CUPTI is not enabled")
    if not 1 <= profile_forwards <= 10000:
        raise ValueError("profile_forwards must be in [1, 10000]")
    module = _load()
    scheduler._t002_cupti_module = module
    scheduler._t002_cupti_remaining = profile_forwards
    scheduler._t002_cupti_output = Path(output_path)
    scheduler._t002_cupti_done = threading.Event()
    scheduler._t002_cupti_pending_finalize = False
    return scheduler._t002_cupti_done


def write_result(scheduler, result):
    output_path = Path(
        getattr(scheduler, "_t002_cupti_output", "/tmp/sglang-t002-cupti-ranges.json")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\\n")
    done = getattr(scheduler, "_t002_cupti_done", None)
    if done is not None:
        done.set()
