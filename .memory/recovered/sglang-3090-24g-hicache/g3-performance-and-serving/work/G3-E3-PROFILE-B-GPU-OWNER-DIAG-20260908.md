# G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-E3-PROFILE-B-GPU-OWNER-DIAG-20260908
epoch: E3
role: devops

## Goal and scope

Diagnosed the pre-transition `nvidia-smi` compute entry `PID 315744,
[Not Found], 22888 MiB` using read-only inspection of
`root@175.155.64.171:22109`. No signal, kill, reset, restart, benchmark,
download, instrumentation, source/model change, or remote write was made.

## Artifacts and evidence

- Exact key command output and hashes:
  [gpu-owner-diagnostic-20260908.txt](./raw/g3-e3-profile-b-20260907T165140Z/gpu-owner-diagnostic-20260908.txt)
  (SHA-256 `5a1eef0c77d105652e2264f473f7b1038334c5decde7fb689d5a9979b1b7b455`).
- Existing pre-transition evidence:
  [gpu-compute.csv](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/gpu-compute.csv),
  [gpu-query.csv](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/gpu-query.csv),
  [nvidia-smi.txt](./raw/g3-e3-profile-b-20260907T165140Z/pre-transition/nvidia-smi.txt).
- Existing run decision:
  [G3-E3-PROFILE-B-LAUNCH-20260908.md](./G3-E3-PROFILE-B-LAUNCH-20260908.md).

## Observed environment facts

- Three GPU query pairs at `2026-09-07T16:58:01Z` and two-second intervals
  were identical: GPU UUID `GPU-3d7e78ec-3446-f41c-824a-b27c6a1da19f`,
  `0%`, `24576 MiB` total, `22912 MiB` used, `1213 MiB` free, and exactly
  `315744, [Not Found], 22888` from `--query-compute-apps`.
- `nvidia-smi -q` independently showed compute PID `315744`, blank name,
  `22888 MiB`; it also showed graphics PID `1393`, blank name, `4 MiB`.
  Both `/proc/315744` and `/proc/1393` were absent. A process table filter
  over PID range `315000..316500` returned no process. Five one-second
  rechecks kept `/proc/315744` absent while the same compute row persisted.
- The v1 service and the diagnostic shell share PID namespace
  `pid:[4026532748]`; v1 `NSpid` is `298123`. Therefore this is not explained
  by the query being run from a different PID namespace.
- v1 PID `298123` remains alive with the exact frozen command, PPID 1, and
  loopback listener `127.0.0.1:8035`; `8036` is absent. Its direct children
  are only `298230` (resource tracker), `298231` (scheduler), and `298232`
  (detokenizer), with expected scheduler/detokenizer threads.
- `fuser` read-only checks found `/dev/nvidia0`, `/dev/nvidiactl`, and
  `/dev/nvidia-uvm` held only by `298123`, `298231`, and `298232` (apart from
  the kernel mount). v1 CUDA FD counts were 6, 20, and 6 respectively for
  those three processes; no other user process held the NVIDIA device files.
- Read-only v1 checks returned health HTTP 200 and idle loads:
  `num_running_reqs=0`, `num_waiting_reqs=0`,
  `max_total_num_tokens=132436`, `max_running_requests=5`. The existing
  pre-transition/restore files retain the v1 command hashes, model hash, and
  GPU query hashes.
- v1 startup log `/data/sglang-qwen35/exp_server_j1_v1.log` has SHA-256
  `0d56b79c97c8ed17aa6338b4bc7db8e0ecc6aa31651ed6a6268472917c9d9262` and
  records the same allocation footprint: weights `11.86 GB`, Mamba
  `0.07+3.38 GB`, KV `2.02+2.02 GB`, prefill graph `1.86 GB`, decode graph
  `0.10 GB`, and final available GPU memory `1.48 GB`. These allocations
  account for the observed roughly 22.9 GiB device usage.
- Driver is NVIDIA `580.173.02`, CUDA `13.0`; GPU persistence mode is
  disabled. `/proc/driver/nvidia/clients` is absent/unreadable. Filtered
  `dmesg`/journal tails contained no readable NVRM/Xid/CUDA fault lines.
- This host's `nvidia-smi` rejected the attempted `-q -d COMPUTE,PROCESSES`
  and accounting/performance forms with `Failed to parse --display/-d flags`;
  plain `-q` and query modes succeeded and are preserved.

## Classification

**Classification: (a) stale NVIDIA driver process attribution, with the live
22888-MiB allocation belonging to the unchanged v1 CUDA service; not a second
owner.** This is an evidence-backed diagnosis, not a claim that the driver
state has been repaired.

Reasons:

1. The reported PID is absent from the same PID namespace, remains absent
   across repeated rechecks, and is not a v1 thread or descendant (all v1
   TIDs are in the `298xxx` range).
2. Device-handle attribution independently finds only the v1 process tree.
   There is no live `/proc` identity, command line, cgroup, socket, or device
   handle for PID `315744`.
3. The v1 startup log's weight/Mamba/KV/CUDA-graph allocations explain the
   total `22912 MiB` GPU usage and the v1 API reports the matching weight,
   KV, and graph pools. The 22888-MiB compute row is therefore consistent
   with a stale PID label for v1's live context, not evidence of an unrelated
   owner.
4. A PID namespace mismatch is ruled out by equal namespace inode
   `4026532748`; “v1 CUDA child missed by initial scan” is ruled out by the
   complete direct tree, thread listing, `/dev/nvidia*` fuser results, and
   repeated absent `/proc/315744`; another owner is ruled out by the same
   device-handle and process-table evidence.

The separate blank graphics PID `1393` is also absent, which is additional
evidence of stale driver-side process attribution, but it is not treated as a
compute owner.

## Safe next action and transition proof

Do not mutate the host under this Task ID. The required external action is for
the authorized infrastructure/host owner to open a maintenance/driver-state
cleanup request and resolve the stale NVIDIA context bookkeeping using a
provider-supported non-destructive procedure, while retaining v1. A driver
reset/reload or host restart must not be attempted by this task and would
require separate explicit authorization because v1 currently owns the GPU.

After the owner reports the stale record cleared, obtain a fresh Task ID and
rerun all dynamic gates. To prove exclusive transition safely, the executor
must reverify v1 exact PID/cmdline, health 200, idle loads, port 8035, and
then follow the runbook's PID-scoped transition: stop only freshly verified
PID `298123`, verify all explicit descendants have exited, verify 8035 is
free, `/dev/nvidia*` has no v1 handles, and `nvidia-smi` has no compute row
(especially no `[Not Found]`) before launching B. B admission then requires
the exact B PID to exist in `/proc`, its command/tree to match, and exactly
one attributable compute owner equal to B with the required free VRAM. No B
launch or B-admission conclusion is made here.

## Summary

The blocker is stale/unattributable driver accounting, not an observable
second process or PID-namespace mismatch. The live allocation is consistent
with v1, which remains healthy, idle, and untouched on PID 298123/8035. The
Profile-B transition remains blocked until the stale record is externally
resolved and a fresh admission task repeats the gates.

## Followups

- Host owner: resolve or formally clear the driver-side stale process record
  without changing the v1 workload, then provide the maintenance evidence.
- Orchestrator: issue a fresh Task ID only after the record is absent and all
  dynamic gates are ready.

## Open issues

- NVIDIA's stale PID attribution cannot be repaired safely within this
  read-only diagnostic task; `/proc/driver/nvidia/clients` is unavailable and
  the driver query's `-d` form is unsupported on this host build.
- B was not launched; capacity, B health, and B performance remain unknown.

Final status: **done**
