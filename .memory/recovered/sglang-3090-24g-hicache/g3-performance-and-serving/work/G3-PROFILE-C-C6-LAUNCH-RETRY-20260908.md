# G3-PROFILE-C-C6-LAUNCH-RETRY-20260908

ENTRY: ACCEPT

## Status

blocked — the C6 candidate did not start because the checkout rejected the
argv value for `--default-chat-template-kwargs` after shell quoting stripped
the JSON quotes. The authorized v1 service was restored and verified healthy.

## Scope and target

- Host: `175.155.64.171:22109`
- Candidate: port `18036`, requested `max-running-requests=6`,
  `max-mamba-cache-size=32`, `cuda-graph-max-bs-decode=8`.
- No benchmark traffic, downloads, audit hooks, or product edits.
- Remote evidence: `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-retry-20260908/launch/`

## Executed procedure and evidence

The identity-verified v1 PID was `484570`; its process tree was stopped before
the candidate launch. The candidate was launched with the frozen flags and
the requested capacity knobs. The effective remote command reached the
runner as `'{preserve_thinking:false}'`, and SGLang rejected it:

`sglang serve: error: argument --default-chat-template-kwargs: invalid loads value: '{preserve_thinking:false}'`

The candidate exited before binding port 18036; no health, admission, graph,
or workload evidence exists. This is a launch-quoting failure, not an OOM.

v1 was immediately relaunched with the frozen production arguments. Verified:

- PID `486264`, scheduler `486398`
- `GET /health` returned HTTP 200
- `/v1/loads?include=all`: idle, `max_running_requests=5`,
  `max_total_num_tokens=132436`, weights `11.857 GB`, KV `4.042 GB`, graph
  `1.955 GB`
- v1 process arguments retain the frozen parser, KV dtype, Mamba strategy,
  and `preserve_thinking=false` settings.

## Raw artifacts and hashes

- `server.log`: `9b0b9f56...68c60c` (full hash in remote `SHA256SUMS`)
- `v1_loads.json`: `369beb9f...9864e`
- `v1_after.txt`: `4cf926df...18c6b`
- `v1_before.txt`: `83ccef47...bd95`
- Remote manifest: `.../launch/SHA256SUMS`

## Follow-up

Fresh task required to retry C6 with a transport that preserves the exact JSON
argv element (for example an argv array or a safely encoded remote script).

invocation_status: blocked

open_issues: C6 admission and graph capture remain unmeasured; no candidate
should be inferred from this failed launch.
