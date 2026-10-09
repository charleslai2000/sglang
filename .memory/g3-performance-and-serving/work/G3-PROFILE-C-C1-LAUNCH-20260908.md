# G3-PROFILE-C-C1-LAUNCH-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-C1-LAUNCH-20260908
epoch: E4
role: devops-executor

## Result

C1 admission PASS on the authorized experimental host and loopback port 18035.
No benchmark traffic or dmon was run. C1 is intentionally left running for the
dependent decode task.

- RUN_ID: `g3-profile-c1-20260907T182700Z`
- candidate PID: `470950`
- candidate tuple: `max-running-requests=4`, `max-mamba-cache-size=20`, `cuda-graph-max-bs-decode=4`
- effective loads: `max_running_requests=4`, `max_total_num_tokens=148053`
- allocation: weights 11.857 GB; Mamba conv 0.06 GB + SSM 2.95 GB; KV 2.26 GB K + 2.26 GB V; graph 1.90 GB
- startup free VRAM: 3.79 GB after memory pool, 1.52 GB after prefill graph, 1.46 GB after decode graph
- health: HTTP 200; 8035 absent; 18035 listening only by PID 470950
- CUDA graph capture: prefill and decode completed; no OOM

## Procedure and evidence

Read and followed the Profile-C plan, preflight, v1 restore, and Profile-B OOM
reports. Captured v1 PID 462700 exact cmdline/tree and GPU state, stopped only
that PID and its captured explicit descendants, and verified 8035 down with no
GPU handles and no compute-app row before C1 launch. The stale pre-transition
row `483639 [Not Found]` was absent after v1 exit. C1 startup later exposed the
single candidate owner through `fuser` (470950/471060/471066); the driver query
reports its worker as `492218 [Not Found]`, while `/proc/492218` is absent.
No competing owner was observed in fuser or process tree.

Remote launch artifacts (append-only fresh subtree):
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-20260907T182700Z/c1/launch/`

- `pre-transition.txt`, `post-stop.txt`: v1 transition evidence
- `v1.command`: exact frozen v1 command, SHA-256 `69f80370e67d3e8e4c364ee847c1ef914641567a07dfc1ba2edb882909d70007`
- `command`, `pid`, `captured-descendants.txt`: C1 argv and identity
- `c1.log`: complete startup log
- `final-admission.txt`: final health, loads, listener, tree, GPU/fuser, allocation and graph evidence

Key final evidence hashes include `c1.log` SHA-256
`e23bb6b81bb1da03752439da7570007382c35b5356771d8fe31b55dc18adac1a` and
`final-admission.txt` SHA-256
`074fe8d0083d2781c65fc876fda90fe8dcbbecd57b7a5fd665777449326060d6`.

## Followups and open issues

Followup: dependent C1 decode task may send only the plan-authorized benchmark
traffic against PID 470950/port 18035 and must retain separate measurement
artifacts.

Open issue: NVIDIA compute-app query represents the candidate worker as
`492218, [Not Found]`; fuser and the candidate tree attribute all device handles
to the candidate. The v1 stale-owner gate itself was clean before launch.

Final status: **done**
