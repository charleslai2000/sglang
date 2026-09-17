#!/usr/bin/env python3
"""Stage 3: native zero-intermediate-gather-copy read of the real host-pool page
layout (CPU stand-in).

Uses the FROZEN v1.1 pool_host classes at exact production geometry
(see L3-STATIC-AUDIT-FINDINGS-20260916.md / E1):
  mamba page = 51,511,296 B  (size,24,1,32,128,128) fp32 + (size,24,1,8192,3) bf16
  kv    page = 16,384 B      (2,size,8,4,256) fp8_e4m3

The device pool is replaced by ordinary CPU buffers and `pin_memory=False`;
`cudaHostRegister` is NOT used (no CUDA context is created; CUDA_VISIBLE_DEVICES="").
That is an explicit limitation, not hidden.
"""

from __future__ import annotations

import ctypes
import gc
import json
import os
import statistics
import sys
import threading
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import FROZEN_SRC, load_poc  # noqa: E402

sys.path.insert(0, FROZEN_SRC)
import torch  # noqa: E402
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost  # noqa: E402
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost  # noqa: E402
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (  # noqa: E402
    _page_byte_view,
)

NUM_MAMBA_LAYERS = 24
TEMPORAL_SHAPE = (32, 128, 128)
CONV_SHAPE = (8192, 3)
KV_LAYER_NUM = 8
KV_HEAD_NUM = 4
KV_HEAD_DIM = 256
KV_DTYPE = torch.float8_e4m3fn
KV_BATCH = 1024
MAMBA_PAGE_BYTES = 51_511_296
KV_PAGE_BYTES = 16_384


class O:
    pass


def make_mamba():
    mc = O()
    mc.temporal = torch.zeros((NUM_MAMBA_LAYERS, 1) + TEMPORAL_SHAPE, dtype=torch.float32)
    mc.conv = [torch.zeros((NUM_MAMBA_LAYERS, 1) + CONV_SHAPE, dtype=torch.bfloat16)]
    dp = O()
    dp.num_mamba_layers = NUM_MAMBA_LAYERS
    dp.mamba_cache = mc
    dp.size = 2
    dp.device = "cpu"
    return MambaPoolHost(dp, 1.0, 0, pin_memory=False, device="cpu", layout="page_first")


def make_kv():
    dp = O()
    dp.layer_num = KV_LAYER_NUM
    dp.head_num = KV_HEAD_NUM
    dp.head_dim = KV_HEAD_DIM
    dp.store_dtype = KV_DTYPE
    dp.size = KV_BATCH + 1
    dp.start_layer = 0
    dp.end_layer = KV_LAYER_NUM
    dp.device = "cpu"
    return MHATokenToKVPoolHost(
        dp, 1.0, 0, page_size=1, layout="page_first", pin_memory=False, device="cpu"
    )


def fill_tensor(tensor, seed):
    n = tensor.numel() * tensor.element_size()
    gen = torch.Generator().manual_seed(seed)
    data = torch.randint(0, 256, (n,), dtype=torch.uint8, generator=gen)
    tensor.view(torch.uint8).reshape(-1).copy_(data)


def fill_pools(mamba, kv):
    fill_tensor(mamba.temporal_buffer, 11)
    for i, buf in enumerate(mamba.conv_buffer):
        fill_tensor(buf, 100 + i)
    fill_tensor(kv.kv_buffer, 777)


def build_all():
    mamba = make_mamba()
    kv = make_kv()
    fill_pools(mamba, kv)
    return mamba, kv


def meta_pairs(pool, indices):
    ptrs, lens = pool.get_page_buffer_meta(torch.tensor(list(indices), dtype=torch.int64))
    return list(zip(ptrs, lens)), sum(lens)


def production_python_bytes(pool, indices):
    """Exactly today's write-path marshalling: get_data_page + _page_byte_view."""
    vals = [pool.get_data_page(int(i), flat=True) for i in indices]
    views = [_page_byte_view(v) for v in vals]
    return b"".join(bytes(v) for v in views), vals, views


