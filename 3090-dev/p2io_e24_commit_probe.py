"""e24 commit self-probe (coordinator's 10-line invariant).

reserve 8 pages -> write 8 -> commit 8 keys
immediate same-thread: 8/8 HIT
wait 100ms: 8/8 HIT
another thread: 8/8 HIT
advance unrelated write: 8/8 HIT
open new extent: 8/8 HIT
recycle that extent: 8/8 MISS (the only expected invalidation)

Failure->rootcause:
  miss right after commit -> commit/index bug
  miss after unrelated write -> generation bug
  miss after new extent -> generation/extent-epoch bug
  miss only in another thread -> instance/threading bug
  miss after recycle -> normal
"""
import os
import sys
import tempfile
import threading
import time

REPO = "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache"
sys.path.insert(0, os.path.join(REPO, "python"))
sys.path.insert(0, os.path.join(REPO, "test"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "teb", os.path.join(REPO, "test/registered/unit/mem_cache/test_extent_file_backend_unit.py"),
)
teb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(teb)

from sglang.srt.mem_cache.hicache_storage import (
    PoolName, PoolTransfer, PoolHitPolicy,
)

tmpdir = tempfile.mkdtemp(prefix="e24_probe_")
backend = teb.ExtentFileBackend(
    teb._make_config(
        extra_config={"storage_dir": tmpdir, "extent_size": "16Ki", "file_size": "256Ki"},
    )
)
kv = teb._PagePool(1000, slots=4096)
mamba = teb._PagePool(1000, slots=4096)
backend.register_mem_host_pool_v2(kv, PoolName.KV)
backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

keys = ["k%05d" % i for i in range(8)]
values = [bytearray(b"v" * 500) for _ in keys]

# 1. write + commit 8
ok = backend.batch_set(keys, values)
assert ok, ok
print("1. immediate same-thread:", backend.batch_exists(keys))

# 2. wait 100ms
time.sleep(0.1)
print("2. after 100ms:", backend.batch_exists(keys))

# 3. another thread
def check_thread():
    global cross_thread
    cross_thread = backend.batch_exists(keys)
cross_thread = None
t = threading.Thread(target=check_thread)
t.start(); t.join()
print("3. another thread:", cross_thread)

# 4. advance unrelated write (fills more slots, but no recycle)
for i in range(8, 40):
    backend.batch_set(["u%05d" % i], [bytearray(b"u" * 500)])
print("4. after unrelated writes:", backend.batch_exists(keys))

# 5. new extent: write many pages to fill to a new extent
for i in range(40, 220):
    backend.batch_set(["n%05d" % i], [bytearray(b"n" * 500)])
print("5. after new-extent fill:", backend.batch_exists(keys))

# 6. recycle: force watermark GC to evict. Set max_size low so _gc_evict drops slots.
# Our keys are the OLDEST (recency order). Set max_size to trigger eviction.
backend._max_size_bytes = 1024  # tiny -> every write triggers GC
for i in range(220, 300):
    backend.batch_set(["r%05d" % i], [bytearray(b"r" * 500)])
print("6. after GC eviction (recycle):", backend.batch_exists(keys))
print("   allocator generations:", backend._allocator._generations[:6])
print("   index size:", len(backend._allocator._index))

backend.close()
