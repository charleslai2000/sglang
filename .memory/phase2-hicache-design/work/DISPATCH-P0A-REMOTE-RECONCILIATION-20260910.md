status: blocked
reason: authorization_required

# P0-A remote test-only reconciliation dispatch packet (not executed)

## Goal
Unblock P0-A by running the current local product source in a fresh isolated remote test namespace with the already dependency-complete interpreter.

## Required authorization
Explicit authorization to write a fresh remote test-only namespace on the existing remote host. The existing remote product checkout, service, GPU workload, live storage namespace, and runtime state remain out of scope.

## Bounded procedure after authorization
1. Preflight remote free space, actors, service state, and target namespace absence; stop on unsafe resource/actor conditions.
2. Create a fresh uniquely named test namespace, without touching `/root/sglang-3060-12g-hicache`.
3. Materialize the current local product source needed by the focused tests; preserve a manifest of source revision and SHA256 values before transfer.
4. Recompute the manifest remotely and require byte-identical source/test files and successful imports of pytest, orjson, msgspec, torch, setproctitle, and local sglang. Any drift stops the task.
5. Run only the exact P0-A focused RH/release/reservation tests; preserve complete stdout/stderr and test counts.
6. Keep the namespace and raw evidence for review; do not clean existing data or alter the service/storage namespace.

## Prohibited
No modification of the remote product checkout; no deploy/restart/stop; no GPU workload; no live trace; no storage mutation outside the fresh test namespace; no dependency installation; no venv creation; no git history operation; no cleanup, commit, push, or permission change.

## Stop / rollback
Stop on insufficient disk, actor conflict, source/hash drift, incomplete transfer, import/collection error, dependency mismatch, or any access outside the declared namespace. Rollback is limited to stopping the bounded test process and leaving no existing resource modified; do not delete unrelated data.

## Current state
No reconciliation has been performed. P0-A remains `blocked / NOT_VERIFIED`; P0-B and all downstream tasks remain blocked.

## Report path after authorization
`work/TEST-P0-A-REMOTE-RECONCILIATION-20260910.md`
