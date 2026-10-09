# G3-IQ3-LOCAL-DEPS-20260909

Invocation: `INV-G3-IQ3-LOCAL-DEPS-001`  Epoch: `E13`

## Status

done

## Scope

Only the isolated venv `/mnt/data/qwen3-g3-baseline/venv` was modified. No GPU
process, service, driver, CUDA installation, or repository product source was
changed.

## Procedure and evidence

Installed from the configured PyPI index with:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -m pip install dill
```

The resolver downloaded `dill-0.4.1-py3-none-any.whl` (120 kB) and reported
successful installation. The package metadata records the project URL as
`https://github.com/uqfoundation/dill`. The exact pip output is preserved in
`raw/g3-iq3-local-deps-20260909/pip-install.log`; installed metadata is in
`pip-show.log`.

Verification:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -c 'import dill; print(dill.__version__)'
=> 0.4.1
```

Raw verification is in `raw/g3-iq3-local-deps-20260909/import.log`; installed
file hashes are in `site-hashes.log`.

## Followups

The venv is ready for the previously blocked smoke dependency. Any smoke or
GPU execution requires a fresh dispatch.

## Open issues

The PyPI installer output did not expose a wheel SHA-256 in the normal console
output; no hash was fabricated.
