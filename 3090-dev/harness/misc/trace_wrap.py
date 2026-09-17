"""Trace the existing circular-wrap test to see which slots are passed."""
import os
import shutil
import tempfile

from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend


def make_config(extra_config=None, **overrides):
    cfg = dict(
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True,
        model_name="testmodel",
    )
    cfg.update(overrides)
    return HiCacheStorageConfig(extra_config=extra_config, **cfg)


def page(i, n=1000):
    return bytearray(bytes([i % 251]) * n)


def main():
    tmp = tempfile.mkdtemp(prefix="trace_wrap_")
    backend = ExtentFileBackend(
        make_config(extra_config={
            "storage_dir": tmp, "extent_size": "16Ki", "file_size": "64Ki",
        })
    )
    try:
        orig = backend._allocator.plan_split

        def traced(key_lengths, pending_drops=None):
            refs, passed, drops = orig(key_lengths, pending_drops)
            print("  plan n=%d passed=%s drops=%s place=%s" % (
                len(key_lengths), passed, drops,
                [(r.extent_id, r.offset) for r in refs if r is not None],
            ))
            return refs, passed, drops

        backend._allocator.plan_split = traced
        for start in range(0, 80, 20):
            keys = ["k%04d" % i for i in range(start, start + 20)]
            values = [page(i) for i in range(start, start + 20)]
            print("batch start=%d" % start)
            ok = backend.batch_set(keys, values)
            print("  ok=%s used=%d cursors=%s next=%d" % (
                ok, backend._allocator.used_bytes,
                backend._allocator._cursors, backend._allocator._next_slot,
            ))
            print("  slot_keys=%s" % [
                (s, sorted(k for k in ks)) for s, ks in enumerate(backend._allocator._slot_keys) if ks
            ])
        for k in ("k0000", "k0016", "k0064"):
            print("exists", k, backend.exists(k))
        print("used", backend._allocator.used_bytes)
    finally:
        backend.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
