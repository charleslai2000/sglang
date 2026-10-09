# G3-IQ3-LOCAL-DEPS-SENTENCEPIECE-20260909

Status: done

## Scope

Installed only `sentencepiece` into `/mnt/data/qwen3-g3-baseline/venv`. No GPU, service, driver, CUDA, or repository changes were made.

## Exact procedure and evidence

```text
python -m pip download --only-binary=:all: --dest .memory/.../raw/... sentencepiece
python -m pip install --no-deps sentencepiece-0.2.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
python -c 'import sentencepiece; print(sentencepiece.__version__)'
```

Resolved artifact:

```text
sentencepiece-0.2.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
SHA256 c8a168b040bc61681293f79a949b5d911c8e25086f4260285b8d97ab5f1195da
Source: pip configured package index (download log preserved); exact resolved URL was not emitted by pip's normal download output.
```

Verification:

```text
import sentencepiece; print(sentencepiece.__version__) => 0.2.2
pip show => Version: 0.2.2; Location: /mnt/data/qwen3-g3-baseline/venv/lib/python3.12/site-packages
```

Raw evidence: `raw/g3-iq3-local-deps-sentencepiece-20260909/` (`pip-download.log`, `pip-install.log`, `import-check.txt`, `pip-show.txt`, `SHA256SUMS`, `all-sha256.txt`, wheel).

## Open issues

The original launch preflight's `ModuleNotFoundError: sentencepiece` is resolved. No launch or GPU test was performed under this invocation; follow-on execution requires a fresh invocation.
