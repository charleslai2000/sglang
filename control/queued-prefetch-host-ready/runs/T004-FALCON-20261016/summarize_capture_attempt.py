#!/usr/bin/env python3
"""Summarize per-RID stream rows from one T004 driver stdout, tolerating truncation."""
import json
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    if not line.startswith("STREAM "):
        continue
    payload = line[7:]
    decoder = json.JSONDecoder()
    try:
        row, end = decoder.raw_decode(payload)
        if payload[end:].strip():
            print("TRAILING_DATA", row.get("tag"), payload[end:1200])
        meta = row.get("meta") or {}
        print(row.get("tag"), row.get("rid"), len(row.get("output_ids") or []),
              meta.get("completion_tokens"), meta.get("finish_reason"),
              meta.get("e2e_latency"))
    except json.JSONDecodeError as exc:
        print("INVALID_STREAM_ROW", payload[:300], repr(exc))
