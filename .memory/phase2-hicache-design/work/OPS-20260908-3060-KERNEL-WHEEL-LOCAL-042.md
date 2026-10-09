# OPS-20260908-3060-KERNEL-WHEEL-LOCAL-042

- Task ID: `D3060-KERNEL-WHEEL-LOCAL-042`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Scope: local-only; no product-source changes; no package installation; no deletion
- Status: `done`

## Procedure and commands

1. Queried current PyPI JSON with a bounded request:

   `curl --fail --silent --show-error --location --max-time 30 'https://pypi.org/pypi/sglang-kernel/0.4.6.post1/json' -o /tmp/sglang-kernel-0.4.6.post1.json`

2. Enumerated `.urls[]` using `jq`.

3. Selected the existing `cp310-abi3-manylinux2014_x86_64` wheel and downloaded it with:

   `curl --fail --silent --show-error --location --max-time 120 --output /tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl '<selected URL>'`

   The command refused to overwrite an existing destination; it was absent.

4. Verified with `stat`, `sha256sum`, and `unzip -t`.

## PyPI JSON file inventory

| filename | URL | size | sha256 |
|---|---|---:|---|
| `sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_aarch64.whl` | `https://files.pythonhosted.org/packages/5e/a9/5ef33ef2e387455c0c6317802db2faf37dcc91867c7f09c3ec4e6b6da1a2/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_aarch64.whl` | 30741582 | `7eccd61408b44b55ab35cdbcf8a05243ce2a9a5e781fabb00da375af7d7130a1` |
| `sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl` | `https://files.pythonhosted.org/packages/d9/d9/fd8d0b81f6e14bb1f5afcdbe99e7cd8a3862b7b70450660217ad70df59ee/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl` | 377094734 | `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04` |

## Selected artifact and evidence

- Downloaded path: `/tmp/sglang_kernel-0.4.6.post1-cp310-abi3-manylinux2014_x86_64.whl`
- `stat`: `size=377094734`; matches PyPI JSON size `377094734`.
- `sha256sum`: `5fee1007113c988bf6d448eca4706f7959631d449a429eb790a70bf89ab0ef04`; exact match to PyPI JSON.
- `unzip -t`: completed with `No errors detected in compressed data`.
- Changed resources: created the `/tmp` wheel and the report file only. Product source was not modified. No packages were installed. No files were deleted.

## Followups

- None.

## Open issues

- None.
