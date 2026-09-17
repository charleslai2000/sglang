import importlib.util, json, os, struct, sys, time
sys.argv=["x"]
m0 = importlib.import_module("repro_wal_discontinuity")
m = m0.load_metadata_module()
p = m.segment_path("/tmp/opencode/l3-reclaim-20260916/scratch-fleet", m0.SUFFIX, 7)
data = open(p,"rb").read()
mv = memoryview(data)
FB = m.FRAME_HEADER_SIZE
off = m.SEGMENT_HEADER_SIZE
n=0; first_seq=None; last_seq=None; seqs_monotonic=True; prev=None
t0=time.time()
while off < len(mv):
    rem = mv[off:]
    if len(rem) < FB: break
    payload_len = struct.unpack_from("<I", rem, 10)[0]
    total = FB + payload_len
    if len(rem) < total: break
    ft, seq, payload, consumed = m.decode_frame(bytes(mv[off:off+total]), wal_max_record_bytes=m.DEFAULT_WAL_MAX_RECORD_BYTES)
    assert consumed == total, (consumed, total)
    if first_seq is None: first_seq=seq
    if prev is not None and seq != prev+1: seqs_monotonic=False; print("discontinuity at frame",n,"prev",prev,"got",seq); break
    prev=seq; last_seq=seq; n+=1; off+=consumed
print(json.dumps({"file":p,"size":len(data),"frames":n,"wasted_s":round(time.time()-t0,2),
  "segment_header_size":m.SEGMENT_HEADER_SIZE,"frame_header_size":FB,
  "first_seq":first_seq,"last_seq":last_seq,"seqs_monotonic_within_segment":seqs_monotonic,
  "tail_offset":off,"tail_bytes":len(data)-off}, indent=2))
