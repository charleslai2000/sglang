# P0-B HOST_ALLOC liveness scout

- Task ID: `P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911`
- Invocation: `scout-20260911-02`
- Scope: read-only inventory of `.memory`, `3090-dev`, `test`, `review/gates`, and 3060-related runtime entries.
- Live/remote execution: **not performed**.

## status

done

## artifacts

- This report: `.memory/phase2-hicache-design/work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md`
- No project files were modified.

## evidence

### 1. Existing HOST_ALLOC unit/regression fixtures

**VERIFIED** — the closest existing liveness fixture is:

- `test/registered/unit/managers/test_hicache_host_allocability.py:13,34,53,63,200-231`
  - imports/constructs `HostAllocWakeArbiter`;
  - supplies a scheduler/cache host-allocability snapshot fixture;
  - initializes `_host_allocability_generations`, instance ID, and telemetry sequence;
  - exercises `lock_release_evictable`, zero-unit `direct_free`, nonzero `direct_free`, and `_bump_changed_host_allocability`.
- `3090-dev/test_hicache_restore.py:738-760`
  - pure state-machine fixture for `capacity_wake_applies`;
  - explicitly asserts `HOST_ALLOC` is wake-applicable and `REVALIDATE` is not.
- `3090-dev/test_hicache_restore_scheduler_feed.py:195-245` (located by search)
  - scheduler-feed fixture for a `HOST_ALLOC` wait reason and re-entry into the wait path.
- `3090-dev/test_storage_regression.py:2487-2489,2613-2634`
  - initializes host-allocability generation state;
  - contains the repeated-mutation telemetry fixture (5,000 bumps, bounded record assertion).

The repository also has the dependency-free neighboring harnesses:

- `3090-dev/test_drain_reentry.py`
- `3090-dev/test_hicache_restore.py`
- `3090-dev/test_hicache_restore_scheduler_feed.py`
- `3090-dev/test_storage_regression.py`

### 2. Existing HOST_ALLOC architecture/review acceptance shape

**VERIFIED** — the required P0-B path is recorded in:

- `.memory/phase2-hicache-design/ledger.md:26-28`
- `.memory/phase2-hicache-design/plan.md:20-23,65-67`

Exact hard-gate path:

```text
not allocable -> park -> real allocability change -> wake -> successful restore
```

The detailed architecture fixture/report is:

- `review/gates/ARCH-20260909-HOST-ALLOC-EPOCH.md:41-53,102`
  - describes the waiter generation-vector/cursor model and requires a separately authorized pinned live 3060 test after source/unit gates.
- `review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH.md:184-197`
  - lists the still-needed live scenarios: unlock-to-evictable, queued KV release, queued Mamba release, KV-only, RH OFF, timeout, cancellation, and repeated failed-grant fairness.
- `review/gates/REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:150-162`
  - lists authoritative live 3060/SM86/GDC acceptance categories: lock release, direct free, queued drain, auxiliary-only cleanup, hybrid all-or-nothing/per-domain feasibility, FIFO/no-spin, and telemetry joins.
- `review/gates/REVIEW-20260909-ALLOC-FAILED-TERMINAL.md:118-137`
  - records the terminal mapping `revoked_alloc_failed -> DENIED_ALLOC -> WAIT[HOST_ALLOC]` and explicitly says no live post-fix 3060 run was included.

### 3. Existing 3060 remote runtime entry

**VERIFIED** — the prior P0-A report records the authorized remote environment and exact probe command:

- `.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-20260911.md:9-14`
  - remote: `root@i-1.gpushare.com:27460`
  - SSH key: `/home/dev-codex/.ssh/sglang_3060_ed25519`
  - checkout: `/root/sglang-3060-12g-hicache`
  - interpreter: `/root/sglang-env-3060-4b/bin/python`
  - observed GPU: RTX 3060, 12288 MiB, SM 8.6; Python 3.11.11; pytest 9.1.1; torch 2.6.0+cu124.

