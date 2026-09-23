"""e24 deterministic repro: multi-batch v1 write -> v2 query.

Reproduces the live e7m defect: node29 wrote 2048 KV pages (2 x 1024
STORAGE_BATCH_SIZE batches), but the read-side batch_exists_v2 finds only
1024 pages present, and the MAMBA TRAILING_PAGES sidecar then clamps the
shared final_pages to 0 -> storage_hit=0 despite the KV chain being written.

Plays the engine _page_backup loop exactly (batches of STORAGE_BATCH_SIZE,
v1 zero-copy write), then the hybrid _storage_hit_query path (batch_exists_v2
with a MAMBA sidecar).
"""
import os
import sys
import tempfile

REPO = "/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache"
sys.path.insert(0, os.path.join(REPO, "python"))
sys.path.insert(0, os.path.join(REPO, "test"))

from sglang.srt.mem_cache.hicache_storage import (
    PoolName,
    PoolTransfer,
    PoolHitPolicy,
)


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "teb",
        os.path.join(
            REPO,
            "test/registered/unit/mem_cache/test_extent_file_backend_unit.py",
        ),
    )
    teb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(teb)

    tmpdir = tempfile.mkdtemp(prefix="e24_repro_")
    backend = teb.ExtentFileBackend(
        teb._make_config(
            model_name="qwen3.5-9b-gptq",
            extra_config={
                "storage_dir": tmpdir,
                "extent_size": "16Ki",
                "file_size": "256Ki",
            },
        )
    )
    kv = teb._PagePool(3000)
    mamba = teb._PagePool(3000)
    backend.register_mem_host_pool_v2(kv, PoolName.KV)
    backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

    page_size = 1
    n_pages = 2048
    keys = ["k%06d" % i for i in range(n_pages)]

    # --- write side: engine _page_backup loop, STORAGE_BATCH_SIZE batches ---
    STORAGE_BATCH_SIZE = 1024
    host_indices = list(range(n_pages))
    for i in range(0, n_pages, STORAGE_BATCH_SIZE):
        batch_hashes = keys[i : i + STORAGE_BATCH_SIZE]
        batch_host_indices = host_indices[i : i + len(batch_hashes)]
        ok = backend.batch_set_v1(batch_hashes, batch_host_indices, None)
        assert all(ok), f"batch {i} failed"

    print("wrote", n_pages, "pages in", n_pages // STORAGE_BATCH_SIZE, "batches")

    # --- read side: batch_exists_v2 with MAMBA TRAILING_PAGES sidecar ---
    # mirror of the live PREFETCH: keys=["__placeholder__"] (len 1 -> trailing 1)
    mamba_transfer = PoolTransfer(
        name=PoolName.MAMBA,
        host_indices=None,
        keys=["__placeholder__"],
        hit_policy=PoolHitPolicy.TRAILING_PAGES,
    )
    result = backend.batch_exists_v2(keys, [mamba_transfer])
    print("kv_hit_pages:", result.kv_hit_pages)
    print("extra_pool_hit_pages:", {
        getattr(k, "value", k): v for k, v in result.extra_pool_hit_pages.items()
    })
    print("EXPECT (no sidecar) kv_hit_pages:",
          backend.batch_exists_v2(keys, []).kv_hit_pages)

    backend.close()


if __name__ == "__main__":
    main()