def python_ctypes_bytes(pairs):
    return b"".join(ctypes.string_at(ptr, length) for ptr, length in pairs)


def native_bytes(module, pairs, total):
    return module.read_iovec(pairs, total)


def sha256(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


class Victim(threading.Thread):
    """Dense pure-Python thread; records the largest contiguous GIL gap."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = False
        self.ready = threading.Event()
        self.reset()

    def reset(self):
        self.iters = 0
        self.max_gap_ns = 0

    def run(self):
        last = time.perf_counter_ns()
        self.ready.set()
        while not self.stop:
            n = 0
            for _ in range(200):
                n += 1
            self.iters += n
            now = time.perf_counter_ns()
            self.max_gap_ns = max(self.max_gap_ns, now - last)
            last = now


def stats_ns(samples):
    s = sorted(samples)
    n = len(s)
    return {
        "n": n,
        "median_ms": statistics.median(s) / 1e6,
        "p95_ms": s[min(n - 1, int(0.95 * n))] / 1e6,
        "min_ms": s[0] / 1e6,
        "max_ms": s[-1] / 1e6,
    }


def timeit(fn, reps):
    fn()
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    return stats_ns(samples)


# --------------------------------------------------------------------------- #
# Cold-process peak-RSS modes
# --------------------------------------------------------------------------- #

def _proc_status():
    with open("/proc/self/status") as handle:
        fields = {}
        for line in handle:
            if line.startswith(("VmHWM:", "VmRSS:")):
                key, value = line.split(":", 1)
                fields[key] = int(value.strip().split()[0]) * 1024
    return fields


def rss_mode(pool_name, kind):
    module = load_poc()
    torch.set_num_threads(1)
    mamba, kv = build_all()
    if pool_name == "mamba":
        pool, indices = mamba, [1]
    elif pool_name == "kv":
        pool, indices = kv, [512]
    elif pool_name == "kv1024":
        pool, indices = kv, list(range(KV_BATCH))
    else:
        raise SystemExit(f"unknown pool {pool_name}")
    pairs, total = meta_pairs(pool, indices)

    # No warm-up: the first call is measured, so first-touch page faults are part
    # of the number (that is the cost the real first write pays).
    gc.collect()
    before = _proc_status()
    if kind == "native":
        result = module.read_iovec(pairs, total)
    elif kind == "python":
        vals = [pool.get_data_page(int(i), flat=True) for i in indices]
        result = b"".join(bytes(_page_byte_view(v)) for v in vals)
    else:
        raise SystemExit(f"unknown kind {kind}")
    after = _proc_status()
    assert len(result) == total
    print(
        json.dumps(
            {
                "pool": pool_name,
                "kind": kind,
                "page_bytes": total,
                "vmhwm_delta_mb": (after["VmHWM"] - before["VmHWM"]) / 1e6,
                "vmrss_delta_mb": (after["VmRSS"] - before["VmRSS"]) / 1e6,
                "note": "VmHWM delta is uninformative here: pool construction and "
                "the fill temporaries already set the process high-water mark, so "
                "VmRSS delta is the field to read",
                "result_sha256": sha256(result),
            }
        )
    )


# --------------------------------------------------------------------------- #
# Main comparison + timing mode
# --------------------------------------------------------------------------- #

def main():
    module = load_poc()
    torch_default_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    mamba, kv = build_all()

    report = {
        "python": sys.executable,
        "torch": torch.__version__,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cuda_available": torch.cuda.is_available(),
        "torch_default_threads": torch_default_threads,
        "torch_threads_during_single_core_comparison": torch.get_num_threads(),
        "pinning": "ordinary page-aligned CPU buffers via torch CPU allocator; "
        "pin_memory=False; NO cudaHostRegister (needs a CUDA context)",
        "shapes": {
            "mamba_temporal_buffer": list(mamba.temporal_buffer.shape),
            "mamba_conv_buffer_0": list(mamba.conv_buffer[0].shape),
            "kv_buffer": list(kv.kv_buffer.shape),
        },
        "equality": {},
        "timing": {},
    }

    # --- geometry assertions (must match the audit's production numbers) ---
    mamba_pairs, mamba_total = meta_pairs(mamba, [1])
    assert mamba_total == MAMBA_PAGE_BYTES, mamba_total
    kv_pairs, kv_total = meta_pairs(kv, [512])
    assert kv_total == KV_PAGE_BYTES, kv_total
    assert kv.get_data_page(512, flat=True).numel() == KV_PAGE_BYTES
    report["geometry"] = {
        "mamba_page_bytes": mamba_total,
        "kv_page_bytes": kv_total,
        "mamba_components": len(mamba_pairs),
        "kv_components": len(kv_pairs),
    }

    # --- 3.1 byte equality: production Python gather vs raw-ptr ctypes vs native ---
    cases = {
        "mamba_page_1": (mamba, [1], mamba_pairs, mamba_total),
        "mamba_page_2": (mamba, [2], *meta_pairs(mamba, [2])),
        "kv_page_0": (kv, [0], *meta_pairs(kv, [0])),
        "kv_page_512": (kv, [512], kv_pairs, kv_total),
        "kv_page_1024": (kv, [1024], *meta_pairs(kv, [1024])),
        "kv_batch_1024": (kv, list(range(KV_BATCH)), *meta_pairs(kv, list(range(KV_BATCH)))),
    }
    for name, (pool, indices, pairs, total) in cases.items():
        py_prod, _vals, _views = production_python_bytes(pool, indices)
        py_ctypes = python_ctypes_bytes(pairs)
        native = native_bytes(module, pairs, total)
        dst = bytearray(total)
        copied = module.read_into(pairs, dst, total)
        assert len(py_prod) == total and len(py_ctypes) == total and len(native) == total
        assert py_prod == py_ctypes, f"{name}: ctypes meta gather != production gather"
        assert py_prod == native, f"{name}: native != production gather"
        assert copied == total and bytes(dst) == py_prod, f"{name}: read_into mismatch"
        report["equality"][name] = {
            "bytes": total,
            "components": len(pairs),
            "sha256_production_python": sha256(py_prod),
            "sha256_native": sha256(native),
            "sha256_native_preallocated_bytearray": sha256(bytes(dst)),
            "byte_identical": True,
        }
        del dst
    # pages are actually distinct, so equality is not vacuous
    assert report["equality"]["mamba_page_1"]["sha256_production_python"] != (
        report["equality"]["mamba_page_2"]["sha256_production_python"]
    )
    assert report["equality"]["kv_page_0"]["sha256_production_python"] != (
        report["equality"]["kv_page_512"]["sha256_production_python"]
    )
    report["distinct_pages_confirmed"] = True

    # --- 3.2 zero-intermediate-gather-copy accounting ---
    tracemalloc.start()
    pairs, total = meta_pairs(mamba, [1])
    module.read_iovec(pairs, total)  # warm
    gc.collect()
    tracemalloc.reset_peak()
    current_before, _ = tracemalloc.get_traced_memory()
    rust_before = module.system_alloc_stats()
    out = module.read_iovec(pairs, total)
    rust_after = module.system_alloc_stats()
    current_after, peak_after = tracemalloc.get_traced_memory()
    last_copy = module.last_copy_alloc_stats()
    tracemalloc.stop()
    report["zero_intermediate_gather_copy"] = {
        "tracemalloc_peak_delta_mb": (peak_after - current_before) / 1e6,
        "tracemalloc_current_delta_mb": (current_after - current_before) / 1e6,
        "page_bytes": total,
        "rust_alloc_calls_total_before_after": [rust_before[0], rust_after[0]],
        "rust_alloc_bytes_total_before_after": [rust_before[1], rust_after[1]],
        "rust_alloc_calls_inside_copy_region": last_copy[0],
        "rust_alloc_bytes_inside_copy_region": last_copy[1],
        "mechanism": "PyBytes::new_with allocates the destination once and the "
        "copy loop writes each (ptr,len) source directly into it; no intermediate "
        "buffer exists in the function body",
    }
    assert last_copy[0] == 0 and last_copy[1] == 0, last_copy
    assert (peak_after - current_before) < total * 1.05, (peak_after, current_before)
    del out
    gc.collect()

    # read_into: caller-owned destination, no allocation anywhere.
    dst = bytearray(total)
    module.read_into(pairs, dst, total)  # warm
    module.read_into(pairs, dst, total)
    into_alloc = module.last_copy_alloc_stats()
    report["zero_intermediate_gather_copy"]["rust_alloc_calls_inside_read_into_copy_region"] = into_alloc[0]
    report["zero_intermediate_gather_copy"]["rust_alloc_bytes_inside_read_into_copy_region"] = into_alloc[1]
    assert into_alloc == (0, 0), into_alloc
    del dst
    gc.collect()

    # --- 3.3 timings. "alone" = no competing Python thread; then a co-running
    #     dense-Python victim measures the native region's GIL behaviour. ---
    default_threads = torch_default_threads
    torch.set_num_threads(1)

    # mamba single page, alone
    pairs, total = meta_pairs(mamba, [1])
    dst = bytearray(total)
    native_mamba_into = timeit(lambda: module.read_into(pairs, dst, total), 30)
    native_mamba_bytes_path = timeit(lambda: module.read_iovec(pairs, total), 30)
    py_mamba = timeit(lambda: _page_byte_view(mamba.get_data_page(1)), 30)
    py_mamba_bytes = timeit(lambda: bytes(_page_byte_view(mamba.get_data_page(1))), 30)
    report["timing"]["mamba_page_51511296B_alone"] = {
        "native_read_into_preallocated_dst": native_mamba_into,
        "native_read_iovec_new_bytes": native_mamba_bytes_path,
        "python_production_get_data_page_plus_view": py_mamba,
        "python_gather_to_bytes": py_mamba_bytes,
    }
    del pairs, total, dst
    gc.collect()

    # kv single page, alone
    pairs, total = meta_pairs(kv, [512])
    dst = bytearray(total)
    native_kv_into = timeit(lambda: module.read_into(pairs, dst, total), 500)
    native_kv = timeit(lambda: module.read_iovec(pairs, total), 500)
    py_kv = timeit(lambda: _page_byte_view(kv.get_data_page(512, flat=True)), 500)
    py_kv_bytes = timeit(
        lambda: bytes(_page_byte_view(kv.get_data_page(512, flat=True))), 500
    )
    report["timing"]["kv_page_16384B_alone"] = {
        "native_read_into_preallocated_dst": native_kv_into,
        "native_read_iovec_new_bytes": native_kv,
        "python_production_get_data_page_plus_view": py_kv,
        "python_gather_to_bytes": py_kv_bytes,
        "note": "single tiny page: call overhead dominates both paths",
    }
    del pairs, total, dst
    gc.collect()

    # kv batch of 1024 pages (= one production extent write), alone
    batch_pairs, batch_total = meta_pairs(kv, list(range(KV_BATCH)))
    assert batch_total == KV_BATCH * KV_PAGE_BYTES
    batch_dst = bytearray(batch_total)
    native_batch_into = timeit(lambda: module.read_into(batch_pairs, batch_dst, batch_total), 30)
    native_batch = timeit(lambda: module.read_iovec(batch_pairs, batch_total), 20)
    py_batch = timeit(
        lambda: [_page_byte_view(kv.get_data_page(int(i), flat=True)) for i in range(KV_BATCH)],
        5,
    )
    py_batch_bytes = timeit(
        lambda: b"".join(
            bytes(_page_byte_view(kv.get_data_page(int(i), flat=True)))
            for i in range(KV_BATCH)
        ),
        5,
    )
    # Best-case Python: let torch use all its default threads.
    torch.set_num_threads(default_threads)
    py_batch_default_threads = timeit(
        lambda: [_page_byte_view(kv.get_data_page(int(i), flat=True)) for i in range(KV_BATCH)],
        5,
    )
    report["timing"]["kv_batch_1024_pages_16777216B_alone"] = {
        "native_read_into_preallocated_dst": native_batch_into,
        "native_read_iovec_new_bytes": native_batch,
        "python_production_marshal_1024_pages_torch_1_thread": py_batch,
        "python_production_marshal_1024_pages_torch_default_threads": (
            py_batch_default_threads
        ),
        "python_gather_to_bytes_torch_1_thread": py_batch_bytes,
        "torch_default_threads": default_threads,
    }
    torch.set_num_threads(1)

    # Same measurements with a co-running dense-Python victim.
    victim = Victim()
    victim.start()
    victim.ready.wait()
    time.sleep(0.2)
    mamba_pairs_v, mamba_total_v = meta_pairs(mamba, [1])
    mamba_dst_v = bytearray(mamba_total_v)
    victim.reset()
    timeit(lambda: module.read_into(mamba_pairs_v, mamba_dst_v, mamba_total_v), 20)
    mamba_into_gap = victim.max_gap_ns / 1e6
    victim.reset()
    timeit(lambda: module.read_iovec(mamba_pairs_v, mamba_total_v), 20)
    mamba_bytes_gap = victim.max_gap_ns / 1e6
    victim.reset()
    timeit(lambda: module.read_into(batch_pairs, batch_dst, batch_total), 30)
    native_batch_into_gap = victim.max_gap_ns / 1e6
    victim.reset()
    timeit(lambda: module.read_iovec(batch_pairs, batch_total), 20)
    native_batch_victim_gap = victim.max_gap_ns / 1e6
    victim.reset()
    py_batch_contended = timeit(
        lambda: [_page_byte_view(kv.get_data_page(int(i), flat=True)) for i in range(KV_BATCH)],
        1,
    )
    py_batch_contended_victim_gap = victim.max_gap_ns / 1e6
    victim.stop = True
    victim.join(2.0)
    report["timing"]["kv_batch_1024_pages_16777216B_contended"] = {
        "definition": "same batch while a dense pure-Python thread competes for the GIL",
        "mamba_page_read_into_victim_max_gap_ms": mamba_into_gap,
        "mamba_page_read_iovec_victim_max_gap_ms": mamba_bytes_gap,
        "mamba_page_read_iovec_gap_cause": "CPython PyBytes_FromStringAndSize "
        "zero-fills the 51.5 MB destination while the GIL is held (first-touch "
        "page faults); read_into has no such allocation",
        "native_read_into_preallocated_dst": {"victim_max_gap_ms": native_batch_into_gap},
        "native_read_iovec_new_bytes": {"victim_max_gap_ms": native_batch_victim_gap},
        "python_production_marshal_torch_1_thread": py_batch_contended,
        "python_production_marshal_victim_max_gap_ms": py_batch_contended_victim_gap,
    }
    assert mamba_into_gap < 10.0, mamba_into_gap
    assert native_batch_into_gap < 50.0, native_batch_into_gap
    del batch_dst, batch_pairs, mamba_dst_v, mamba_pairs_v
    gc.collect()
    report["timing"]["kv_batch_alone_ratio_python_over_native"] = (
        py_batch["median_ms"] / native_batch_into["median_ms"]
    )

    # --- 3.4 cold-process peak-RSS measurement of the two paths ---
    import subprocess

    rss = {}
    for pool_name in ("mamba", "kv1024"):
        for kind in ("native", "python"):
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--rss", pool_name, kind],
                capture_output=True,
                text=True,
                env=os.environ.copy(),
            )
            assert proc.returncode == 0, (pool_name, kind, proc.stderr[-2000:])
            rss[f"{pool_name}_{kind}"] = json.loads(proc.stdout.strip().splitlines()[-1])
    report["peak_rss_cold_process"] = rss

    print(json.dumps(report, indent=2))
    print("STAGE3_PAGE_OK")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--rss":
        rss_mode(sys.argv[2], sys.argv[3])
    else:
        main()
