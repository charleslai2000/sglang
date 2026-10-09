# OPS-20260909-RH-STARTUP-NVRUNTIME-RETRY

ENTRY: ACCEPT

status: done
task_id: D3060-RH-STARTUP-NVRUNTIME-RETRY-20260909
orchestration_epoch: 20260909-rh-ab2
role: devops
host: i-1.gpushare.com:27460 (RTX3060 only)
final_observed_at: 2026-09-09T14:03:46+08:00

## Summary

The RTX3060 Qwen3.5-4B service was restored and left running in RH-OFF seeded-storage
mode. It listens on `127.0.0.1:30000`; final `/health` returned HTTP 200. The
seeded-storage directory was not deleted, cleared, altered, copied, or moved.

## Observed facts

- GPU: NVIDIA GeForce RTX 3060, compute capability 8.6; driver `550.144.03`; driver
  CUDA version `12.4`.
- Venv: `/root/sglang-env-3060-4b`; torch `2.6.0+cu124`; `torch.version.cuda=12.4`;
  `torch.cuda.is_available()` was true.
- Installed NVRTC package: `nvidia-cuda-nvrtc-cu12 12.4.127`.
- Loader-visible CUDA libraries included `libnvrtc.so.12` and
  `libnvrtc-builtins.so.12.4`; no `libnvrtc.so.13` existed on the host.
- Installed `sglang-kernel` was `0.4.6.post1`. Its wheel at
  `/hy-tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl` has
  `sha256=5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`.
- The wheel's `sm90` and `sm100` common-ops binaries require CUDA-13 sonames,
  including `libnvrtc.so.13`, `libcublas.so.13`, and `libcudart.so.13`.
- The prior runtime attempt had added/changed
  `sgl_kernel/sm86/common_ops.abi3.so` at 2026-09-09 11:57:35. Its observed SHA256
  was `3d2a6efd611a0aa2109ccc1cfac72c0669ffbe49c354e4f0dda742dabc66ffc9`.
  `readelf`, `ldd`, direct extension import, and package import all succeeded for
  this SM86 CUDA-12-compatible binary with torch CUDA 12.4.
- The initial failed launch log recorded the exact failure: the SM86 variant was
  unavailable, fallback loading reached CUDA-13 `sm100`/`sm90` binaries, and those
  failed with `ImportError: libnvrtc.so.13: cannot open shared object file`.

## Exact fix

1. No ABI-unsafe `libnvrtc.so.13 -> libnvrtc.so.12` symlink was created, and no
   CUDA-13 runtime was installed. The verified SM86 CUDA-12 common-ops binary was
   retained and used; package import then resolved `sgl_kernel.common_ops` from
   `sgl_kernel/sm86/common_ops.abi3.so`.
2. The venv already contained `ninja 1.13.2` at
   `/root/sglang-env-3060-4b/bin/ninja`; the first post-NVRTC launch failed only
   because that directory was absent from `PATH`. A no-op
   `pip install --no-deps ninja` confirmed it was already installed. The successful
   service launch prepended `/root/sglang-env-3060-4b/bin` to `PATH`.
3. The successful launch exported:

   ```text
   SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909
   ```

   It did not pass `--enable-ready-horizon`; the emitted `server_args` explicitly
   recorded `enable_ready_horizon=False`.

## Successful service evidence

- Log: `/tmp/sglang3060-rh-startup-nvruntime-retry2-20260909.log`.
- Service PID: `97921`, command rooted at `/root/sglang-env-3060-4b/bin/python`.
- Port: `127.0.0.1:30000`, owned by PID `97921`.
- `/health`: HTTP 200 at final verification; log contains `GET /health ... 200 OK`.
- Readiness: log contains `The server is fired up and ready to roll!`.
- CUDA graph capture completed for prefill and decode; file storage backend was
  created successfully.
- Fatal scan found no `Traceback`, `AssertionError`, OOM, `ImportError`,
  `FileNotFoundError`, or `Killed` in the successful launch log.

## Seeded-storage invariant

The directory `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909` was measured before and
after the successful launch and health checks:

```text
before: bytes=23051071488 files=550080
after:  bytes=23051071488 files=550080
```

## Neuron safety audit

Using the exact requested SSH options, the 2026-09-09T14:03:46+08:00 read-only audit
found no `neuron`-named process. No process was signaled or stopped. The local process
tree showed the task service PID 97921 and its scheduler/compile workers. `nvidia-smi`
reported two compute-app rows as PID `3065498`/`3065786`, process name `[Not Found]`,
using 120/8370 MiB; their commands were not visible in this container PID namespace.
They were not identified as Neuron and were not touched.

## Followups

- None required for the stated acceptance criteria.

## Open issues

- Non-blocking startup warnings remain for optional `openai_harmony`, `cutlass`, and
  `torchcodec` modules; they did not prevent readiness or affect RH-OFF acceptance.
- The host/container PID namespace does not expose command names for the two
  `nvidia-smi` `[Not Found]` rows; no action was taken because attribution was
  unavailable and no Neuron command was observed.

Extra work requires a fresh Task ID.
