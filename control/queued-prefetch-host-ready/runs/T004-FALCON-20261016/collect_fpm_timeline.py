#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Capture FPM PUB metrics and a run-scoped readiness handshake."""
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path
import msgspec, zmq
from sglang.srt.observability.forward_pass_metrics import ForwardPassMetrics
p=argparse.ArgumentParser(); p.add_argument('--endpoint',required=True); p.add_argument('--output',required=True); p.add_argument('--stop',required=True); a=p.parse_args()
ctx=zmq.Context(); sub=ctx.socket(zmq.SUB); sub.setsockopt(zmq.SUBSCRIBE,b''); sub.setsockopt(zmq.RCVHWM,200000); sub.connect(a.endpoint)
poll=zmq.Poller(); poll.register(sub,zmq.POLLIN); dec=msgspec.msgpack.Decoder(ForwardPassMetrics)
out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
identity={'head':os.environ.get('T004_FPM_SOURCE_HEAD'),'binary_sha256':os.environ.get('T004_FPM_BINARY_SHA256'),'endpoint':a.endpoint,'collector_pid':os.getpid()}
with out.open('a') as f:
 f.write(json.dumps({'schema':'t004_fpm_identity.v1','identity':identity,'utc_epoch_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns()},separators=(',',':'))+'\n'); f.flush()
 last_seq=None
 while not Path(a.stop).exists():
  ready=dict(poll.poll(50))
  if sub not in ready: continue
  before=time.monotonic_ns(); parts=sub.recv_multipart(); after=time.monotonic_ns()
  if len(parts)!=3: continue
  m=dec.decode(parts[2]); seq=int.from_bytes(parts[1],'big')
  if last_seq is not None and seq > last_seq + 1:
   f.write(json.dumps({'schema':'t004_fpm_seq_gap.v1','first_missing_seq':last_seq+1,'last_missing_seq':seq-1,'missing_count':seq-last_seq-1,'next_seq':seq,'recv_mono_ns':after},separators=(',',':'))+'\n'); f.flush()
  last_seq=seq
  if m.worker_id == 'collector-readiness-probe':
   f.write(json.dumps({'schema':'t004_fpm_ready_ack.v1','counter_id':m.counter_id,'seq':seq,'recv_mono_ns':after},separators=(',',':'))+'\n'); f.flush(); continue
  if not m.scheduled_requests.num_prefill_requests and not m.scheduled_requests.num_decode_requests: continue
  row={'schema':'t004_fpm.v1','recv_mono_before_ns':before,'recv_mono_after_ns':after,'seq':seq,'counter_id':m.counter_id,'iteration_id':m.iteration_id,'worker_id':m.worker_id,'dp_rank':m.dp_rank,'wall_time_s':m.wall_time,'prefill_requests':m.scheduled_requests.num_prefill_requests,'prefill_tokens':m.scheduled_requests.sum_prefill_tokens,'prefill_kv_tokens':m.scheduled_requests.sum_prefill_kv_tokens,'decode_requests':m.scheduled_requests.num_decode_requests,'decode_kv_tokens':m.scheduled_requests.sum_decode_kv_tokens}
  f.write(json.dumps(row,separators=(',',':'))+'\n'); f.flush()
ctx.destroy(linger=0)
