"""Fail-closed atomic writer for opt-in Gemma4 Forward diagnostics."""
import json
import os
from pathlib import Path
import torch

def save_gemma4_capture(record, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError(f"refusing to overwrite Gemma4 capture: {target}")
    temp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    if temp.exists():
        raise RuntimeError(f"capture temporary path already exists: {temp}")
    try:
        if target.suffix == ".manifest":
            with temp.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            torch.save(record, temp)
        os.link(temp, target)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
