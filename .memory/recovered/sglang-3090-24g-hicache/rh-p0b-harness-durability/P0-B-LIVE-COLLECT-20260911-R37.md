# P0-B live collect R37

## Dispatch

- `ENTRY: ACCEPT`
- Task ID: `P0-B-LIVE-COLLECT-20260911-R37`
- Invocation: `ses-p0b-live-collect-r37-20260911`
- Epoch: `2026-09-11`
- Role: `devops-executor`
- Authorized target: remote `root@i-1.gpushare.com:27460`, key
  `/home/dev-codex/.ssh/sglang_3060_ed25519`

## Status

`blocked`

## Scope and stop condition

No remote command, transfer, experiment, server lifecycle action, test run, or
source/storage/Git change was performed. Execution stopped before remote access
because the required R31 authorization, R35 review result, and R32 raw-artifact
availability were not present in the live workspace. R34 explicitly reports no
local R32 bundle and says the existing vehicles do not independently establish
the complete live chain.

The requested first step is conditional on the reviewed fixture patch being
present. In the available workspace there is no R35 review artifact or reviewed
fixture patch that can be verified. Per dispatch instructions, transferring or
running unreviewed content is prohibited.

## Local evidence inspected

- Read `/home/dev-codex/AGENTS.md` and the applicable project/runtime
  instructions supplied by the environment.
- Read R34:
  `.memory/phase2-hicache-design/work/P0-B-HARNESS-SCOUT-20260911-R34.md`.
- R34 records: no local R32 raw artifact bundle; no single existing vehicle
  proving real 3060 capacity transition, HOST_ALLOC generation/retry, complete
  KV+Mamba restore, and READY; focused registered tests were previously blocked
  by missing dependencies.
- Existing workspace contains only the R34 report and prior P0-A reports under
  `.memory/phase2-hicache-design/work/`; no R31, R32, or R35 artifact was
  available to validate for this invocation.

## Commands and outputs

Local read-only discovery used the workspace file listing/glob and file reads
for the paths above. No remote SSH command was issued, so there is no remote
identity/source/dependency output and no experiment log or raw artifact.

## Changed resources

- Created this report only:
  `.memory/phase2-hicache-design/work/P0-B-LIVE-COLLECT-20260911-R37.md`
- No remote resources changed.
- No repository source, tests, gates, storage, or Git state changed.

## Acceptance result

The required complete chain is **not verified**. No claim is made for P0-B
pass. The following transitions therefore have no evidence: positive full
KV+Mamba hit; terminal/not-allocable allocation failure; WAIT_CAPACITY/
HOST_ALLOC; real allocability change; generation change; exactly one FIFO
retry; bounded-reclaim full-span allocation; complete KV+Mamba restore; READY;
and the required absence of crop, genuine miss, same-generation self-wake, and
repeated retry.

## Followups

1. Provide the R31 authorization artifact and R35 reviewed-fixture review,
   including the exact approved revision/path.
2. Provide or expose the R32 raw artifacts if they exist remotely.
3. Dispatch a fresh invocation after those prerequisites are verifiable; only
   then perform the bounded remote preflight and registered tests/vehicles.

## Open issues

- R31 authorization not available in the live workspace.
- R35 review and reviewed fixture patch not available/verified.
- R32 raw artifacts not available locally; remote availability was not queried
  because the authorization/review preconditions were unresolved.
- Existing R34 evidence says the listed vehicles are not by themselves a
  complete live P0-B chain.
