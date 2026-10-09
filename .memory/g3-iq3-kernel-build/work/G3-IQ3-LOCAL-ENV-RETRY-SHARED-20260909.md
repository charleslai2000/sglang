# G3-IQ3-LOCAL-ENV-RETRY-SHARED-20260909

status: blocked
invocation: INV-G3-IQ3-LOCAL-ENV-REBUILD-004
epoch: E26

## Summary

The authorized hash-locked wheelhouse download was attempted once using the shared
`/mnt/data/cache/pip` path. It failed on the 366.2 MB `nvidia-cudnn-cu13` download
with an HTTPS read timeout after 245.1 MB. Per dispatch instruction, no retry was
made and the procedure stopped. The wheelhouse remains empty; the venv remains
unpopulated. No product source, service, benchmark, GPU kernel, lock, model, or
unrelated process was touched.

## Commands and evidence

Working checkout: `/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s`

```text
export PIP_CACHE_DIR=/mnt/data/cache/pip
/usr/bin/python3 -m pip download --require-hashes \
  -r /mnt/data/qwen3-g3-baseline/artifacts/torch-cu130-wheelhouse-requirements.txt \
  --dest /mnt/data/qwen3-g3-baseline/wheels --retries 2 --timeout 30
```

Output is preserved at [raw download log](raw/g3-iq3-env-retry-shared-20260909/env-rebuild-download-20260909.log).
Pip reported the shared cache is owned by `charles:dev` and not writable by this
user, so cache use was disabled; permissions were not changed and the cache was
not cleared. The network failure was:

```text
HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.
```

Observed tools: `/usr/bin/python3` 3.12.3; `/usr/local/bin/cmake` 4.4.3;
`/usr/local/cuda/bin/nvcc` CUDA 13.0 (Build cuda_13.0.r13.0/compiler.36260728_0).

Observed resources:

```text
/mnt/data/qwen3-g3-baseline/wheels: empty (8.0K directory)
/mnt/data/qwen3-g3-baseline/venv: 16M; pip 24.0 only; torch/sglang import failed
/mnt/data/cache/pip: 7.8G; charles:dev, drwxrwsr-x (unchanged)
```

## Followups

Fresh dispatch is required to resume after external network/cache authorization
or state change; this invocation performs no further attempts.

## Open issues

- Hash-verified wheelhouse and offline venv installation are incomplete because the
  required download did not finish.
- Shared cache is not writable by this user; no permission change was authorized.
