# G3-IQ3-LOCAL-SMOKE-ARGPARSE-DEBUG-20260909

status: done

stable_task_id: `G3-IQ3-LOCAL-SMOKE-20260909`  
invocation_id: `INV-G3-IQ3-LOCAL-SMOKE-DEBUG-001`  
epoch: `E17`  
role: `debugger-deep`  
capability_level: `L2`

## Result

The failure is a deterministic argparse help-formatting defect, not a CUDA,
model, entrypoint-selection, or dependency-resolution failure.  The safe
workaround is to replace the unusable `--help` gate with a no-GPU,
full-argv `prepare_server_args()` parse gate, then launch the unchanged argv
without `--help` under the normal GPU lock.

## Observed causal chain

1. `python -m sglang.launch_server --help` calls
   `prepare_server_args(["--help"])`.
2. `ServerArgs.add_cli_args()` registers
   `--hicache-writeback-reserve-gb` from
   `python/sglang/srt/server_args.py:2983-3002`.
3. Its help text contains the literal `67%` at line 2998.
4. Python 3.12 `argparse.HelpFormatter._expand_help()` applies old `%`
   interpolation to every help string. It reads `% o` as an octal formatter
   and receives argparse's parameter dictionary, raising:

   ```text
   TypeError: %o format: an integer is required, not dict
   ```

The original complete traceback is retained in the prior retry artifact:
`/mnt/data/qwen3-g3-baseline/artifacts/local-smoke-20260909-retry4/preflight.stderr`.
The first actionable frames are `server_args.py:11384` and
`/usr/lib/python3.12/argparse.py:656`.

The direct parser scan found exactly one percent-bearing help string and
exactly one offender. See [action-help-scan.txt](raw/g3-iq3-local-smoke-argparse-debug-20260909/action-help-scan.txt).

## Competing hypotheses

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| CUDA/3090 initialization fails | Rejected | `CUDA_VISIBLE_DEVICES=''` reproduces before server startup; all probes completed without GPU lock. |
| `python -m` is the only bad entrypoint | Rejected | `sglang serve --help` reaches the same `prepare_server_args(["--help"])` path and throws the same exception. |
| A different help action is responsible | Rejected | Per-action `_expand_help()` scan reports one percent-bearing action and one offender: `--hicache-writeback-reserve-gb`. |
| Normal launch parsing is broken | Rejected for the intended smoke argv | Full frozen argv parsed and its model/path/parser/KV/Mamba/template values exactly matched expected values; exit 0. |

## Reproducible safe preflight

Use the recorded command in [argv-parse-preflight.txt](raw/g3-iq3-local-smoke-argparse-debug-20260909/argv-parse-preflight.txt).
It sets `CUDA_VISIBLE_DEVICES=''`, only imports the parser and validates the
exact intended launch argv. It exited 0 and does not acquire
`/mnt/data/gpu/3090.lock`, load the GGUF, bind a port, or start a server.

For any changed launch tuple, the next executor must substitute only that
tuple in the `argv` list and retain every frozen profile argument. Do not use
`--help` as this checkout's launch preflight until product code is separately
fixed.

## Minimal product fix (not performed)

If help output itself must be restored, a coder-owned change should escape the
literal percent as `67%%` in the affected help text, followed by a focused
`launch_server --help` test. No product code was modified in this invocation.

## Safety and scope

- No GPU lock acquired.
- No CUDA model loading, service, benchmark, driver, CUDA, venv, or product
  file modification.
- No alternative runtime semantics selected; the successful parser oracle uses
  the frozen smoke argv unchanged.

## Followups

Return to `devops-executor` for the queued smoke. It may use the successful
argv parse gate and then, only after acquiring `/mnt/data/gpu/3090.lock`, run
the unchanged launch command without `--help`.

## Open issues

- `--help` remains unavailable until a fresh coder task makes and validates
  the one-character help-text escape.
- This diagnosis validates argument construction only; it is not evidence that
  the GGUF can load or serve on the local 3090.