The exact environment/identity probe recorded there is:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com \
  'printf "hostname="; hostname; printf "gpu="; nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>&1; printf "checkout="; pwd; test -d /root/sglang-3060-12g-hicache && printf OK || printf MISSING; printf "\npython="; /root/sglang-env-3060-4b/bin/python --version; printf "pytest="; /root/sglang-env-3060-4b/bin/python -m pytest --version; printf "deps="; /root/sglang-env-3060-4b/bin/python -c "import orjson,msgspec,torch; print(orjson.__version__,msgspec.__version__,torch.__version__,torch.version.cuda)"; printf "\nstatus="; cd /root/sglang-3060-12g-hicache && git status --short 2>&1; printf "revision="; git rev-parse HEAD 2>&1'

**VERIFIED** — the same report states the remote checkout is not a Git repository and differs from the current local test corpus. Therefore it is an environment entry, not a current-HEAD deployment/synchronization procedure.

### 4. Existing 3090 live drivers are not P0-B HOST_ALLOC drivers

**VERIFIED** — `3090-dev/README.md:10-25,47-53` identifies the existing executable assets as Gate-2 restore/load tools, capacity unit tests, and Gate-3 natural-pressure parked-session/capacity drivers. Relevant scripts include:

- `3090-dev/gate2-run.sh` and `gate2-run2.sh` (engine launch + load; `gate2-run.sh:63-95` uses `direct-launch-gate1.sh` and `agent_driver.py`);
- `3090-dev/gate3_capacity.py:4-12,65-72` (natural device-capacity curve; explicitly no `WAIT_CAPACITY` or `/pause_generation`);
- `3090-dev/gate3_parked.py:4-25,60-124` (natural LRU/eviction parked-session resume; explicitly no scheduler pause/wait endpoint);
- `3090-dev/direct-launch-gate3-parked.sh:23-60` (3090-oriented server launcher with extent backend, RH toggle, and Qwen3.5-9B-w4a16 defaults).

These are neighboring capacity/restore experiments, not an existing exact `not allocable -> park -> real allocability change -> wake -> successful restore` HOST_ALLOC liveness driver, and their defaults target the 3090/Qwen3.5-9B environment.

### 5. Negative findings

**NOT_FOUND within the searched scope:**

- no file named or clearly documented as a dedicated `HOST_ALLOC` liveness/allocability live driver;
- no existing 3060-specific server launch script that pins the P0-B capacity profile;
- no existing command/report proving the full hard-gate sequence on current HEAD;
- no capacity-bundle fixture that directly drives a real remote allocator through park, external capacity change, wake, and successful restore.

This is scoped to the searched repository paths and `.memory/phase2-hicache-design`; it is not evidence that no such artifact exists outside this checkout or in the remote filesystem.

## summary

The repository has pure/unit and scheduler-feed HOST_ALLOC fixtures, plus detailed review requirements, but no existing exact live P0-B HOST_ALLOC liveness script. The smallest executable next task is therefore a fresh remote 3060 execution task that first pins/records environment identity, then runs the existing focused HOST_ALLOC/unit fixtures before any live scenario. The current remote checkout cannot be assumed to represent local HEAD because the prior report records missing/different test files and no Git metadata.

## followups

Recommended next task (execution owner; fresh Task ID; live 3060 only):

1. Run the environment identity probe above.
2. If the remote source/test fixture is explicitly pinned to the intended revision, run the existing dependency-complete focused tests:

```bash
cd /root/sglang-3060-12g-hicache && \
PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test \
/root/sglang-env-3060-4b/bin/python -m pytest -q \
  test/registered/unit/managers/test_hicache_host_allocability.py \
  3090-dev/test_hicache_restore.py \
  3090-dev/test_hicache_restore_scheduler_feed.py \
  3090-dev/test_storage_regression.py
```

3. Only after focused gates pass, execute a newly authored/pinned live fixture for the seven scenarios named in `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH.md:195-197`; this scout found no pre-existing exact command or fixture to invoke for that step.

## open_issues

- HOST_ALLOC governance remains blocked at G1/G2 per `.memory/phase2-hicache-design/context.md:15`.
- The final deep review remains `REJECT` with three blocking findings in `REVIEW-DEEP-20260909-HOST-ALLOC-EPOCH-FINAL.md:62-133`; no live run can be treated as acceptance until the applicable source/test/review gates are resolved.
- The suggested focused command is a next-task fixture assembled from existing paths; it was not executed here, and its remote path availability must be checked by the execution owner because the prior remote checkout lacked some local files.
- No live runtime, remote mutation, deployment, synchronization, or code/test modification was performed by this scout.
