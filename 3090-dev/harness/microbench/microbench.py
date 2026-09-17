#!/usr/bin/env python3
"""E1 CPU-only microbenchmark for the L3 long-context write-back candidate C1/C2.

Frozen v1 tree only (PYTHONPATH=/opt/sglang/local-prod-v1/src/python).
No GPU: CUDA_VISIBLE_DEVICES="" is asserted.

Real host pools are constructed from the frozen classes with a minimal CPU
`device_pool` stand-in that supplies the *exact* geometry/dtypes the real
Qwen3.5-9B workload uses (24 mamba layers; temporal (32,128,128) fp32;
conv (8192,3) bf16; KV: 8 full-attn layers, 4 heads, head_dim 256, fp8_e4m3).
Only the host-side buffers matter for the marshalling cost, so the surrogate
device_pool does not affect the measured copy.
"""
from __future__ import annotations
import json, os, statistics, sys, threading, time
import torch

assert os.environ.get("CUDA_VISIBLE_DEVICES") == "", "CUDA_VISIBLE_DEVICES must be empty"
assert not torch.cuda.is_available(), "CUDA must not be available"

from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.storage.extent.extent_file_backend import _page_byte_view
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

# ------------------------------------------------------------------ geometry
NUM_MAMBA_LAYERS = 24
TEMPORAL_SHAPE = (32, 128, 128)      # (HV, V, K) fp32
CONV_SHAPE = (8192, 3)               # (conv_dim, K-1) bf16  (key_dim*2+value_dim=8192)
KV_LAYER_NUM = 8                     # full_attention_interval=4 over 32 layers
KV_HEAD_NUM = 4
KV_HEAD_DIM = 256
KV_DTYPE = torch.float8_e4m3fn
KV_BATCH = 1024
CRC_PAYLOAD = 122_920

results = {"meta": {
    "torch": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "torch_num_threads": torch.get_num_threads(),
    "switchinterval": sys.getswitchinterval(),
    "cpu_count": os.cpu_count(),
}, "geometry": {}, "ops": {}, "concurrency": {}}


class _Obj:
    pass


def make_mamba_pool():
    mc = _Obj()
    mc.temporal = torch.zeros((NUM_MAMBA_LAYERS, 1) + TEMPORAL_SHAPE, dtype=torch.float32)
    mc.conv = [torch.zeros((NUM_MAMBA_LAYERS, 1) + CONV_SHAPE, dtype=torch.bfloat16)]
    dp = _Obj()
    dp.num_mamba_layers = NUM_MAMBA_LAYERS
    dp.mamba_cache = mc
    dp.size = 2
    dp.device = "cpu"
    return MambaPoolHost(dp, host_to_device_ratio=1.0, host_size=0, pin_memory=False,
                         device="cpu", layout="page_first")


def make_kv_pool():
    dp = _Obj()
    dp.layer_num = KV_LAYER_NUM
    dp.head_num = KV_HEAD_NUM
    dp.head_dim = KV_HEAD_DIM
    dp.store_dtype = KV_DTYPE
    dp.size = KV_BATCH + 1
    dp.start_layer = 0
    dp.end_layer = KV_LAYER_NUM
    dp.device = "cpu"
    return MHATokenToKVPoolHost(dp, host_to_device_ratio=1.0, host_size=0, page_size=1,
                                layout="page_first", pin_memory=False, device="cpu")


def stats(xs):
    xs = list(xs)
    s = sorted(xs)
    n = len(s)
    def pct(p):
        return s[min(n - 1, int(p * n))]
    return {
        "n": n,
        "min_ms": min(s) / 1e6,
        "p25_ms": pct(0.25) / 1e6,
        "median_ms": statistics.median(s) / 1e6,
        "p75_ms": pct(0.75) / 1e6,
        "p95_ms": pct(0.95) / 1e6,
        "max_ms": max(s) / 1e6,
        "mean_ms": statistics.fmean(s) / 1e6,
    }


# ---------------------------------------------------------- op 1: mamba page
def bench_mamba(pool, reps):
    idx = 1
    # warm
    for _ in range(3):
        pool.get_data_page(idx)
    total = []
    flat = []
    cat = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        pool.get_data_page(idx)
        total.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        fs = [pool._flatten_tensor_bytes(t) for t in pool._iter_page_tensors(idx)]
        flat.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        c = torch.cat(fs)
        cat.append(time.perf_counter_ns() - t0)
    page = pool.get_data_page(idx)
    results["geometry"]["mamba_page_bytes"] = page.numel()
    results["geometry"]["mamba_page_dtype"] = str(page.dtype)
    results["ops"]["mamba_get_data_page"] = {**stats(total), "raw_ns": total}
    results["ops"]["mamba_flatten_bytes"] = stats(flat)
    results["ops"]["mamba_torch_cat_only"] = stats(cat)
    return pool


