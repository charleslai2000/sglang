# OPS-20260908-P0-R17-TRANSIENT-CLEANUP

- Task ID: `OPS-20260908-P0-R17-TRANSIENT-CLEANUP`
- Epoch: `phase2-hicache-design/2026-09-08`
- Target: `root@175.155.64.171:24052` (`pytorch-4402`)
- Status: `done`

## Scope and authorization

Read-only audit plus cleanup of exactly the authorized transient paths:

- `/tmp/t38c-probe.log`
- `/tmp/t38c-durable-trace`
- `/tmp/t38c-on`

No `/data` evidence, source, model, environment, engine, or vehicle artifacts were deleted.

## Commands and evidence

1. Audited remote disk, processes, r17 evidence, transient paths, and hashes.
   - Before: `/` overlay `98G total, 90G used, 3.9G avail, 96%`.
   - `/data` was `197G total, 158G used, 30G avail, 85%`.
   - r17 evidence directory existed and contained the preserved post-stop trace.
2. Verified `/data/evidence-gate3-parked/p0-s25-v43-residency-node-lookup-fix1-live-r17/raw/final-process-audit.txt`:
   - `engine_proc_absent=yes`
   - `vehicle_proc_absent=yes`
   - `engine_still_present=no`
3. Verified trace preservation before cleanup:
   - Evidence trace: `619892039` bytes.
   - Evidence SHA-256: `da99dfacd885573ab7736d1229e8ec54c766d1cda2f98620d9d8f870116d59ea`.
   - `/tmp/t38c-probe.log` had the same size and SHA-256, proving it was already represented in preserved evidence.
4. Removed only the three named paths with `rm -f --`.
5. Verified after cleanup:
   - All three paths reported `ABSENT`.
   - `/` overlay: `98G total, 89G used, 4.4G avail, 96%`.
   - Preserved evidence trace remained `619892039` bytes with SHA-256 `da99dfacd885573ab7736d1229e8ec54c766d1cda2f98620d9d8f870116d59ea`.
   - No engine/vehicle process was found by the post-cleanup check (the only match was the audit shell's own command text).

## Changed resources

Removed:

- `/tmp/t38c-probe.log` — `619892039` bytes before removal.
- `/tmp/t38c-durable-trace` — `0` bytes before removal.
- `/tmp/t38c-on` — `0` bytes before removal.

Preserved and verified:

- `/data/evidence-gate3-parked/p0-s25-v43-residency-node-lookup-fix1-live-r17/raw/trace-post-stop.jsonl`
- `/data/evidence-gate3-parked/p0-s25-v43-residency-node-lookup-fix1-live-r17/raw/trace-post-stop.sha256`

## Followups

None.

## Open issues

None within the authorized scope. Background tar-wait shell processes were observed, but were not engine/vehicle processes and were outside the authorized cleanup list; they were left unchanged.
