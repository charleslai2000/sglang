# Migration Verification Report — sglang on RTX 3090 (175.155.64.171:22151)

**Date:** 2026-09-05
**Verifier:** devops (orchestrator-dispatched)
**Target:** root@175.155.64.171:22151
**Mode:** read-only verification (no modifications)

---

## Status: blocked

Migration is **incomplete**. Two critical failures detected:
1. Conda environment `sglang-patch` is missing its Python binary (`bin/python`), making the env non-functional.
2. Model file `model.safetensors` is truncated (2.6G on target vs 11G on source); md5 hash mismatch confirms incomplete transfer.

---

## Step-by-Step Evidence

### Step 1: Directory Integrity & Size Check

**Command:**
```
sshpass -p 'K0@dx' ssh -p 22151 -o StrictHostKeyChecking=no root@175.155.64.171 \
  "du -sh /root/miniconda3/envs/sglang-patch /root/sglang-b1-continuity /root/sglang /root/models/Qwen3.5-9B-w4a16"
```

**Real output:**
```
6.1G	/root/miniconda3/envs/sglang-patch
161M	/root/sglang-b1-continuity
145M	/root/sglang
2.6G	/root/models/Qwen3.5-9B-w4a16
```

**Judgment:**
- env: 6.1G vs expected 8.8G — **FAIL** (significantly smaller)
- source (sglang-b1-continuity): 161M vs expected 161M — PASS
- package root (sglang): 145M vs expected 145M — PASS
- model: 2.6G vs expected 11G — **FAIL** (truncated, ~24% of expected)

---

### Step 2: Env Completeness

#### 2a: Python binary and version

**Command:**
```
ls /root/miniconda3/envs/sglang-patch/bin/python && /root/miniconda3/envs/sglang-patch/bin/python --version
```

**Real output:**
```
ls: cannot access '/root/miniconda3/envs/sglang-patch/bin/python': No such file or directory
```
**Exit code:** 2

**Judgment: FAIL** — `bin/` directory does not exist in the env. Python binary is missing. The conda-meta/history confirms Python 3.10.21 was installed (python-3.10.21-h17756b0_0.json present in conda-meta), but the actual binary files were not transferred.

#### 2b: Critical packages in site-packages

**Command:**
```
ls /root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/ | grep -E "sgl_kernel|flashinfer|triton|torch"
```

**Real output:**
```
flashinfer
flashinfer_python-0.6.17.dist-info
sgl_kernel
tokenspeed_triton
tokenspeed_triton-3.8.10.post20260721.dist-info
torch
torch-2.13.0.dist-info
torch_c_dlpack_ext
torch_c_dlpack_ext-0.1.5.dist-info
torch_memory_saver
torch_memory_saver_hook_mode_preload.abi3.so
torch_memory_saver_hook_mode_preload_cu12.abi3.so
torch_memory_saver_hook_mode_preload_cu13.abi3.so
torch_memory_saver_hook_mode_torch.abi3.so
torch_memory_saver_hook_mode_torch_cu12.abi3.so
torch_memory_saver_hook_mode_torch_cu13.abi3.so
torchaudio
torchaudio-2.11.0.dist-info
torchcodec
torchcodec-0.15.0.dist-info
torchgen
torchvision
torchvision-0.28.0.dist-info
torchvision.libs
triton
triton-3.7.1.dist-info
triton_kernels
```

**Judgment: PASS** — All critical packages (sgl_kernel, flashinfer, triton, torch) are present in site-packages.

#### 2c: Editable finder MAPPING

**Command:**
```
ls /root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/__editable___sglang_0_0_0_dev0_finder.py
```

**Real output:**
```
/root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/__editable___sglang_0_0_0_dev0_finder.py
```

**Judgment: PASS** — File exists. Content verified: MAPPING points `sglang` → `/root/sglang-b1-continuity/python/sglang` (correct).

---

### Step 3: Import Verification

#### 3a: sglang + flashinfer + triton + torch import

**Command:**
```
source /root/miniconda3/etc/profile.d/conda.sh && conda activate sglang-patch && python -c "import sglang, flashinfer, triton, torch; print('ALL_IMPORTS_OK')"
```

**Real output:**
```
bash: line 1: python: command not found
```
**Exit code:** 127

**Judgment: FAIL** — `python` command not found because `bin/python` is missing from the env. The `conda activate` succeeded (no error from conda itself), but the activated env has no `python` binary on PATH.

#### 3b: CUDA availability

