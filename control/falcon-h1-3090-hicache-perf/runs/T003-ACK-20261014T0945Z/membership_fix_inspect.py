#!/usr/bin/env python3
"""Read-only attach to the local T003 scheduler to inspect actual target ownership."""
import json, os, torch
from pathlib import Path
from sglang.srt.utils.common import get_bool_env_var
import torch.multiprocessing.reductions as reductions
import zmq
from sglang.srt.managers.scheduler import Scheduler

pid=int(os.environ['T003_SCHEDULER_PID'])
ctx=zmq.Context.instance()
sock=ctx.socket(zmq.REQ)
sock.connect(f"ipc:///tmp/sglang_scheduler_{pid}.ipc")
sock.send_pyobj({"cmd":"get_hicache_target_snapshot", "node_id":26, "session_id":"falcon-t003-target-radix-session-9014"})
result=sock.recv_pyobj()
print(json.dumps(result, default=str))

if hasattr(cache,'inner'): cache=cache.inner
rows=[json.loads(x) for x in Path(os.environ['T003_PROBE']).read_text().splitlines() if x.strip()]
build=next(e for e in rows if e.get('evt')=='build_complete' and e.get('session_id')=='falcon-t003-target-radix-session-9014')
node=cache.tree_core.node_by_id(int(build['node_id']))
print(json.dumps({
 'node_id':node.id,'hash':node.get_last_hash_value(),
 'pending':node.write_through_pending_id,'evicted':node.evicted,'backuped':node.backuped,
 'device':{str(ct):node.component_data[ct].value is not None for ct in node.component_types},
 'host':{str(ct):node.component_data[ct].host_value is not None for ct in node.component_types},
 'lock':{str(ct):node.component_data[ct].lock_ref for ct in node.component_types},
 'host_lock':{str(ct):node.component_data[ct].host_lock_ref for ct in node.component_types},
 'component_session_ref':{str(ct):node.component_data[ct].session_ref for ct in node.component_types},
 'component_session_ids':{str(ct):sorted(node.component_data[ct].session_ids or ()) for ct in node.component_types},
 'node_session_ref':node.session_ref,'node_session_ids':sorted(node.session_ids or ()),
 'parent':node.parent.id if node.parent else None,'children':[c.id for c in node.children.values()],
 'host_leaf_expected':cache.tree_core._is_host_leaf(node),'host_leaf_indexed':node in cache.tree_core.evictable_host_leaves,
 'full_lru':cache.tree_core.lru_lists[next(ct for ct in node.component_types if str(ct)=='FULL')].in_list(node),
 'mamba_host_lru':cache.tree_core.host_lru_lists[next(ct for ct in node.component_types if str(ct)=='MAMBA')].in_list(node),
},default=str))
