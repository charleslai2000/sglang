#!/usr/bin/env python3
"""Join one run's scheduler RID/step, FPM and Nsight runtime/kernel evidence."""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

run = Path(sys.argv[1])
db = sqlite3.connect(run / "falcon.sqlite")
strings = dict(db.execute("select id,value from StringIds"))
fpm = [json.loads(x) for x in (run / "fpm.jsonl").read_text().splitlines() if x.strip()]
print("FPM rows", len([x for x in fpm if x.get('schema') == 't004_fpm.v1']))
print("Timeline rows", sum(1 for x in (run / "timeline.jsonl").read_text().splitlines() if x.strip()))
print("NVTX text examples", db.execute("select text,count(*) from NVTX_EVENTS where text is not null group by text order by count(*) desc limit 10").fetchall())
print("Nsight NVTX events", db.execute("select count(*) from NVTX_EVENTS").fetchone()[0])
print("Nsight kernel events", db.execute("select count(*) from CUPTI_ACTIVITY_KIND_KERNEL").fetchone()[0])
print("Nsight runtime events", db.execute("select count(*) from CUPTI_ACTIVITY_KIND_RUNTIME").fetchone()[0])
print("Kernel/runtime correlation join candidates", db.execute("select count(*) from CUPTI_ACTIVITY_KIND_KERNEL k join CUPTI_ACTIVITY_KIND_RUNTIME r on k.correlationId=r.correlationId").fetchone()[0])
print("Step NVTX markers", db.execute("select count(*) from NVTX_EVENTS where text like 'sglang.step;%'").fetchone()[0])
