# Reproducible SM86 CPU-test overlay

Purpose: run current checkout Python kernels with the already-installed genuine SM86 DSO when this venv's editable `sglang-kernel` finder points at the sibling `opt` checkout. This is a temporary import-path overlay; it does not install/modify packages, the venv, DSO, sibling checkout, or GPU state.

Environment observed during F1-R3 preparation:
- Python: `/home/ubuntu/venvs/sglang-3090/bin/python` (Python 3.12)
- venv: `/home/ubuntu/venvs/sglang-3090`
- Torch: `2.13.0+cu129`
- `sglang-kernel`: `0.4.6.post1`
- DSO directory: `/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86`
- Repository Python root: `python/`

For a test command, from the repository root:

```bash
set -eu
overlay=$(mktemp -d /tmp/f1-kernel-overlay.XXXXXX)
trap 'rm -rf "$overlay"' EXIT
mkdir -p "$overlay/sgl_kernel"
ln -s "$PWD/python/sglang/kernels/aot/python/sgl_kernel"/* "$overlay/sgl_kernel/"
ln -s /home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86 "$overlay/sgl_kernel/sm86"
PYTHONPATH="$overlay:$PWD/python${PYTHONPATH:+:$PYTHONPATH}" \
  /home/ubuntu/venvs/sglang-3090/bin/python -m pytest -q <test paths>
```

The overlay supplies Python package files from this checkout and the real installed `sm86` binary directory. It does not emulate or mock native symbols. A successful CPU unit test using this overlay is not evidence of GPU correctness; do not use it to bypass the coordinated RTX 3090 ownership gate.

F1-R3 CPU regression command passed **142 tests** on 2026-10-09. Exact test paths are in `tasks/T001-f1-source-and-seam-audit.md`; normal pytest warnings include the environment's unknown `asyncio_mode` option and TorchScript deprecations.
