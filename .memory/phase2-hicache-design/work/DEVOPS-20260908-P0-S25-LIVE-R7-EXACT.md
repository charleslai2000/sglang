# DEVOPS-20260908-P0-S25-LIVE-R7-EXACT

status: done (execution completed; operational verdict NOT_VERIFIED)

## Scope and procedure

- SSH target: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Run ID: `p0-s25-v43-fix2-live-20260907T232817Z`
- Vehicle: absolute interpreter and explicit `PYTHONPATH` as dispatched; S=25, active=8, build-workers=8, history-target=55000, RH=off.
- Launcher: `/root/sglang-b1-continuity/3090-dev/direct-launch-gate3-parked.sh`
- New evidence: `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r7/{vehicle,storage}`

## Preflight and baseline evidence

The exact mandatory preflight succeeded:

```text
/root/miniconda3/envs/sglang-patch/bin/python
5.12.1
/root/sglang-b1-continuity/3090-dev/gate3_parked.py
```

The initial matching-process check found no pre-existing engine or vehicle. The only broad-pattern matches were the inspection shell itself and an unrelated environment-tar wait process.

Before reuse, both transient files were copied to `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r5/raw/` and hashed:

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  t38c-probe.log.pre-r7
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  t38c-durable-trace.pre-r7
```

The transient files were then truncated and marked with the fresh run ID. Launcher readiness succeeded at `2026-09-07T23:29:57Z` UTC.

## Vehicle result

The vehicle exited with RC=1 at `2026-09-07T23:38:31Z` UTC and emitted:

```json
{"barrier_waits":25,"branches":{"A_omitted_transfer":0,"B_write_failure":0,"C_key_mismatch":0,"D_recycle_or_remove":0,"E_late_write_or_barrier":0,"F_unresolved":25},"eligible_full_sessions":25,"errors":[],"execution_started":true,"fail_closed":true,"missing_event_join":true,"no_fixed_sleep_success":true,"planned_sessions":25,"restore_success":0,"vehicle_readiness":"live-capable","verdict":"NOT_VERIFIED"}
```

Summary: all 25 planned sessions reached eligible-full state and produced 25 barrier waits, but all 25 were unresolved; no restore successes were recorded. The operational verdict is therefore `NOT_VERIFIED`, not a passing P0 result.

## Stability and shutdown verification

- Engine served successful HTTP 200 requests throughout the run.
- No `ModuleNotFoundError` or scheduler-crash signature was observed.
- Engine evidence contains unrelated torchcodec/libavutil load warnings and shutdown cancellation output; these did not prevent readiness or the live requests.
- The launcher stopped only the matching engine PID (`1006943`) after vehicle termination.
- Final `ps` check returned no matching engine or `p0_session_barrier_vehicle.py` process.
- Storage was preserved at the new path; the extent file is 120,000,000,000 bytes. Vehicle artifacts include `verdict.json`, `barrier-waits.jsonl`, `build-warm.jsonl`, `reducer-result.json`, and `trace-copy.jsonl`.

## Artifacts and followups

Remote artifacts remain preserved under `/root/evidence-gate3-parked/p0-s25-v43-fix2-live-r7/`. No prior evidence/storage was mutated. No alternative procedure, RH-on run, synthetic run, manual warm, fixed settle, or larger fleet was performed.

Followup: the unresolved event-join / zero-restore condition requires a separately authorized Task ID and fresh procedure before any rerun or diagnosis.

Open issues: `missing_event_join=true`; `F_unresolved=25`; `restore_success=0`; verdict `NOT_VERIFIED`.
