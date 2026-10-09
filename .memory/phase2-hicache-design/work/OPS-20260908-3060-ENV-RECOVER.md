# OPS-20260908-3060-ENV-RECOVER

Task ID: D3060-ENV-PROVISION-009  
Orchestration epoch: 20260908-3060  
Role: devops-executor  
Status: done

## Scope and authorization

Recovered only `/root/sglang-env-3060-4b` on `root@i-1.gpushare.com:27460`.
The password was supplied to `sshpass` through an environment variable and was not
printed or recorded. No model download, large package installation, kernel build,
server start, benchmark, 3090 change, or modification of
`/root/miniconda3/envs/sglang-3060-4b` was performed.

## Commands and outputs

Initial inspection:

```text
/root/sglang-env-3060-4b contained bin/, include/, lib/, lib64 -> lib, and pyvenv.cfg only.
/usr/local/bin/python: Python 3.11.11
/root/miniconda3/envs/sglang-3060-4b: present
```

Recovery commands executed remotely:

```text
mv /root/sglang-env-3060-4b /root/sglang-env-3060-4b.partial-20260908-203818
/usr/local/bin/python -m venv --system-site-packages --without-pip /root/sglang-env-3060-4b
/usr/local/bin/python -m pip --python /root/sglang-env-3060-4b install --force-reinstall pip
```

Pip result:

```text
Successfully installed pip-26.2.1
pip 26.2.1 from /root/sglang-env-3060-4b/lib/python3.11/site-packages/pip (python 3.11)
```

## Verification evidence

All final verification commands exited successfully.

```text
venv: /root/sglang-env-3060-4b exists
python: /root/sglang-env-3060-4b/bin/python -> /usr/local/bin/python (executable)
prefix: /root/sglang-env-3060-4b
base_prefix: /usr
stdlib=ok
pip 26.2.1 from /root/sglang-env-3060-4b/lib/python3.11/site-packages/pip (python 3.11)
torch=2.5.1+cu124
cuda_available=True
cuda_version=12.4
gpu_count=1
gpu_0=NVIDIA GeForce RTX 3060 capability=(8, 6)
nvidia-smi: NVIDIA GeForce RTX 3060, 8.6
/root/miniconda3/envs/sglang-3060-4b: present
```

## Changed resources

- Created `/root/sglang-env-3060-4b` as a system-site-packages venv without ensurepip.
- Installed venv-local pip using the system pip `--python` target method.
- Moved the original partial directory, without deletion, to
  `/root/sglang-env-3060-4b.partial-20260908-203818`.
- Wrote this report only to the task-specified path.

## Followups

None required for this task.

## Open issues

None observed.