# ---------------------------------------------------------- op 2: kv 1024 batch
def bench_kv(pool, reps):
    n = KV_BATCH
    host_indices = list(range(n))
    page_size = pool.page_size
    # warm
    _ = [pool.get_data_page(int(host_indices[i * page_size]), flat=True) for i in range(n)]
    batch = []
    views = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        values = [pool.get_data_page(int(host_indices[i * page_size]), flat=True)
                  for i in range(n)]
        batch.append(time.perf_counter_ns() - t0)
        t0 = time.perf_counter_ns()
        _v = [_page_byte_view(v) for v in values]
        views.append(time.perf_counter_ns() - t0)
    results["geometry"]["kv_page_bytes"] = pool.get_data_page(0, flat=True).numel()
    results["geometry"]["kv_batch_bytes"] = n * results["geometry"]["kv_page_bytes"]
    results["ops"]["kv_batch_get_data_page_1024"] = {**stats(batch), "raw_ns": batch}
    results["ops"]["kv_batch_page_byte_view_1024"] = {**stats(views), "raw_ns": views}
    # single page alone for scaling
    single = []
    for _ in range(200):
        t0 = time.perf_counter_ns()
        pool.get_data_page(3, flat=True)
        single.append(time.perf_counter_ns() - t0)
    results["ops"]["kv_single_get_data_page"] = stats(single)
    return pool


# ---------------------------------------------------------- op 3: crc32c
def bench_crc(reps):
    payload = bytes(bytearray((i * 37 + 11) & 0xFF for i in range(CRC_PAYLOAD)))
    # realistic 1024-entry SetPayload frame (storage_key len chosen to hit the
    # measured max frame payload)
    key_len = (CRC_PAYLOAD - 40) // KV_BATCH - 23
    entries = [em.SetEntry(storage_key=b"k" * key_len, extent_id=i, offset=i * 16384,
                           length=16384, generation=1, component=1)
               for i in range(KV_BATCH)]
    sp = em.SetPayload(group_epoch=b"\x00" * 16, group_seq=0, batch_id=1,
                       member_index=0, member_count=1, entries=entries)
    set_payload = em.encode_set_payload(sp)
    # warm
    em.crc32c(payload[:4096])
    crc = []
    enc = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        em.crc32c(payload)
        crc.append(time.perf_counter_ns() - t0)
    for _ in range(max(3, reps // 5)):
        t0 = time.perf_counter_ns()
        em.encode_frame(em.FRAME_SET, 1, set_payload)
        enc.append(time.perf_counter_ns() - t0)
    results["geometry"]["crc_payload_bytes"] = len(payload)
    results["geometry"]["set_payload_1024_entries_bytes"] = len(set_payload)
    results["geometry"]["encoded_frame_bytes"] = 24 + 4 + len(set_payload)
    results["ops"]["crc32c_122920B"] = {**stats(crc), "raw_ns": crc}
    results["ops"]["encode_frame_1024entries"] = {**stats(enc), "raw_ns": enc}
    return payload


# ------------------------------------------------- co-running busy Python loop
class BusyLoop(threading.Thread):
    """Minimal Python loop; tracks stall count above thresholds + max gap."""
    def __init__(self):
        super().__init__(daemon=True)
        self.stop = False
        self.ready = threading.Event()
        self.reset()

    def reset(self):
        self.count = 0
        self.max_ns = 0
        self.sum_ns = 0
        self.stalls = {2_000_000: 0, 5_000_000: 0, 10_000_000: 0, 50_000_000: 0}

    def run(self):
        n = 1
        last = time.perf_counter_ns()
        self.ready.set()
        while not self.stop:
            n = n + 1
            now = time.perf_counter_ns()
            d = now - last
            if d > self.max_ns:
                self.max_ns = d
            self.sum_ns += d
            for th in self.stalls:
                if d >= th:
                    self.stalls[th] += 1
            self.count += 1
            last = now

    def snapshot(self):
        return {"iters": self.count, "max_gap_ms": self.max_ns / 1e6,
                "mean_gap_us": (self.sum_ns / self.count / 1e3) if self.count else 0,
                "stalls_ge": {f"{k//1_000_000}ms": v for k, v in self.stalls.items()}}


def bench_corun(name, fn, reps):
    """fn() executes one op; returns its wall ns."""
    # baseline loop alone
    loop = BusyLoop()
    loop.start()
    loop.ready.wait()
    time.sleep(1.0)
    base = loop.snapshot()
    # contended: keep loop running, main thread executes ops
    loop.reset()
    op_alone = [fn() for _ in range(3)]
    t0 = time.perf_counter_ns()
    ops = [fn() for _ in range(reps)]
    wall = time.perf_counter_ns() - t0
    cont = loop.snapshot()
    loop.stop = True
    loop.join(timeout=2.0)
    results["concurrency"][name] = {
        "baseline_loop": base,
        "contended_loop": cont,
        "contended_window_ms": wall / 1e6,
        "reps": reps,
        "op_wall_ms": stats(ops),
        "baseline_stall_rate_per_s": {
            k: v / 1.0 for k, v in base["stalls_ge"].items()},
        "contended_stall_rate_per_s": {
            k: v / (wall / 1e9) for k, v in cont["stalls_ge"].items()},
        "op_raw_ns": ops,
    }


def main():
    reps = int(os.environ.get("REPS", "30"))
    mp = make_mamba_pool()
    kp = make_kv_pool()
    bench_mamba(mp, reps)
    bench_kv(kp, reps)
    bench_crc(max(20, reps))

    # co-run: mamba page materialisation and kv batch
    def mamba_op():
        t = time.perf_counter_ns()
        mp.get_data_page(1)
        return time.perf_counter_ns() - t
    mamba_op()
    bench_corun("mamba_get_data_page", mamba_op, reps)

    def kv_op():
        t = time.perf_counter_ns()
        [kp.get_data_page(int(i), flat=True) for i in range(KV_BATCH)]
        return time.perf_counter_ns() - t
    kv_op()
    bench_corun("kv_batch_get_data_page_1024", kv_op, max(5, reps // 2))

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
