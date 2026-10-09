# OPS-20260908-3060-ENV-PROVISION

## Invocation

- Task ID: `D3060-ENV-PROVISION-007`
- Orchestration epoch: `20260908-3060`
- Role: `devops-executor`
- Target: `root@i-1.gpushare.com:27460` (RTX 3060 only)
- Status: **blocked**
- Entry: `ACCEPT`

## Scope and safety

Executed only the authorized dedicated-runtime provisioning attempt. The old
`/root/miniconda3/envs/sglang-3060-4b` directory was preserved. No Qwen
weights were downloaded, no server or benchmark was started, and no 3090
resource was touched. The synced source at
`/root/sglang-3060-12g-hicache/python` was not modified.

## Environment

- Requested dedicated path: `/root/miniconda3/envs/sglang-3060-4b-runtime`
- Method: recoverable prefix-style runtime using `/usr/local/bin/python`
  symlinked as `bin/python`; the preferred `python -m venv
  --system-site-packages` failed during `ensurepip`.
- Environment size after attempted provisioning: `121M`
- Before disk: `overlay 30G total, 624M used, 30G available, 3% use`
- After disk: `overlay 30G total, 879M used, 29G available, 3% use`
- Source install mode attempted: editable, `--no-deps`, with
  `SGLANG_BUILD_RUST_EXTS=none` and `--no-build-isolation`.

## Commands and evidence

Baseline:

```text
/usr/local/bin/python --version
Python 3.11.11
/usr/local/bin/python -c 'import torch; print(torch.__version__, torch.version.cuda)'
2.5.1+cu124 12.4
```

The venv attempt failed before package installation:

```text
Error: Command [...] '/root/miniconda3/envs/sglang-3060-4b-runtime/bin/python', '-m', 'ensurepip' [...]
returned non-zero exit status 1.
```

The fallback prefix installed these requested tools successfully:

```text
Successfully installed black-26.5.1 isort-9.0.1 scikit-build-core-1.0.3 transformers-5.12.1
```

Editable source installation then succeeded:

```text
Created wheel for sglang: filename=sglang-0.0.0-0.editable-py3-none-any.whl
Successfully installed sglang-0.0.0
```

The source install required the source-supported Rust bypass because `cargo`
is absent. No source files were changed.

Final verification:

```text
interpreter: /root/miniconda3/envs/sglang-3060-4b-runtime/bin/python
version: 3.11.11
stdlib: /usr/lib/python3.11
prefix site-packages: /root/miniconda3/envs/sglang-3060-4b-runtime/lib/python3.11/site-packages
pip: No module named pip
import smoke through the runtime path: ModuleNotFoundError: No module named 'torch'
```

The old path remained a directory with its prior package-only contents and no
executable Python; it was not deleted or repaired.

## Current blockers

1. The preferred venv mechanism is unavailable because host `ensurepip` fails.
2. The fallback prefix is not yet a complete executable runtime: its
   `bin/python` works, but `pip` is not importable through that runtime and the
   final smoke command did not see system-site `torch`.
3. The source metadata requests `torch==2.13.0`, while the host exposes
   `torch 2.5.1+cu124`; resolving that mismatch would require a separate
   authorization and potentially a large download.
4. Because the final interpreter/pip/torch/sglang smoke verification did not
   pass, the environment is **not accepted as ready** for the next AOT build.

## Followups

Fresh Task ID required to repair the runtime isolation/path wiring and resolve
the Torch compatibility decision. No further action was taken in this Task ID.

## Open issues

- No AOT build was started.
- No kernel artifact was produced.
- `pip`, `torch`, and `sglang` imports were not all verified through the
  dedicated runtime path.
