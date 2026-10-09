# HiCache Production Migration — sglang-patch Env to RTX 3090 (3090-dev)

## status: in-progress

**Streaming migration is in progress. Three of five streams completed (sglang-b1-continuity, sglang, launch-scripts). Two remain: sglang-patch env (2.3G/8.8G extracted) and model (1.1G/11G extracted).**

## artifacts

- **Source machine**: `175.155.64.171:24052` (experimental, unchanged)
- **Target machine**: `175.155.64.171:22151` (new RTX 3090 production)
- **Target paths** (planned and partially verified):
  - `/root/miniconda3/envs/sglang-patch/` — conda env (in progress: 3.2G/8.8G extracted)
  - `/root/sglang-b1-continuity/` — editable install source (DONE)
  - `/root/sglang/` — sglang namespace package root (DONE)
  - `/root/models/Qwen3.5-9B-w4a16/` — model (in progress: 1.1G/11G extracted)
  - `/root/direct-launch-gate1.sh` — launch script (DONE)

## evidence

### Inventory (source machine 24052, from prior investigation)

| Item | Path | Size | Notes |
|------|------|------|-------|
| sglang-patch env | `/root/miniconda3/envs/sglang-patch/` | 8.8G | Python 3.10.21, self-contained conda env |
| sglang editable MAPPING | `__editable___sglang_0_0_0_dev0_finder.py` | — | Points to `/root/sglang-b1-continuity/python/sglang` |
| sglang-b1-continuity source | `/root/sglang-b1-continuity/` | 161M | Contains `python/sglang/` with all sglang Python code |
| sglang (no suffix) source | `/root/sglang/` | 145M | Separate git tree, same code, different inode |
| sglang_kernel .so files | `site-packages/sgl_kernel/*.abi3.so` | — | `sm90/common_ops.abi3.so`, `spatial_ops.abi3.so`, `flashmla_ops.abi3.so`, `flash_ops.abi3.so`, `infllm_ops.cpython-310-x86_64-linux-gnu.so`, `sm100/common_ops.abi3.so` |
| flashinfer | `site-packages/flashinfer/` | 109M | `flashinfer-python 0.6.17` |
| triton | `site-packages/triton/` | 690M | `triton 3.7.1` |
| torch | `site-packages/torch/` | 1.1G | `torch 2.13.0`, CUDA 13.0 |
| Model | `/root/models/Qwen3.5-9B-w4a16/` | 11G | 2 safetensors files (model.safetensors + model_mtp.safetensors) |
| Launch script | `/root/direct-launch-gate1.sh` | 2.4KB | Uses `sglang-patch` env python, flashinfer backend |

### Key finding: editable install MAPPING

The sglang editable install (`sglang 0.0.0.dev0`) has MAPPING:
```
{'sglang': '/root/sglang-b1-continuity/python/sglang'}
```
Both `/root/sglang` and `/root/sglang-b1-continuity` must exist at the same absolute paths on the target for sglang to import correctly.

### Streaming migration approach (zero source disk writes)

All transfers use `tar czf - | ssh ... tar xzf -` piping. Source disks remain untouched (6.9G free on `/`, no tar files written).

### Transfer progress (as of last check)

| Stream | Status | Target progress | Source disk |
|--------|--------|-----------------|-------------|
| sglang-patch env | RUNNING | 3.2G / 8.8G | 6.9G free (93%) |
| sglang-b1-continuity | DONE | 161M / 161M | n/a |
| sglang (no suffix) | DONE | 145M / 145M | n/a |
| Model | RUNNING | 1.1G / 11G | n/a |
| Launch scripts | DONE | 5.6K / 5.6K | n/a |

### Verified on target (already extracted)

- `/root/sglang-b1-continuity/` — contains full source tree (confirmed by `ls`)
- `/root/sglang/` — contains full source tree (confirmed by `ls`)
- `/root/models/Qwen3.5-9B-w4a16/` — model files present (chat_template.jinja, config.json, model.safetensors, etc.)
- `/root/direct-launch-gate1.sh` — launch script (50 lines, confirmed present)

## summary

Migration is **in progress** using streaming pipe approach. Three of five streams completed successfully. Two remain in progress (sglang-patch env at 3.2G/8.8G, model at 1.1G/11G). Source machine disk is untouched (6.9G free).

Once all streams complete, the verification steps will run:
1. `source /root/miniconda3/etc/profile.d/conda.sh && conda activate sglang-patch && python -c "import sglang, flashinfer, triton, torch; print('All imports OK')"`
2. `python -c "import torch; print(torch.cuda.is_available())"`
3. `md5sum` model files comparison with source

## followups

1. **Wait for remaining streams**: sglang-patch env and model still extracting on target.
2. **Run verification**: Once extraction completes, verify imports and model integrity.
3. **Update report**: Mark status as `done` once verification passes.
4. **Editable install paths**: The MAPPING points to `/root/sglang-b1-continuity/python/sglang` — verified on target, both `/root/sglang` and `/root/sglang-b1-continuity` exist.

## open_issues

1. **Remaining transfers in progress**: sglang-patch env (8.8G) and model (11G) are still streaming.
2. **Verification not yet run**: Cannot run import verification until sglang-patch env extraction completes.
3. **Transfer time**: Over the SSH pipe, the remaining ~16G (8.8G env + 11G model) will take time to transfer.
