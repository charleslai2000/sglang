# G3-IQ3-LOCAL-SMOKE-RETRY3-20260909

## Status

blocked

## Scope and procedure

Local-only preflight for the isolated RTX 3090 smoke. Per contract, ran the no-GPU
entry check before acquiring `/mnt/data/gpu/3090.lock`; no server, benchmark, or
GPU process was started.

Command:

```text
CUDA_VISIBLE_DEVICES='' /mnt/data/qwen3-g3-baseline/venv/bin/python -m sglang.launch_server --help
```

## Evidence

- Exit status: `1`
- Raw stdout/stderr: `work/raw/g3-iq3-local-smoke-retry3-20260909/preflight-help.txt`
- Raw exit code: `work/raw/g3-iq3-local-smoke-retry3-20260909/preflight.rc`
- Failure: `ModuleNotFoundError: No module named 'sentencepiece'` while importing
  `sglang.srt.configs.internvl`.

## Resource safety

- GPU lock was not acquired.
- No GPU process or SGLang server was launched.
- No user/other process was stopped or modified.
- No repository/product files were changed.

## Follow-up

Install the missing approved runtime dependency `sentencepiece` in the venv, then
rerun this same preflight under a fresh invocation ID before any GPU queue attempt.

## Open issues

The requested smoke cannot proceed until the import dependency is available.
