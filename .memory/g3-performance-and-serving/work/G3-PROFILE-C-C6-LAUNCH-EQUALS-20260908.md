# G3-PROFILE-C-C6-LAUNCH-EQUALS-20260908

ENTRY: ACCEPT

## Result

done — C6 admission succeeded without benchmark traffic. The candidate was
launched on the authorized experimental host at `127.0.0.1:18036` and remains
running for the separately assigned decode task.

## Exact scope and command

- Host: `175.155.64.171:22109`; no other host touched.
- v1 PID `487847` was identity-verified from its full command line, then
  terminated before candidate launch because its health endpoint was still
  loading and GPU ownership had to be transferred.
- Candidate PID: `488839`.
- Remote artifacts:
  `/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-equals-20260908/launch/`
- Local copy:
  `.memory/g3-baseline-20260907/work/raw/g3-profile-c6-equals-20260908/launch/`
- Command used `/data/sglang-qwen35-env/bin/python -m sglang.launch_server`
  with frozen model/parser/KV/Mamba/template flags and only C6 capacity knobs:
  `--max-running-requests 6 --max-mamba-cache-size 32
  --cuda-graph-max-bs-decode 8`.
- The JSON argument was passed in equals form and verified in `/proc/488839/cmdline`:
  `--default-chat-template-kwargs={"preserve_thinking":false}`.
- Offline environment variables were set; no downloads or benchmark requests
  were performed.

## Admission evidence

- `GET /health`: HTTP 200.
- `/v1/loads?include=all`: idle, `max_running_requests=6`,
  `max_total_num_tokens=91677`, `num_running_reqs=0`.
- Weight allocation: `11.857 GB`.
- Mamba cache: `max_mamba_cache_size=32`, log reports conv `0.09 GB`, SSM
  `4.64 GB`.
- KV cache: FP8 E4M3, 91,677 tokens, K `1.40 GB`, V `1.40 GB`;
  endpoint reports `kv_cache_gb=2.798`.
- CUDA graphs: prefill capture completed for all 42 target sizes; decode
  capture completed for batch sizes `[1,2,4,6]` with no OOM.
- Post-capture available GPU memory: `1.43 GB`; one RTX 3090, 22,826 MiB
  used and 1,299 MiB free at capture.
- Model SHA-256:
  `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- Deployed source is `/data/sglang-qwen35/python`; it is not a git worktree,
  so no commit/dirty-state identity is available from that path.

## Raw artifact integrity

Remote `SHA256SUMS` covers the launch evidence files. The same directory was
copied locally under the raw artifact path above. Key raw files are
`server.log`, `proc.cmdline`, `loads.json`, `ps.txt`, `gpu-query.csv`,
`gate-lines.txt`, `model-sha256.txt`, and `source-identity.txt`.

invocation_status: done

followups: run the separately authorized C6 fixed-256-token decode workload;
restore v1 after decode and verify service invariants.

open_issues: none for C6 admission. No throughput claim is made here.
