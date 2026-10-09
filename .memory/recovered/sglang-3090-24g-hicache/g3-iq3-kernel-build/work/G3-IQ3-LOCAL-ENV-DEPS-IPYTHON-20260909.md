# G3-IQ3-LOCAL-ENV-DEPS-IPYTHON-20260909

status: blocked
task_id: G3-IQ3-LOCAL-ENV-DEPS-IPYTHON
invocation_id: INV-G3-IQ3-LOCAL-ENV-DEPS-IPYTHON-001
epoch: E41
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s

`pwd` matched the bound workdir. Installed only `IPython` using `sg dev -c` and
the shared pip cache. `import torch, sglang` progressed to
`ModuleNotFoundError: No module named 'aiohttp'`.

Logs: `/mnt/data/qwen3-g3-baseline/artifacts/env-rebuild-ipython-001-20260909.log`
and `env-rebuild-import-ipython-001-20260909.log`.

Followup: fresh dispatch to install only `aiohttp`.

Open issue: import acceptance incomplete.
