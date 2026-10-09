#!/usr/bin/env python3
"""P2-IO batch-size composition microbenchmark (throwaway, not committed).

Decompose the engine-side per-batch cost of the restore read path into
    F = per-batch fixed overhead (shrinks with fewer, bigger batches)
    L = per-page linear engine work (invariant to batch size)
at N in {128, 512, 1024}, using the real read-path components:

  A. get_dummy_flat_data_page   -- pinned torch.zeros, ~32KiB, x N
     (controller `_generic_page_get` allocates one dummy page per key)
  B. ExtentFileBackend.batch_get -- real temp extent file, N keys
  C. set_from_flat_data_page     -- N x 32KiB pinned->pinned copy

T_batch(N) = F + N*L, fit from the three points.  A' (3090) measured
44ms/batch at N=128; the question is how much of it is F (fixed, fixable
by the 128->1024 batch-size change) vs N*L (linear, invariant).

Projection for a full chain of P pages:
  T_total(N) = P*L + (P/N)*F + device_time(P)
"""
import os
import shutil
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "python"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "test"))

import torch  # noqa: E402

from sglang.srt.mem_cache.hicache_storage import (  # noqa: E402
    HiCacheStorageConfig,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (  # noqa: E402
    ExtentFileBackend,
)

PAGE_BYTES = 32 * 1024  # ~31KiB measured on 3090 (qwen3.5-9b-gptq)
DTYPE = torch.bfloat16
ELEMS = PAGE_BYTES // 2  # bf16: 16384 elems = 32KiB
KEYS_FMT = "{:064x}"


def make_backend(tmpdir: str) -> ExtentFileBackend:
    cfg = dict(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name="benchmodel",
    )
    return ExtentFileBackend(
        HiCacheStorageConfig(
            **cfg,
            extra_config={
                "storage_dir": tmpdir,
                "extent_size": "64Mi",
                "file_size": "256Mi",
            },
        )
    )


def bench_dummy_alloc(n: int, reps: int) -> float:
    """A: one pinned torch.zeros dummy page per key (controller per-batch)."""
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        for _ in range(n):
            torch.zeros((ELEMS,), dtype=DTYPE, pin_memory=True)
        times.append(time.perf_counter() - t0)
    return statistics.median(times) / n  # per-page seconds


def bench_backend_batch_get(backend: ExtentFileBackend, n: int, reps: int) -> float:
    """B: real ExtentFileBackend.batch_get for n keys (backend per-batch)."""
    keys = [KEYS_FMT.format(i) for i in range(n)]
    values = [bytearray(PAGE_BYTES) for _ in range(n)]
    assert backend.batch_set(keys, values), "seed write failed"
    times = []
    for _ in range(reps):
        targets = [bytearray(PAGE_BYTES) for _ in range(n)]
        t0 = time.perf_counter()
        out = backend.batch_get(keys, targets)
        times.append(time.perf_counter() - t0)
        assert all(o is not None for o in out), "batch_get returned misses"
    return statistics.median(times)  # per-batch seconds


def bench_pool_copy(n: int, reps: int) -> float:
    """C: set_from_flat_data_page-style pinned->pinned copy, N pages."""
    src = torch.zeros((ELEMS,), dtype=DTYPE, pin_memory=True)
    pool = torch.zeros((n, ELEMS), dtype=DTYPE, pin_memory=True)
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        for i in range(n):
            pool[i].copy_(src)
        times.append(time.perf_counter() - t0)
    return statistics.median(times) / n  # per-page seconds


def main() -> int:
    ns = (128, 512, 1024)
    reps = 5
    results = {}
    with tempfile.TemporaryDirectory(prefix="p2io-bench-") as tmp:
        backend = make_backend(tmp)
        try:
            for n in ns:
                a = bench_dummy_alloc(n, reps)
                b = bench_backend_batch_get(backend, n, reps)
                c = bench_pool_copy(n, reps)
                results[n] = (a, b, c)
                print(
                    f"N={n:5d}  A(dummy alloc)={a*1e6:8.1f}us/page "
                    f"B(batch_get)={b*1e3:8.2f}ms/batch "
                    f"C(pool copy)={c*1e6:8.1f}us/page"
                )
        finally:
            backend.close()

    # Fit T_batch(N) = F + N*L over A+B+C (per-batch seconds).
    xs = [float(n) for n in ns]
    ys = [
        results[n][0] * n + results[n][1] + results[n][2] * n for n in ns
    ]
    # Least squares: L = cov(x,y)/var(x), F = mean(y) - L*mean(x)
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    L = num / den
    F = my - L * mx
    print(f"\nfit: F (per-batch fixed) = {F*1e3:.2f} ms/batch, "
          f"L (per-page linear) = {L*1e6:.1f} us/page")
    print(f"at N=128: F = {F*1e3:.2f}ms, N*L = {128*L*1e3:.2f}ms "
          f"({100*F/(F+128*L):.0f}% fixed)")

    # Projection for the A' full chain: 20,864 tokens/page_size... use the
    # measured batch counts instead: 175 batches at 128 = 22,400 pages.
    pages = 175 * 128
    device = 0.516  # A' measured device time, 3090, seconds
    for n in (128, 512, 1024):
        total = pages * L + (pages / n) * F + device
        print(f"projected T_total(N={n:5d}) = {total:.2f}s "
              f"(fixed part {(pages/n)*F:.2f}s + linear {pages*L:.2f}s "
              f"+ device {device:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
