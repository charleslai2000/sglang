#!/usr/bin/env python3
"""Report actual scheduler instrumentation for one unique request RID."""
import json,sys
from pathlib import Path
log=Path(sys.argv[1]).read_text(errors='replace').splitlines();rid=sys.argv[2]
hits=[line for line in log if 'SGLANG_STEP_BIND' in line and rid in line]
if len(hits)!=1:
 print(json.dumps({'status':'FAIL','rid':rid,'matching_scheduler_step_records':len(hits),'records':hits}));raise SystemExit(2)
print(json.dumps({'status':'OK','rid':rid,'scheduler_step_record':hits[0]}))
