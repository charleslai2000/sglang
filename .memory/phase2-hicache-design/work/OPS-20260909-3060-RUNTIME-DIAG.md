# OPS-20260909-3060-RUNTIME-DIAG

- Task ID: `D3060-OPS-085`
- Orchestration epoch: `2026-09-09`
- Role: `devops-executor`
- Invocation status: `done`
- Scope: read-only SSH BatchMode diagnostics to `root@i-1.gpushare.com:27460` using `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Remote host: `I2aff9805ac001019d1`
- Remote timestamp: `2026-09-09T02:14:03+08:00`

## Method and authorization

Executed one bounded SSH session (connection timeout 10s, outer timeout 90s, remote timeout 75s) containing only read-only path inspection, bounded Python diagnostics, package metadata reads, and `nvidia-smi`. No install, edit, delete, reboot, source modification, or unbounded server launch was performed.

## Evidence

### GPU state

Initial query:

```text
GPU 0: NVIDIA GeForce RTX 3060 (UUID: GPU-11b93eab-99ae-a34f-5c5f-df9b43b28e62)
0, NVIDIA GeForce RTX 3060, 550.144.03, 12288 MiB, 2 MiB, 0 %
```

Post-check after all diagnostics:

```text
0, NVIDIA GeForce RTX 3060, 2 MiB, 0 %
```

GPU was left idle.

### Authorized target paths

```text
directory drwxr-xr-x root:root 74 /root/sglang-env-3060-4b
directory drwxr-xr-x root:root 4096 /root/sglang-3060-12g-hicache
directory drwxr-xr-x root:root 24 /hy-tmp/ops-081-sm86-import-20260909
```

The staged path contains `sgl_kernel/` Python modules and `spatial_ops.cpython-311-x86_64-linux-gnu.so`.

### `python -m sglang.launch_server --help`

`/root/sglang-env-3060-4b/bin/python` produced this exact traceback and exited 1:

```text
/root/sglang-3060-12g-hicache/python/sglang/launch_server.py:63: UserWarning: 'python -m sglang.launch_server' is still supported, but 'sglang serve' is the recommended entrypoint.
  Example: sglang serve --model-path <model> [options]
  warnings.warn(
Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/root/sglang-3060-12g-hicache/python/sglang/launch_server.py", line 73, in <module>
    server_args = prepare_server_args(sys.argv[1:])
  File "/root/sglang-3060-12g-hicache/python/sglang/srt/server_args.py", line 11384, in prepare_server_args
    raw_args = parser.parse_args(argv)
  File "/usr/lib/python3.11/argparse.py", line 1886, in parse_args
    args, argv = self.parse_known_args(args, namespace)
  File "/usr/lib/python3.11/argparse.py", line 1919, in parse_known_args
    namespace, args = self._parse_known_args(args, namespace)
  File "/usr/lib/python3.11/argparse.py", line 2140, in _parse_known_args
    start_index = consume_optional(start_index)
  File "/usr/lib/python3.11/argparse.py", line 2080, in consume_optional
    take_action(action, namespace, argument_values)
  File "/usr/lib/python3.11/argparse.py", line 1995, in take_action
    action(self, namespace, argument_values)
  File "/usr/lib/python3.11/argparse.py", line 1134, in __call__
    parser.print_help()
  File "/usr/lib/python3.11/argparse.py", line 2623, in print_help
    self._print_message(self.format_help(), file)
  File "/usr/lib/python3.11/argparse.py", line 2607, in format_help
    return formatter.format_help()
  File "/usr/lib/python3.11/argparse.py", line 299, in format_help
    help = self._root_section.format_help()
  File "/usr/lib/python3.11/argparse.py", line 229, in format_help
    item_help = join([func(*args) for func, args in self.items])
  File "/usr/lib/python3.11/argparse.py", line 229, in <listcomp>
    item_help = join([func(*args) for func, args in self.items])
  File "/usr/lib/python3.11/argparse.py", line 229, in <listcomp>
    item_help = join([func(*args) for func, args in self.items])
  File "/usr/lib/python3.11/argparse.py", line 558, in format_help
    help_text = self._expand_help(action)
  File "/usr/lib/python3.11/argparse.py", line 655, in _expand_help
    return self._get_help_string(action) % params
TypeError: %o format: an integer is required, not dict
exit=1
```

The second named path has no `/root/sglang-3060-12g-hicache/bin/python` (`python-missing`), so the same Python checks were not runnable there.

### Torch/CUDA and private symbols (`sglang-env-3060-4b`)

```text
python 3.11.11 (main, Dec  4 2024, 08:55:07) [GCC 11.4.0]
torch_version 2.5.1+cu124
torch_cuda_compiled 12.4
cuda_is_available True
cuda_device_count 1
symbol _get_allocator_backend module= False torch= False
symbol _cuda_getAllocatorBackend module= False torch= False
symbol _cuda_changeCurrentAllocator module= False torch= False
exit=0
```

### Import-only `pynccl_allocator`

```text
Traceback (most recent call last):
  File "<stdin>", line 2, in <module>
ModuleNotFoundError: No module named 'pynccl_allocator'
exit=0
```

The diagnostic wrapper printed the traceback and then returned from the shell block; the Python import itself failed.

### Package versions (`sglang-env-3060-4b`)

```text
sglang 0.0.0.dev0
torch 2.5.1+cu124
torchvision 0.20.1+cu124
torchaudio 2.5.1+cu124
pynccl NOT_INSTALLED
pynccl-allocator NOT_INSTALLED
triton 3.1.0
flashinfer NOT_INSTALLED
transformers 5.12.1
nvidia-cuda-runtime-cu12 12.4.127
exit=0
```

## Changed resources

None. Remote inspection was read-only. The only local resource created/changed was this report.

## Verification

- SSH authenticated using BatchMode and the authorized key.
- All requested bounded diagnostics were attempted.
- Final `nvidia-smi` verified RTX 3060 utilization at `0 %` and memory use at `2 MiB`.
- No server was launched; only `python -m sglang.launch_server --help` was invoked, with its observed argparse traceback.

## Summary

The 3060 runtime evidence shows: help-path failure at argparse formatting (`TypeError: %o format: an integer is required, not dict`); Torch `2.5.1+cu124` with CUDA 12.4 and one available GPU; all three requested private allocator symbols absent; `pynccl_allocator` unavailable; and no Python interpreter in `/root/sglang-3060-12g-hicache`.

## Followups

None within this Task ID. Any installation, source change, repair, launch, or further diagnosis requires a fresh Task ID.

## Open issues

- The second named path is a source tree, not a Python virtual environment with `bin/python`; its Python runtime compatibility remains unmeasured by this read-only procedure.
- This report records observed blockers only; remediation and causal diagnosis are outside the authorized role/scope.

