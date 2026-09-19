# P5-MAMBA-FINAL-AND-PROD-START-20260918

status: WORKING

## Task
Execute the mamba-pool sizing experiment to completion (cells `max_mamba_cache_size = 48, 56, 64`),
pick the smallest size that removes/materially suppresses the `mamba_available_tokens==0 ->
WAIT_CAPACITY -> extreme TTFT tail` with no OOM and safe VRAM, then START production on :30000 and HOLD.

## Scope
- ONE GPU window (owner-authorized). Sequential cells on port 30160, cloning the captured production argv.
- Then production start on :30000 via `bash /tmp/opencode/prod-service-20260917/bin/start.sh prod`.
- Only artifact this file + fresh per-cell run dirs. No ledger writes, no repo edits, no pkill/killall.

## Result
IN PROGRESS. Cell-48 attempt (sweep4) was externally SIGTERM'd at 23:59:13 mid-load by a
competing session (see Evidence). Retrying cell-48.

## Evidence
- Approvals: `OWNER-APPROVAL-20260918-PROD-START` (ledger line 9520) + the 2026-09-18 entry
  "Mamba 定档必须真跑出来" (ledger ~9630).
- GPU takeover at 23:56:31-23:56:37: stopped the in-flight production start (client `start.sh prod`
  pid 1738571, supervisor pid 1738792, server pgid 1738819) identity-checked; GPU verified clean
  (no launch_server, ports 30000/30160 free, flock FREE, no compute apps).
- sweep4 cell-48: run `sweep4-mamba48-20260917T235645Z-1740204`, server pid 1740265, UP 23:58:39
  lock gen 15. Load 8/128 ok; server received external `SIGTERM` at 23:59:13 (console line 1136).

## Defects / blockers
PENDING

## Remaining claims / exclusions
PENDING

## Terminal state
WORKING
