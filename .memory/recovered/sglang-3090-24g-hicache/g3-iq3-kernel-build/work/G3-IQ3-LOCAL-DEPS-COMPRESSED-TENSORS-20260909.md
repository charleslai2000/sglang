# G3-IQ3-LOCAL-DEPS-COMPRESSED-TENSORS-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-DEPS-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-DEPS-005`
- Epoch: `E18`
- Role: `devops-executor`, capability L4

## Result

**Invocation status: done.** Installed the exact required package `compressed-tensors==0.18.0` into `/mnt/data/qwen3-g3-baseline/venv`.

## Exact procedure and evidence

Command:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple compressed-tensors==0.18.0
```

The install fetched `compressed_tensors-0.18.0-py3-none-any.whl` and its missing dependency `loguru-0.7.3`; all other declared dependencies were already present. The package source/index was PyPI (`https://pypi.org/simple`).

Verification command succeeded:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -c 'import compressed_tensors, importlib.metadata as m; print(compressed_tensors.__file__); print(m.version("compressed-tensors"))'
```

Observed:

```text
/mnt/data/qwen3-g3-baseline/venv/lib/python3.12/site-packages/compressed_tensors/__init__.py
0.18.0
```

Downloaded wheel evidence SHA-256:

```text
91168237c2d815614c44dfc354c61c613085c811dabbb2ccdb929e9aaa313b8f  compressed_tensors-0.18.0-py3-none-any.whl
```

## Changed resources

- `/mnt/data/qwen3-g3-baseline/venv`: installed `compressed-tensors==0.18.0` and `loguru==0.7.3`.
- No GPU process or service was started/stopped.
- No driver, CUDA, repository, model, or production resource was changed.

Raw command logs and wheel hash are under:

`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-deps-compressed-tensors-20260909/`

## Open issues / followups

- Pip reported pre-existing unrelated missing/incompatible SGLang dependencies; this invocation did not alter them.
- Follow-on smoke/deployment work requires a fresh invocation/task dispatch.
