# G3-E3-PROFILE-B-TRANSITION-20260908

ENTRY: ACCEPT

status: blocked
invocation_status: blocked
task_id: G3-E3-PROFILE-B-TRANSITION-20260908
epoch: E3
role: devops

## Artifacts

- Remote run root: `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T170803Z/`
- Local practical raw copy: `.memory/g3-baseline-20260907/work/raw/g3-e3-profile-b-20260907T170803Z/` (209 files)
- Local report: `.memory/g3-baseline-20260907/work/G3-E3-PROFILE-B-TRANSITION-20260908.md`

Key raw hashes:

```text
launch/profile-b.command  cb02a208e967ff1786c6841b6aa0ca0abc46e2e4d9bbd3535590351b029c8840
launch/profile-b.log      e653fb4cd4b9b53a0cb319336b7b749510d3ca08bd9a36350e424e448de2b608
restore/v1.command        69f80370e67d3e8e4c364ee847c1ef914641567a07dfc1ba2edb882909d70007
restore/v1.log            6b8581858b60ff59cd35eaea85816ec33a725e391cb4136c93c5da3ba9c112bb
```

## Observed facts and execution evidence

- The fresh pre-transition capture reverified PID `298123` as the exact frozen
  v1 command, health HTTP 200, idle loads, 8035 ownership, 8036 free, and no
  benchmark/dmon/query sampler processes. The corrected immediate recheck is
  `transition/reverify-summary.txt` (`reverify_gate=1`).
- v1 PID `298123` was TERM-stopped under exact cmdline identity; its explicitly
  captured descendants were identity-checked. `transition/post-stop-summary.txt`
  records `stop_gate=1`, `desc_bad=0`; 8035 was free and the repeated
  post-stop compute query was empty.
- The exact Profile-B command from the runbook launched once on 8036 with
  parent PID `459460`, using only the capacity flags `chunked-prefill-size
  2048`, `max-prefill-tokens 16384`, `max-running-requests 16`,
  `max-mamba-cache-size 64`, `max-total-tokens 33024`,
  `mem-fraction-static 0.95`, and `cuda-graph-max-bs-decode 16` alongside
  the frozen flags. No benchmark request or other traffic was sent.
- B failed during startup CUDA-graph capture before health/admission. Its log
  records `torch.OutOfMemoryError`: process `480396` had `23.53 GiB` in use,
  only `10.88 MiB` free, and the attempted allocation was `170.00 MiB`.
  Therefore no B effective capacity, health 200, or admission pass exists.
  The captured B health and loads HTTP statuses were both `000` (startup
  failure); no effective-capacity JSON was available.
- The B wrapper's initial admission bookkeeping also encountered a local
  parser defect after B had exited (GPU free field was read as `Disabled`).
  This did not change the launch command or host state; the raw startup log
  and process failure are authoritative. No retry or parameter substitution
  was made.
- Exact v1 restoration was attempted once with the runbook command, parent
  PID `461274`. It failed before health with
  `RuntimeError: Could not find nvcc and default cuda_home='/usr/local/cuda'
  doesn't exist`; `restore/RESTORE_FAILED.txt` and `restore/restore-summary.txt`
  record `restore_gate=0`, `owner_count=0`.
  Restore health and loads HTTP statuses were both `000`. The preserved model
  MD5 is `a37cff66ad81b0e6311d4b6671ac2b09`; runner SHA-256 is
  `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`; and
  `server_args.py` SHA-256 is
  `aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9`.
- Final read-only capture records both 8035 and 8036 absent, no compute-app
  row, GPU memory `15 MiB used / 24110 MiB free`, and no running SGLang
  service. This is an operationally blocked restoration state; no further
  launch was attempted because the runbook forbids improvising a restore
  command after restore failure.
- The first script's `launch/HALTED.txt` preflight marker was caused by its
  self-matching `/proc` capture scan before any signal. That provenance is
  preserved in the same file; the current B startup OOM outcome is appended
  explicitly as `current_outcome` and separately recorded in
  `launch/current-outcome.txt`.

## Summary

The one authorized v1-to-B transition was executed through the stop gate.
GPU accounting was clean after v1 exit, but Profile B could not fit its
requested startup CUDA graphs and failed OOM before admission. The exact v1
rollback command then failed because the host shell environment could not find
`nvcc` at `/usr/local/cuda`. No benchmark traffic was sent. The host currently
has neither v1 nor B running, so the task is blocked pending an authorized
host-owner restoration decision/environment correction.

## Followups

- Host owner must restore the exact v1 operating point using an approved
  environment that satisfies the existing runbook, or issue a new authorized
  recovery task. Do not alter the frozen profile under this task.
- A future Profile-B attempt requires a fresh Task ID and must treat the B OOM
  as a failed admission; no performance matrix is authorized from this run.

## Open issues

- Exact v1 restoration is not verified; current service state is empty.
- Profile-B effective capacity is unknown because startup failed.
- `launch/profile-b.log` includes the complete OOM traceback; no source/model
  edits, downloads, resets, reboots, or broad process matching were used.

Final status: **blocked**
