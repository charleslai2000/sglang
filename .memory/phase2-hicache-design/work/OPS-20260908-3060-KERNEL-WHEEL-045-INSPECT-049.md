# OPS-20260908-3060-KERNEL-WHEEL-045-INSPECT-049

- Task ID: `D3060-KERNEL-WHEEL-045-INSPECT-049`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Status: `done`
- Execution scope: local workstation only; no private 3060 host access.
- Product source/install state: unchanged; wheel was not installed.
- Temporary work directory: `/tmp/sglang-kernel-0.4.5-inspect-n7YaHh`

## Target selected

Source queried: `https://pypi.org/pypi/sglang-kernel/0.4.5/json`

The JSON response identified exactly one requested Linux x86_64 `cp310-abi3` wheel:

- Filename: `sglang_kernel-0.4.5-cp310-abi3-manylinux2014_x86_64.whl`
- URL: `https://files.pythonhosted.org/packages/ab/62/c99dac5404b004f1c8e0d846c18566f2678374cde919ed03db373084ba89/sglang_kernel-0.4.5-cp310-abi3-manylinux2014_x86_64.whl`
- PyPI size: `382990222` bytes
- PyPI SHA256: `5927a14dfff92ced8b1f7c7d5844144bc574ec58e604d4fd53e6f53c709003a8`

The other release artifact was aarch64 and was not downloaded.

## Verification evidence

Downloaded path:

`/tmp/sglang-kernel-0.4.5-inspect-n7YaHh/sglang_kernel-0.4.5-cp310-abi3-manylinux2014_x86_64.whl`

Observed:

- `stat`: size `382990222` bytes — matches PyPI JSON.
- `sha256sum`: `5927a14dfff92ced8b1f7c7d5844144bc574ec58e604d4fd53e6f53c709003a8` — matches PyPI JSON.
- `unzip -t`: `No errors detected in compressed data`.
- Six ELF shared objects were found and inspected.

## Shared-library inspection

For every ELF file below, `readelf -d` `DT_NEEDED` and `strings -a` both reported the same CUDA-related names:

```
libcuda.so.1
libcudart.so.13
libnvrtc.so.13
```

ELF files:

```
sgl_kernel/flash_ops.abi3.so
sgl_kernel/flashmla_ops.abi3.so
sgl_kernel/infllm_ops.cpython-310-x86_64-linux-gnu.so
sgl_kernel/sm100/common_ops.abi3.so
sgl_kernel/sm90/common_ops.abi3.so
sgl_kernel/spatial_ops.abi3.so
```

Conclusion: the wheel records `libnvrtc.so.13` and `libcudart.so.13`; the observed CUDA major is **13**. `libcuda.so.1` is the driver API SONAME and does not encode the CUDA toolkit major.

## Commands executed

```sh
curl --fail --location --max-time 240 --silent --show-error \
  https://pypi.org/pypi/sglang-kernel/0.4.5/json -o /tmp/.../pypi.json
curl --fail --location --max-time 240 --silent --show-error <selected-wheel-url> \
  -o /tmp/.../sglang_kernel-0.4.5-cp310-abi3-manylinux2014_x86_64.whl
stat -c 'size=%s path=%n' <wheel>
sha256sum <wheel>
unzip -t <wheel>
unzip -q <wheel> -d /tmp/.../unpacked
readelf -d <each ELF>        # filtered to CUDA/NVRTC NEEDED names
strings -a <each ELF>        # filtered to libcuda/libcudart/libnvrtc names
```

## Changed resources / rollback

- Created only the temporary `/tmp/sglang-kernel-0.4.5-inspect-n7YaHh` download/extraction directory and this report.
- No product source, environment, package installation, or private host resource was changed.
- No rollback action is required. Temporary files were intentionally retained for evidence and were not deleted.

## Followups and open issues

- Followups: none within this Task ID.
- Open issues: none for the requested inspection.
- Extra work requires a new Task ID.
