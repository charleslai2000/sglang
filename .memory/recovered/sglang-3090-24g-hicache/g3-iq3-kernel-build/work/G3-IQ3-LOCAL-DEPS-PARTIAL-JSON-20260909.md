# G3-IQ3-LOCAL-DEPS-PARTIAL-JSON-20260909

Status: done

## Scope

Installed only the missing `partial_json_parser` dependency into
`/mnt/data/qwen3-g3-baseline/venv`. No GPU, service, driver, CUDA, or repository
changes were made.

## Procedure and evidence

- Python: 3.12.3 at `/mnt/data/qwen3-g3-baseline/venv/bin/python`.
- Initial offline lookup confirmed the package was absent from the existing wheelhouse.
- Downloaded the official PyPI wheel with pip:
  `partial_json_parser-0.2.1.1.post7-py3-none-any.whl`
- Wheel SHA-256:
  `145119e5eabcf80cbb13844a6b50a85c68bf99d376f8ed771e2a3c3b03e653ae`
- Installed using `--no-index --require-hashes` with the pinned requirement in
  `raw/g3-iq3-local-deps-partial-json-20260909/requirements.txt`.
- Import verification passed:
  `partial_json_parser.__file__` resolves under the target venv and metadata
  version is `0.2.1.1.post7`.

## Artifacts

Raw command logs, pinned requirement, wheel hash, and pip metadata are under:
`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-deps-partial-json-20260909/`.

## Open issues

Pip reported pre-existing unrelated missing/incompatible SGLang dependencies;
this invocation did not install or alter them. A fresh invocation is required
for any further dependency work.
