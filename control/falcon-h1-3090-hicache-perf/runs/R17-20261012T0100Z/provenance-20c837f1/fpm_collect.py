#!/home/ubuntu/venvs/sglang-3090/bin/python
"""Consume the existing SGLang scheduler ForwardPassMetrics ZMQ PUB; no new instrumentation."""
import argparse,json,time
from pathlib import Path
import msgspec,zmq
from sglang.srt.observability.forward_pass_metrics import ForwardPassMetrics
p=argparse.ArgumentParser();p.add_argument('--endpoint',required=True);p.add_argument('--duration',type=float,default=600);p.add_argument('--out',required=True);a=p.parse_args()
ctx=zmq.Context();s=ctx.socket(zmq.SUB);s.setsockopt(zmq.SUBSCRIBE,b'');s.setsockopt(zmq.RCVHWM,100000);s.connect(a.endpoint)
dec=msgspec.msgpack.Decoder(ForwardPassMetrics);poll=zmq.Poller();poll.register(s,zmq.POLLIN);end=time.monotonic()+a.duration;rows=[]
while time.monotonic()<end:
 ev=dict(poll.poll(200))
 if s not in ev:continue
 parts=s.recv_multipart()
 if len(parts)!=3:continue
 topic,seq,payload=parts
 try:m=dec.decode(payload)
 except Exception:continue
 rows.append({'recv_monotonic_ns':time.monotonic_ns(),'seq':int.from_bytes(seq,'big'),'version':m.version,'worker_id':m.worker_id,'dp_rank':m.dp_rank,'counter_id':m.counter_id,'gpu_forward_s':m.wall_time,'prefill':{'requests':m.scheduled_requests.num_prefill_requests,'tokens':m.scheduled_requests.sum_prefill_tokens,'prefix_kv_tokens':m.scheduled_requests.sum_prefill_kv_tokens},'decode':{'requests':m.scheduled_requests.num_decode_requests,'kv_tokens':m.scheduled_requests.sum_decode_kv_tokens},'queued':{'prefill_requests':m.queued_requests.num_prefill_requests,'prefill_tokens':m.queued_requests.sum_prefill_tokens,'decode_requests':m.queued_requests.num_decode_requests,'decode_kv_tokens':m.queued_requests.sum_decode_kv_tokens}})
Path(a.out).write_text(json.dumps({'endpoint':a.endpoint,'start_wall_ns':time.time_ns(),'messages':len(rows),'records':rows},indent=2));print(json.dumps({'messages':len(rows),'out':a.out}))
s.close(0);ctx.term()
