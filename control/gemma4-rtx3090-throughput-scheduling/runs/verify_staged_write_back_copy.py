"""Contract check + CPU-submission timing for the staged write-back copy path."""

import time, statistics
import torch
from sglang.kernels.ops.kvcache.hicache import transfer_hicache_all_layer_staged_lf_pf

DEV = "cuda"
LAYERS, DIM, SLOTS, HOST_ROWS = 35, 256, 8192, 8192


def build(n_tokens, contiguous_dst):
    dev_k = torch.randint(0, 255, (SLOTS, LAYERS, DIM), dtype=torch.uint8, device=DEV)
    dev_v = torch.randint(0, 255, (SLOTS, LAYERS, DIM), dtype=torch.uint8, device=DEV)
    dev_kt, dev_vt = dev_k.transpose(0, 1), dev_v.transpose(0, 1)
    k_ptrs = torch.tensor([dev_kt[i].data_ptr() for i in range(LAYERS)], dtype=torch.uint64, device=DEV)
    v_ptrs = torch.tensor([dev_vt[i].data_ptr() for i in range(LAYERS)], dtype=torch.uint64, device=DEV)
    staging_k = torch.zeros((n_tokens, LAYERS, DIM), dtype=torch.uint8, device=DEV)
    staging_v = torch.zeros((n_tokens, LAYERS, DIM), dtype=torch.uint8, device=DEV)
    host_k = torch.zeros((HOST_ROWS, LAYERS, DIM), dtype=torch.uint8, pin_memory=True)
    host_v = torch.zeros((HOST_ROWS, LAYERS, DIM), dtype=torch.uint8, pin_memory=True)
    src = torch.arange(n_tokens, dtype=torch.int64, device=DEV) * 2 % SLOTS
    if contiguous_dst:
        dst = torch.arange(1000, 1000 + n_tokens, dtype=torch.int64)
    else:
        dst = (torch.arange(n_tokens, dtype=torch.int64) * 3 + 7) % HOST_ROWS
        assert len(set(dst.tolist())) == n_tokens
    return dict(dev_k=dev_k, dev_v=dev_v, k_ptrs=k_ptrs, v_ptrs=v_ptrs,
                staging_k=staging_k, staging_v=staging_v, host_k=host_k, host_v=host_v,
                src=src, dst=dst)


def call(t):
    transfer_hicache_all_layer_staged_lf_pf(
        k_ptr_src=t["k_ptrs"], v_ptr_src=t["v_ptrs"], src_indices=t["src"],
        dst_indices=t["dst"], staging_k=t["staging_k"], staging_v=t["staging_v"],
        dst_k=t["host_k"], dst_v=t["host_v"], page_size=1)


def verify(n_tokens, contiguous_dst):
    t = build(n_tokens, contiguous_dst)
    call(t)
    torch.cuda.synchronize()
    ok_k = torch.equal(t["host_k"][t["dst"]].contiguous(), t["staging_k"].cpu())
    ok_v = torch.equal(t["host_v"][t["dst"]].contiguous(), t["staging_v"].cpu())
    print(f"verify pages={n_tokens} contiguous_dst={contiguous_dst} k={ok_k} v={ok_v}")
    return ok_k and ok_v


def bench(n_tokens, contiguous_dst, iters=20):
    t = build(n_tokens, contiguous_dst)
    call(t); torch.cuda.synchronize()
    cpu = []
    for _ in range(iters):
        t0 = time.perf_counter(); call(t); cpu.append(time.perf_counter() - t0)
    torch.cuda.synchronize()
    print(f"bench pages={n_tokens} contiguous_dst={contiguous_dst} "
          f"cpu_us_per_call={statistics.median(cpu)*1e6:.1f}")


if __name__ == "__main__":
    ok = all(verify(n, c) for n in (128, 512, 4096) for c in (True, False))
    assert ok, "staged write-back copied wrong bytes"
    bench(512, True); bench(4096, True); bench(4096, False)
    print("OK")