**Command:**
```
source /root/miniconda3/etc/profile.d/conda.sh && conda activate sglang-patch && python -c "import torch; print('CUDA_AVAILABLE=', torch.cuda.is_available())"
```

**Real output:**
```
bash: line 1: python: command not found
```
**Exit code:** 127

**Judgment: FAIL** — Same root cause: no `python` binary in env. Cannot test CUDA availability.

---

### Step 4: Model Integrity (md5sum)

#### Target machine (175.155.64.171:22151)

**Command:**
```
md5sum /root/models/Qwen3.5-9B-w4a16/*.safetensors
```

**Real output:**
```
1cbe6f05515488846d75a109290e6e6  /root/models/Qwen3.5-9B-w4a16/model.safetensors
50767e137d5a8a4885c065fcd0f29e81  /root/models/Qwen3.5-9B-w4a16/model_mtp.safetensors
```

#### Source machine (24052, same host, port 24052)

**Command:**
```
sshpass -p 'K0@dx' ssh -p 24052 -o StrictHostKeyChecking=no root@175.155.64.171 "md5sum /root/models/Qwen3.5-9B-w4a16/*.safetensors"
```

**Real output:**
```
5e6de91cf0e7f52575f37033683c6ef2  /root/models/Qwen3.5-9B-w4a16/model.safetensors
50767e137d5a8a4885c065fcd0f29e81  /root/models/Qwen3.5-9B-w4a16/model_mtp.safetensors
```

**Comparison:**
| File | Target md5 | Source md5 | Match? |
|------|-----------|-----------|--------|
| model.safetensors | `1cbe6f05515488846d75a109290e6e6` | `5e6de91cf0e7f52575f37033683c6ef2` | **NO** |
| model_mtp.safetensors | `50767e137d5a8a4885c065fcd0f29e81` | `50767e137d5a8a4885c065fcd0f29e81` | YES |

**Judgment: FAIL** — `model.safetensors` md5 mismatch. The target file is truncated (2.6G total model dir vs 11G on source; model.safetensors alone is 2.2G vs 11G on source). `model_mtp.safetensors` transferred correctly.

---

### Step 5: Disk Space

**Command:**
```
df -h / /data
```

**Real output:**
```
Filesystem      Size  Used Avail Use% Mounted on
overlay          98G   44G   50G  47% /
/dev/sda        295G   25G  258G   9% /data
```

**Judgment: PASS** — Ample space on both `/` (50G free) and `/data` (258G free). Disk space was not a limiting factor for the transfer.

---

## Final Conclusion

**Migration is NOT complete or usable.** The env is missing its Python binary, and the model file `model.safetensors` is truncated with a different md5 hash than the source. The transfer of `model.safetensors` (11G on source, 2.2G on target) was interrupted or failed.

The conda environment `sglang-patch` has its `lib/` and `conda-meta/` directories present (including Python 3.10.21 metadata and all critical packages), but the `bin/` directory with the actual `python3.10` binary was not transferred. This is consistent with an interrupted `rsync`/`cp` that did not complete — the `bin/` directory (small, early in transfer) may have been skipped or the transfer was killed before finishing the large model file.

---

## Followups (for orchestrator decision)

1. **Re-transfer `model.safetensors`**: The source file is 11G on 24052. Use `rsync -av --progress` (or `scp -P 24052`) from source to target to resume/complete the transfer. Verify md5 after transfer.
2. **Restore `bin/` directory in conda env**: The conda env metadata is intact but `bin/python3.10` is missing. Options:
   - (a) Re-run `conda create --name sglang-patch --clone <backup>` on target if a backup exists.
   - (b) Reinstall via conda: `conda install -n sglang-patch python=3.10.21 -y` (requires network or local conda cache).
   - (c) Copy `bin/` from a known-good source if one exists on 24052 (`/root/miniconda3/envs/sglang-patch/bin/`).
3. **After both fixes, re-run Steps 2a, 3a, 3b, and 4 to confirm**.
4. **Do not attempt to launch the engine** (launch script `/root/direct-launch-gate1.sh` exists and references `/root/miniconda3/envs/sglang-patch/bin/python3` which is currently missing).

---

## Open Issues

- The launch script `/root/direct-launch-gate1.sh` references `CUDA_HOME=/root/miniconda3/envs/sglang-dev/lib/...` (a different env name `sglang-dev`), not `sglang-patch`. This may be a separate pre-existing config issue, not caused by migration.
- The source machine SSH port for migration is 24052 (discovered from project files); the migration agent may have used a different port or method. The exact transfer command used by the migration agent is unknown.
