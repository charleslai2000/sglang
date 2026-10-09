# G3-IQ3-LOCAL-DEPS-OPENAI-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-DEPS-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-DEPS-002`
- Epoch: `E14`
- Role: `devops-executor`, capability L4

## Scope and command

Only `/mnt/data/qwen3-g3-baseline/venv` and this report's raw directory were
modified. No GPU, service, driver, CUDA, or repository operations were run.

Install command:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -m pip install --no-cache-dir --disable-pip-version-check --index-url https://pypi.org/simple openai==2.6.1
```

The package was obtained from the PyPI simple index. A reproducible wheel copy
was downloaded for evidence as:

```text
https://files.pythonhosted.org/packages/15/0e/331df43df633e6105ff9cf45e0ce57762bd126a45ac16b25a43f6738d8a2/openai-2.6.1-py3-none-any.whl
```

The exact resolved URL is recorded by pip's download metadata/logs where
available; wheel SHA-256 is `904e4b5254a8416746a2f05649594fa41b19d799843cd134dac86167e094edef`.

## Verification

```text
python -c 'import openai; print(openai.__version__)' -> 2.6.1
pip show openai -> Version: 2.6.1
```

Installed wheel RECORD SHA-256:
`89efacba3237fe1d3c20c9f20a719c3dbb1da760b56e187d7ab7577f720b026f`.

## Status

done

## Raw evidence

Directory:
`.memory/g3-baseline-20260907/work/raw/g3-iq3-local-deps-openai-20260909/`

Includes `pip-install.log`, `pip-download.log`, `verification.txt`, and
`openai-2.6.1-py3-none-any.whl`.

## Open issues / followups

- Pip reported pre-existing missing/incompatible SGLang optional dependencies;
  those were not changed under this invocation.
- Follow-up smoke testing requires a fresh invocation and remains outside this
  package-install task.
