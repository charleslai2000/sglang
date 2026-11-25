#!/usr/bin/env python3
"""Extract per-request HTTP attempt records and failures from driver stdout."""
import json, re, sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    if 'generate_http_attempt' in line:
        try:
            print(json.loads(line))
        except Exception:
            pass
    if line.startswith('STREAM '):
        try:
            r=json.loads(line[7:]); print('STREAM_OK',r['tag'],r['rid'],len(r['output_ids']),r['meta'].get('completion_tokens'))
        except Exception as e: print('STREAM_ROW_INVALID',str(e))
    if 'RuntimeError: {' in line: print('FAILURES',line.split('RuntimeError: ',1)[1])
