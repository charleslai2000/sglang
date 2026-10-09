# G3-E3-PRODUCTION-A-LAUNCH-20260907

status: pending
task_id: G3-E3-PRODUCTION-A-LAUNCH-20260907
epoch: E3
role: devops

## Launch

- RUN_ID: `g3-e3-prod-a-20260907T145045488234751Z`
- Remote path: `/data/qwen3-g3-baseline/e3-prod-a/g3-e3-prod-a-20260907T145045488234751Z/`
- Wrapper PID: `434309` (active at 2026-09-07T14:58:22Z)
- Wrapper: `run-production-a.sh`
- Wrapper SHA-256: `02752a72359e0e1aaf686807c50c2dccb156a4c50158654715d5f8d35965f38f`
- First point: `C1/repeat-1`, `max-concurrency=1`, `num-prompts=20`, `warmup-requests=3`; active.
- Current benchmark client PID: `434364`.
- Current exact telemetry PIDs: `nvidia-smi dmon=434362`, query loop `434363`.

## Admission evidence

- Host: `175.155.64.171:22109`; service `127.0.0.1:8035`; service PID `298123`.
- Service command identity remained the expected frozen IQ3_S SGLang command during launch checks.
- `/health` and `/v1/loads` succeeded; loads were zero before launch; GPU utilization was 0% before launch.
- The wrapper records per-repeat before/after loads, service identity, server-log deltas, native stdout/stderr/result, and exact telemetry PID files.

## Notes

- The earlier 14:48:27 directory is preserved as a pre-existing-process admission halt; the 14:50:45 directory was the authorized idle metadata run used for this launch.
- Two wrapper-only setup attempts halted before benchmark traffic; the final wrapper was syntax-validated and corrected before this active launch. No benchmark invocation completed or produced a measurement before the active launch.

## Open issues

- Matrix is still running; no scorecard or completion verdict is available yet.
