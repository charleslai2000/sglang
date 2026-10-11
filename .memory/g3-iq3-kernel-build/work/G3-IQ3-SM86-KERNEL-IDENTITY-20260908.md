# G3 IQ3 SM86 kernel identity — 2026-09-08

Status: done

## Scope and invariant

Read-only checks were executed on the explicit experimental host
`175.155.64.171:22109`. Frozen v1 service PID `503601` on loopback port `8035`
was not stopped, restarted, reconfigured, or benchmarked. No files were changed
on the host.

## Commands and observations

The deployed interpreter command was:

```sh
/data/sglang-qwen35-env/bin/python -c \
  'import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0))'
```

Observed: PyTorch `2.13.0+cu130`, CUDA `13.0`, GPU `NVIDIA GeForce RTX 3090`,
capability **`(8, 6)`**. Driver: `580.173.02`.

The actual loaded extension, confirmed from `/proc/503601/maps`, is:

```text
/data/sglang-qwen35-env/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so
```

File size: `17,058,824` bytes. SHA-256:
`7107039cd6d78c62cbb96bfa677cfdbbd4ae355c50e1ce9481590e033f61feff`.

`/opt/cuda-conda/bin/cuobjdump` was available (the bare `cuobjdump` was not on
PATH). Exact inspection command:

```sh
/opt/cuda-conda/bin/cuobjdump --list-elf \
  /data/sglang-qwen35-env/lib/python3.12/site-packages/sgl_kernel/sm100/common_ops.abi3.so
```

The fatbinary contains native cubins for `sm_80`, `sm_89`, `sm_90`, `sm_100`,
and `sm_120` (47, 47, 94, 47, and 47 entries respectively). It contains **no
native `sm_86` cubin**. The inspected list therefore does not support claiming
an SM86-native build. The RTX 3090 must use the available compatible image/JIT
fallback path; this report does not infer whether the driver chooses `sm_80`
compatibility or a PTX image because the extension's `cuobjdump --dump-ptx`
output did not expose a target in the bounded read-only extraction.

## Raw evidence

Raw command outputs and hashes are under:

`.memory/g3-baseline-20260907/work/raw/g3-iq3-sm86-kernel-identity-20260908/`

Notable files:

- `remote-kernel-check.txt`
- `sass-ptx-arch.txt`
- `SHA256SUMS`

## Conclusion

P0 is complete: GPU capability is `(8,6)`, while the actual loaded `common_ops`
fatbinary has no `sm_86` native cubin. A build/dispatch correction may be
warranted, but implementing or rebuilding it is outside this read-only task and
requires a fresh Task ID.

Invocation status: **done**
