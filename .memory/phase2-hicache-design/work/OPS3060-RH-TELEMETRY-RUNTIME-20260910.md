# OPS3060-RH-TELEMETRY-RUNTIME-20260910

## Status

done (bounded check executed; request completion remained unobserved and is an open issue)

## Authorization and scope

- Task: `T3060-RH-TELEMETRY-RUNTIME-20260910`; epoch `20260910-rh-ab60`.
- Remote: `root@i-1.gpushare.com:27460`, key `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Service path: `/root/sglang-3060-12g-hicache`; venv: `/root/sglang-env-3060-4b`; listener: `127.0.0.1:30000`.
- No product source or storage was edited. No restart was performed.

## Commands and evidence

The following bounded SSH commands were run (exact command forms preserved here; outputs were captured in the execution record):

```sh
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com
ps -eo pid=,ppid=,cmd=
ss -ltnp | grep ':30000'
curl -sS --max-time 10 -w '\\nHTTP=%{http_code}\\n' http://127.0.0.1:30000/health
readlink -f /proc/120252/cwd
readlink -f /proc/120252/fd/1
/root/sglang-env-3060-4b/bin/python  # imported scheduler path/hash and logger levels/handlers
stat -c '%n size=%s mtime=%y' /tmp/sglang3060-rh-on-9213-20260910.log
```

The single request command was:

```python
text = "y " * 55000
body = json.dumps({"text": text, "sampling_params": {"max_new_tokens": 1, "temperature": 0}}).encode()
POST http://127.0.0.1:30000/generate
```

The log byte offset immediately before the request was `228464`; appended evidence begins at byte `228465`. The service log grew from `228464` to `11043936` bytes. The request RID observed in service logs was `2a2780a49ef64250a977ab99cf09ff0d`.

## Baseline / post-check

- PID: `120252`, authorized SGLang listener process; unchanged and alive after the check.
- Listener: `127.0.0.1:30000` owned by PID `120252`; present after the check.
- Health: HTTP `200` before and after the request.
- Process command still used the authorized SGLang launch configuration and `--max-total-tokens 65536`.
- The requested exact commit `9213ee01d90ba3925e7fe928e80cc41354ee4fff` was not independently resolved by `git rev-parse`: the supplied service path was not a Git worktree. No source checkout mutation was attempted.

## Source identity and logger configuration

- Imported scheduler source: `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py`.
- SHA-256: `f6c3644a039df88ca2d9a47df1fac1fd7d0bf12f29538c7b87e3e5c810627bde`.
- Python import used the editable `sglang` installation from `/root/sglang-env-3060-4b`.
- Root logger: level `30`, handlers `[]`.
- `sglang`, `sglang.srt`, and `sglang.srt.managers.scheduler`: explicit level `0`, handlers `[]`, propagate `True`.

## Contiguous raw log evidence and ordering

The first appended lines for this RID were:

```text
[2026-09-09 20:58:35] [P2A] ts_ms=1788958715857 evt=prefetch_issued rid=2a2780a49ef64250a977ab99cf09ff0d prefetch_length=55000
[2026-09-09 20:58:35] [P2A] ts_ms=1788958715862 evt=restore_state rid=2a2780a49ef64250a977ab99cf09ff0d state=RESTORING reason=none
[2026-09-09 20:58:35] [P3] ts_ns=8678801102077087 evt=rh_preadmission_decision schema=rh_preadmission.v1 rid=2a2780a49ef64250a977ab99cf09ff0d ... decision=issue reason=issued issue_origin=READY_HORIZON attempt_id=2a2780a49ef64250a977ab99cf09ff0d:prefetch:1
[2026-09-09 20:58:35] [P3] ts_ns=8678801102204343 evt=ready_stage schema=rh_stage.v2 rid=2a2780a49ef64250a977ab99cf09ff0d ... result=issued reason=issued ... restore_state_after=RESTORING
[2026-09-09 20:58:35] [P2A] ts_ms=1788958715863 evt=admission rid=2a2780a49ef64250a977ab99cf09ff0d pos=0 qlen=1 running_bs=0 can_run=0
```

Counts over the appended RID lines:

- `prefetch_issued`: 1.
- `restore_state`: 1 direct state line; later RH decisions show `WAIT_CAPACITY/HOST_ALLOC`.
- `rh_preadmission_decision`: 2 (initial `issue/issued`; later `exclude/no_restore_potential`).
- `rh_stage.v2` / `ready_stage`: 1, initial issue path only.
- `admission`: 97,429 repeated `can_run=0` lines observed through `20:59:58`.
- `admission.v2`: 0 observed.
- `POST /generate` completion: 0 observed.

The contiguous ordering therefore proves `rh_match_prepare.v1` was not present before the observed `rh_stage.v2` line; the service emitted `rh_stage.v2` directly after the issue decision. The later state was `WAIT_CAPACITY` with wait reason `HOST_ALLOC`, and no admission/completion record was emitted during the captured interval.

## Request outcome and classification

Observed facts:

1. The exact one-request workload was sent once with `text='y ' * 55000`, `max_new_tokens=1`, `temperature=0`.
2. The server assigned RID `2a2780a49ef64250a977ab99cf09ff0d` and emitted the issue/stage sequence above.
3. The server remained alive but repeatedly reported `can_run=0`, then `WAIT_CAPACITY/HOST_ALLOC`.
4. No successful `/generate` completion, response status, generated token, or `admission.v2` was observed.

Inference/classification: **RH telemetry ordering defect / incomplete admission path, with request not completed in the observation window.** The evidence supports that `rh_stage.v2` is emitted at prefetch issue time and that the request subsequently stalls on host allocation capacity. It does not establish a successful L3 hit or a miss. Hit-related fields are **unobserved**, not zero; no hit count was inferred from absent fields.

## Rollback / cleanup

No restart, source edit, storage change, seed change, or rollback action was performed. The service was left running under PID `120252`; post-check health was HTTP 200.

## Open issues / followups

- Client-side response status and final request outcome were not returned by the SSH execution wrapper; do not treat the request as successful.
- The stated commit could not be verified because `/root/sglang-3060-12g-hicache` is not a Git worktree. Resolving that requires a fresh Task ID if commit provenance is required.
- Any further runtime request, timeout intervention, restart, or source/telemetry investigation requires a fresh Task ID.
