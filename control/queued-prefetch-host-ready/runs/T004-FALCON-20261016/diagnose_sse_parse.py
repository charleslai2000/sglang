#!/usr/bin/env python3
"""Identify SSE data records that the capture client attempts to JSON-decode."""
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
    if line.startswith("data:"):
        raw = line[5:].strip()
        if raw == "[DONE]":
            continue
        try:
            item = json.loads(raw)
            info = item.get("meta_info") or {}
            print(i, "OK", len(item.get("output_ids") or []), info.get("completion_tokens"), info.get("id"))
        except json.JSONDecodeError as exc:
            print(i, "BAD", len(raw), repr(exc), repr(raw[:160]), repr(raw[-160:]))
