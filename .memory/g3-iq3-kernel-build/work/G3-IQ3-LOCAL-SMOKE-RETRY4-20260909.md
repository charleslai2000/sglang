# G3-IQ3-LOCAL-SMOKE-RETRY4-20260909

status: blocked
invocation_id: INV-G3-IQ3-LOCAL-SMOKE-005
task_id: G3-IQ3-LOCAL-SMOKE-20260909
epoch: E17

## Scope

Executed only the authorized no-GPU launch preflight. Because it failed, the
GPU lock was not acquired and no server or benchmark was started.

## Exact command

```sh
CUDA_VISIBLE_DEVICES='' /mnt/data/qwen3-g3-baseline/venv/bin/python \
  -m sglang.launch_server --help
```

Exit code: `1`.

## Observed failure

The checkout reaches `prepare_server_args()` and then fails while argparse is
formatting help:

```text
TypeError: %o format: an integer is required, not dict
```

Full stdout/stderr and return code are preserved in:

```text
/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry4/preflight.stdout
/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry4/preflight.stderr
/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry4/preflight.rc
```

## Safety verification

- GPU lock `/mnt/data/gpu/3090.lock`: not acquired.
- No launch_server process was started by this invocation.
- No benchmark request was sent.
- No product, driver, CUDA, or other process was modified.
- No GPU1/RSS/health/loads/result telemetry exists because the gate failed.

## Follow-up

Fresh invocation required for any retry. The next authorized action is to
repair or work around this checkout-local help-formatting failure, then rerun
the exact preflight before considering the GPU smoke.

## Open issues

The `--help` preflight is currently not executable under Python 3.12 due to the
`%o` formatting collision. No alternative launch was selected in this
invocation.
