# G3-IQ3-LOCAL-SMOKE-20260909

## Invocation

- Stable task: `G3-IQ3-LOCAL-SMOKE-20260909`
- Invocation: `INV-G3-IQ3-LOCAL-SMOKE-001`
- Epoch: `E13`
- Role/capability: `devops-executor / L4`
- Invocation status: `blocked`

## Scope and preflight

Authorized target was local GPU1 (RTX 3090), queue lock `/mnt/data/gpu/3090.lock`,
port `18035`, and artifact directory `/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909/`.
No lock was acquired, no service was started, no user process was touched, and no
driver/CUDA/model files were changed.

Observed 2026-09-09 18:21:42 +08:00:

```text
GPU 1: NVIDIA GeForce RTX 3090
GPU1 memory 53 / 24576 MiB, utilization 0%
port 18035: not listening
model present: /mnt/data/qwen3-g3-baseline/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf (11G)
torch: 2.13.0+cu130, torch.cuda.is_available()=True
```

## Blocking command and evidence

Command:

```text
/mnt/data/qwen3-g3-baseline/venv/bin/python -m sglang.launch_server --help
```

The editable checkout failed during import before argument parsing:

```text
ModuleNotFoundError: No module named 'dill'
```

Import chain: `sglang.launch_server` -> `sglang.srt.configs.deepseek_ocr` ->
`sglang.srt.sampling.custom_logit_processor` -> `import dill`.

Because the exact launch entrypoint cannot import, the authorized smoke gate cannot
be attempted without an environment repair. No alternative workload or random-text
fallback was used.

## Required follow-up

Install the approved `dill` dependency into the prepared venv (preferably via the
root-provided verified wheelhouse), then dispatch a fresh invocation ID for the
same queued smoke procedure. Re-run preflight and preserve the new command/output.

## Open issues

- `dill` is absent from `/mnt/data/qwen3-g3-baseline/venv`.
- Native SM86 extension load/compilation and one-request `random-ids` completion are
  untested in this invocation.
