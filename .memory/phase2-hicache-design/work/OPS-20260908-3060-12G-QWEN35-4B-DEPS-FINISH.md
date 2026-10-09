ENTRY: ACCEPT

# OPS-20260908-3060-12G-QWEN35-4B-DEPS-FINISH

status: done

Scope: host `i-1.gpushare.com:27460`, target `/root/miniconda3/envs/sglang-3060-4b`, Python `/usr/local/bin/python`. Password was redacted and not persisted. Marker `/root/sglang-3060-12g-hicache` existed. System torch/triton were inspected only. All installs used `pip install --target TARGET --no-cache-dir`.

## Evidence

Redacted commands executed:

```text
P=/usr/local/bin/python; T=/root/miniconda3/envs/sglang-3060-4b
$P -m pip install --target "$T" --no-cache-dir orjson
$P -m pip install --target "$T" --no-cache-dir pybase64
$P -m pip install --target "$T" --no-cache-dir starlette
$P -m pip install --target "$T" --no-cache-dir tqdm
$P -m pip install --target "$T" --no-cache-dir pydantic
$P -m pip install --target "$T" --no-cache-dir aiohttp
PYTHONPATH="$T" $P -c 'import torch, sglang'
```

Import loop exposed `pybase64`, `starlette`, `tqdm`, `pydantic`, and `aiohttp` in sequence; each was installed as a permitted pure-Python/runtime dependency. No replacement of torch or large compiler/CUDA stack was needed.

Final imports:

```text
torch 2.5.1+cu124 /usr/local/lib/python3.11/dist-packages/torch/__init__.py
sglang 0.5.19 /root/miniconda3/envs/sglang-3060-4b/sglang/__init__.py
```

System inspection: `torch 2.5.1+cu124`, `triton 3.1.0`; neither was modified.

Installed packages: `orjson 3.12.0`, `pybase64 1.5.0`, `starlette 1.6.0`, `anyio 4.15.1`, `idna 3.19`, `tqdm 4.70.0`, `pydantic 2.13.5`, `pydantic-core 2.46.5`, `aiohttp 3.14.3`, `aiohappyeyeballs 2.7.1`, `aiosignal 1.4.0`, `attrs 26.1.0`, `frozenlist 1.8.0`, `multidict 6.7.1`, `propcache 0.5.2`, `yarl 1.24.5`, `typing-extensions 4.16.0`, `annotated-types 0.8.0`, `typing-inspection 0.4.4`.

AWQ/Marlin/sgl_kernel import probes under `PYTHONPATH=TARGET`:

```text
awq ABSENT
marlin ABSENT
sgl_kernel ABSENT
```

The wheel does contain internal SGLang AWQ/Marlin source paths such as `sglang/srt/layers/quantization/awq/`, `awq_marlin.py`, `marlin_utils.py`, and `sglang/kernels/ops/quantization/`; no top-level import path is exposed. This is path detection only, not checkpoint compatibility validation.

Disk evidence:

```text
target_size_before=147928719 bytes
target_size_after=172060639 bytes
target_delta=24131920 bytes
root filesystem before: 244M used (df -h)
root filesystem after: 281948160 bytes used
```

No cache cleanup, model deletion, disk expansion, or broad `rm` was performed. No Qwen model or BF16 weights were downloaded. No server or benchmark was started. No 3090 state-machine action was performed. Final process probe found no `sglang` or `benchmark` process.

Followups: none within this Task ID.

Open issues: real AWQ/Marlin checkpoint compatibility and compiled-kernel/runtime compatibility remain unverified by design; this task performed import bootstrap only.
