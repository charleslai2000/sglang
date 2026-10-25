#!/usr/bin/env python3
import argparse, hashlib, json, os, statistics, time
from pathlib import Path
import torch

p = argparse.ArgumentParser()
p.add_argument("--out", required=True)
p.add_argument("--n", type=int, default=8192)
p.add_argument("--warmup", type=int, default=5)
p.add_argument("--iters", type=int, default=15)
p.add_argument("--repeats", type=int, default=3)
a = p.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
assert torch.cuda.is_available()
torch.cuda.set_device(0)
props = torch.cuda.get_device_properties(0)
assert "3090" in props.name, props.name
# Seed and create identical FP32 source matrices for all dtypes.
torch.manual_seed(20261025)
g = torch.Generator(device="cuda").manual_seed(20261025)
x = torch.randn((a.n, a.n), generator=g, device="cuda", dtype=torch.float32) / (
    a.n**0.5
)
y = torch.randn((a.n, a.n), generator=g, device="cuda", dtype=torch.float32) / (
    a.n**0.5
)
torch.cuda.synchronize()
meta = {
    "gpu": props.name,
    "uuid": str(torch.cuda.get_device_properties(0).uuid)
    if hasattr(torch.cuda.get_device_properties(0), "uuid")
    else None,
    "n": a.n,
    "seed": 20261025,
    "warmup": a.warmup,
    "iters": a.iters,
    "repeats": a.repeats,
    "torch": torch.__version__,
    "cuda_runtime": torch.version.cuda,
    "matmul_fp32_precision": torch.get_float32_matmul_precision(),
    "power_limit_w": None,
    "input_x_fp32_sha256": hashlib.sha256(x.cpu().numpy().tobytes()).hexdigest(),
    "input_y_fp32_sha256": hashlib.sha256(y.cpu().numpy().tobytes()).hexdigest(),
}
try:
    import pynvml

    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    meta["power_limit_w"] = pynvml.nvmlDeviceGetPowerManagementLimit(h) / 1000
except Exception as e:
    meta["nvml_error"] = repr(e)
# Float32 strict reference uses cuBLAS FP32, TF32 disabled.
torch.backends.cuda.matmul.allow_tf32 = False
ref = (x @ y).float()
torch.cuda.synchronize()
ref_cpu = ref.cpu()
meta["reference_sha256"] = hashlib.sha256(ref_cpu.numpy().tobytes()).hexdigest()
res = {}
for name, dtype, tf32 in [
    ("fp16", torch.float16, False),
    ("bf16", torch.bfloat16, False),
    ("tf32", torch.float32, True),
]:
    torch.backends.cuda.matmul.allow_tf32 = tf32
    xx = x.to(dtype)
    yy = y.to(dtype)

    def op():
        return xx @ yy

    for _ in range(a.warmup):
        z = op()
    torch.cuda.synchronize()
    times = []
    checks = []
    for r in range(a.repeats):
        ev0 = torch.cuda.Event(enable_timing=True)
        ev1 = torch.cuda.Event(enable_timing=True)
        ev0.record()
        for _ in range(a.iters):
            z = op()
        ev1.record()
        ev1.synchronize()
        ms = ev0.elapsed_time(ev1) / a.iters
        times.append(ms)
        torch.cuda.synchronize()
        zf = z.float()
        d = zf - ref
        checks.append(
            {
                "max_abs": float(d.abs().max().item()),
                "rmse": float(d.square().mean().sqrt().item()),
                "rel_l2": float(d.norm().item() / ref.norm().item()),
                "output_sha256": hashlib.sha256(
                    zf.cpu().contiguous().numpy().tobytes()
                ).hexdigest(),
            }
        )
        del z, zf, d
    t = statistics.median(times)
    res[name] = {
        "dtype": str(dtype),
        "allow_tf32": tf32,
        "ms_samples": times,
        "median_ms": t,
        "tflops": 2 * a.n**3 / (t * 1e-3) / 1e12,
        "correctness_per_repeat": checks,
    }
    del xx, yy
    torch.cuda.empty_cache()
meta["results"] = res
# Record end-of-run device telemetry from NVML.
try:
    meta["telemetry"] = {
        "temperature_c": pynvml.nvmlDeviceGetTemperature(
            h, pynvml.NVML_TEMPERATURE_GPU
        ),
        "power_w": pynvml.nvmlDeviceGetPowerUsage(h) / 1000,
        "sm_clock_mhz": pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_SM),
        "mem_clock_mhz": pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_MEM),
    }
except Exception as e:
    meta["telemetry_error"] = repr(e)
(out / "result.json").write_text(json.dumps(meta, indent=2) + "\n")
print(json.dumps(meta, indent=2))
