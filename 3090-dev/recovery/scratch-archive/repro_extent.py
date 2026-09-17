import sys, os, shutil, time, struct, tempfile, traceback

TREE = sys.argv[1]
FIX = "--fix" in sys.argv
AUTO = "--auto" in sys.argv     # v1.1: rely on the automatic checkpoint worker
PHASE = sys.argv[2]
DIR = sys.argv[3]

sys.path.insert(0, TREE)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.storage.extent import extent_metadata as M

if FIX:
    # Faithful simulation of the proposed minimal fix: the post-rotation
    # sequence (set from state.checkpoint_lsn + 1 by checkpoint()) must not be
    # dragged backwards by _open_active_wal()'s stale recovery watermark.
    _orig_open = ExtentFileBackend._open_active_wal
    def _patched_open(self):
        authoritative = self._wal_next_seq
        _orig_open(self)
        if self._wal_next_seq < authoritative:
            self._wal_next_seq = authoritative
            self._wal_recovered_next_seq = authoritative
    ExtentFileBackend._open_active_wal = _patched_open


def cfg(d, threshold=None):
    extra = {"storage_dir": d, "extent_size": "16Ki", "file_size": "64Ki"}
    if threshold is not None:
        extra["wal_checkpoint_bytes"] = threshold
    return HiCacheStorageConfig(
        extra_config=extra, tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True,
        model_name="testmodel",
    )

def page(i, n=1000):
    return bytearray(bytes([i % 251]) * n)

def dump(d, tag):
    man = os.path.join(d, "hicache.meta.manifest")
    if os.path.exists(man):
        st = M.read_manifest(man)
        print(f"  [{tag}] manifest checkpoint_lsn={st.checkpoint_lsn} "
              f"wal_floor={st.wal_floor} wal_active_gen={st.wal_active_gen} "
              f"next_slot={st.next_slot} entries={len(st.entries)}")
    cur = os.path.join(d, "hicache.meta.wal.current")
    if os.path.exists(cur):
        print(f"  [{tag}] current generation={M.read_current(cur)}")
    for name in sorted(os.listdir(d)):
        if ".wal." in name and name.endswith(tuple("0123456789")):
            p = os.path.join(d, name)
            gen = int(name.rsplit(".", 1)[1])
            raw = open(p, "rb").read()
            hdr = M.deserialize_segment_header(raw[:M.SEGMENT_HEADER_SIZE])
            try:
                frames = M.iter_segment_frames(p, active=False)
                seqs = [f.seq for f in frames]
                print(f"  [{tag}] {name} size={len(raw)} header_gen={hdr.segment_generation} "
                      f"header_base_lsn={hdr.base_lsn} frames={len(seqs)} "
                      f"first_seq={seqs[0] if seqs else None} last_seq={seqs[-1] if seqs else None}")
            except Exception as e:
                print(f"  [{tag}] {name} size={len(raw)} header_gen={hdr.segment_generation} "
                      f"header_base_lsn={hdr.base_lsn} FRAME_SCAN_FAIL={e}")

if PHASE == "write":
    if os.path.isdir(DIR):
        shutil.rmtree(DIR)
    os.makedirs(DIR)
    be = ExtentFileBackend(cfg(DIR, 1 if AUTO else None))
    print("OPEN ok; wal_next_seq=%d recovered_next_seq=%s" % (
        be._wal_next_seq, getattr(be, "_wal_recovered_next_seq", None)))
    be.batch_set([f"a{i}" for i in range(4)], [page(i) for i in range(4)])
    print("after writes#1: wal_next_seq=%d recovered_next_seq=%s" % (
        be._wal_next_seq, getattr(be, "_wal_recovered_next_seq", None)))
    if AUTO:
        t = time.time() + 3
        while be.stats_snapshot()["wal_checkpoint_successes"] < 1 and time.time() < t:
            time.sleep(0.05)
        print("auto checkpoint_successes=%d" % be.stats_snapshot()["wal_checkpoint_successes"])
    else:
        if FIX:
            # simulate the minimal one-line diff: checkpoint() must re-seed the
            # recovery watermark with the authoritative post-rotation lsn
            # (state.checkpoint_lsn + 1 == self._wal_next_seq at that point)
            be._wal_recovered_next_seq = be._wal_next_seq
        be.checkpoint()
        print("manual checkpoint done: wal_next_seq=%d recovered_next_seq=%s" % (
            be._wal_next_seq, be._wal_recovered_next_seq))
    be.batch_set([f"b{i}" for i in range(4)], [page(100 + i) for i in range(4)])
    print("after writes#2: wal_next_seq=%d recovered_next_seq=%s" % (
        be._wal_next_seq, be._wal_recovered_next_seq))
    dump(DIR, "after-crash")
    sys.stdout.flush()
    os._exit(9)     # abrupt kill: no close(), no shutdown checkpoint
else:
    dump(DIR, "before-recover")
    try:
        be = ExtentFileBackend(cfg(DIR, 1 if AUTO else None))
        got = be.batch_get([f"a{i}" for i in range(4)] + [f"b{i}" for i in range(4)])
        print("RECOVER OK: present=%s" % [g is not None for g in got])
        sys.stdout.flush()
        os._exit(0)
    except Exception as e:
        print("RECOVER FAILED: %s.%s: %s" % (type(e).__module__, type(e).__name__, e))
        sys.stdout.flush()
        os._exit(1)
