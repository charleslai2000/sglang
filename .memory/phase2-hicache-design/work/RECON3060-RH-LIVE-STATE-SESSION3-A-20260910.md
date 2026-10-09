status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/RECON3060-RH-LIVE-STATE-SESSION3-A-20260910.md

evidence:
- Designated input read first: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md
- SSH target: root@i-1.gpushare.com:27460. Authentication used the existing local identity `/home/dev-codex/.ssh/sglang_3060_ed25519` with `-o IdentitiesOnly=yes`; no remote mutation was requested or performed.
- Initial bounded read-only command was run at remote time `2026-09-10T06:20:35+08:00`:
  `curl --max-time 5 -sS -o /dev/null -w "http_code=%{http_code} remote=%{remote_ip} time_total=%{time_total}\\n" http://127.0.0.1:30000/health`
  Result: `http_code=200 remote=127.0.0.1 time_total=1.002920`.
- At that initial check, `pgrep` reported the existing SGLang master PID `212252`, with command beginning:
  `/root/sglang-env-3060-4b/bin/python -m sglang.launch_server --model-path /hy-tmp/models/Qwen3.5-4B-AWQ ... --enable-hierarchical-cache ... --hicache-storage-backend file ... --enable-ready-horizon --ready-horizon-frontier-n 8`.
  `ps -p 212252` reported: `212252 ... Sl ... /root/sglang-env-3060-4b/bin/python -m sglang.launch_server ...`; direct children at that moment included scheduler PID `212536` and detokenizer PID `212537` (plus compile/resource-tracker children).
- A later bounded read-only check at remote time `2026-09-10T06:21:36+08:00` ran the same health probe. Result: `curl: (7) Failed to connect to 127.0.0.1 port 30000 after 0 ms: Connection refused`, `code=000 total=0.000282`.
- At `06:21:36`, the old PID `212252` was absent. A relaunch shell PID `214112` and new SGLang master PID `214113` were present. Exact service command included the same RH/HiCache options and additionally `--ready-host-watermark-low 55000 --ready-host-watermark-high 110000`; its output was redirected to `/tmp/sglang3060-rh-on-watermark55-4f41f5.log`. Scheduler and detokenizer children were `214263` and `214264`.
- A final bounded check at remote time `2026-09-10T06:21:53+08:00` ran:
  `curl --max-time 5 -sS -o /dev/null -w "code=%{http_code} total=%{time_total}\\n" http://127.0.0.1:30000/health`
  Result: `code=503 total=0.009253`.
  `ss -ltnp` simultaneously showed `LISTEN ... 127.0.0.1:30000 ... users:(("python",pid=214113,fd=59))`; therefore the process was listening but health was not yet 200 at this observation.
- Final service process observation (`ps -p 214112,214113,214263,214264,214359,214394`):
  `214112 ... bash -c cd /root/sglang-3060-12g-hicache ... nohup python -m sglang.launch_server ... > /tmp/sglang3060-rh-on-watermark55-4f41f5.log 2>&1 & echo $!`
  `214113 214112 ... Sl ... python -m sglang.launch_server ...`
  `214263 214113 ... Rl ... sglang::scheduler`
  `214264 214113 ... Sl ... sglang::detokenizer`
  `214359 ... sshd: root@notty`
  `214394 214359 ... bash -c for i in $(seq 1 30); do code=$(curl ... /health); ...`
- The bounded process scan for actor names (`driver`, `join`, `trace`, `probe`, request client names) returned no process lines at the final check after excluding the grep process and SGLang server/compile workers. No process named or command-line-matched as a concurrent driver, join, or trace actor was observed in that scan.
- The final log metadata observation was: `/tmp/sglang3060-rh-on-watermark55-4f41f5.log`, mtime `2026-09-10 06:21:34.288552052 +0800`, size `20155`; its bounded tail showed startup/model loading, including `Init torch distributed ends`, `Load weight begin`, and `Load weight end` at `06:21:34`. A separate process `214394` was polling health for startup and is not a driver/join/trace process by its command line.
- Earlier bounded metadata showed `/tmp/sglang3060-rh-on-long8-4f41f5.log`, `/tmp/t38c-probe.log`, `/tmp/b15-probe.log`, and other historical logs; no file was altered or deleted.

summary:
- HTTP health: VERIFIED `200` at `06:20:35` for the then-current master `212252`; subsequently observed transition during relaunch, then VERIFIED listener on port 30000 but health `503` at `06:21:53`. Current health should therefore be recorded as `503/not ready` at the last observation, not healthy/200.
- Current SGLang master PID: VERIFIED `214113` at the last observation; old PID `212252` was no longer present. The new master was still initializing, with scheduler `214263` and detokenizer `214264`.
- Concurrent driver/trace actor: VERIFIED no matching driver/join/trace process in the bounded final process scan; overall actor liveness remains UNKNOWN outside the observed command-line/process-name scope. No A/B or acceptance conclusion is inferred.
- Driver/join process availability: VERIFIED none observed by the bounded final process scan; UNKNOWN whether any output exists in retained files beyond the inspected identifiers. The health polling shell PID `214394` was observed and is distinct from a driver/join/trace actor by its exact command line.
- No service start/stop/restart, trace, cleanup, deployment, or file mutation was performed by this invocation. The remote relaunch was already present when observed; this report does not attribute or authorize it.

followups:
- Before any live trace, recheck health and actor liveness because the final observed state was startup health `503`.
- If step B proceeds, obtain driver/join output separately; do not infer A/B labels from process absence or log filenames.

open_issues:
- Current readiness after `06:21:53+08:00` is UNKNOWN; only the transient `503` observation is verified.
- Overall concurrent-actor liveness is UNKNOWN beyond the bounded process scan; no matching process was observed.
- Live RH acceptance remains NOT VERIFIED; this report establishes state only and does not evaluate acceptance criteria.
