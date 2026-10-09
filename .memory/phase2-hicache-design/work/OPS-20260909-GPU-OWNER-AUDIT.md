# GPU/process ownership audit

- Task ID: `D3060-GPU-OWNER-AUDIT-20260909`
- Orchestration epoch: `20260909-rh-ab3`
- Role: `devops-executor`
- Invocation status: `blocked`
- Audit time: 2026-09-09 (local execution time; remote audit did not authenticate)
- Target: `i-1.gpushare.com:27460`

## Scope and authorization

Read-only audit only. No remote command reached process execution because SSH
authentication failed. No process, service, port, product/source/git, or storage
was modified.

## Commands and outputs

Command attempted:

```text
ssh -p 27460 -o BatchMode=yes -o ConnectTimeout=15 i-1.gpushare.com \
  'date -Is; hostname; nvidia-smi --query-gpu=index,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu --format=csv,noheader; echo "--- processes ---"; ps -eo user=,pid=,ppid=,lstart=,etime=,args= --sort=pid | grep -E "[n]euron|[s]glang|[p]ython|[t]orch|[c]uda" || true; echo "--- gpu processes ---"; nvidia-smi; echo "--- port 30000 ---"; (ss -ltnp "sport = :30000" || true); (lsof -nP -iTCP:30000 -sTCP:LISTEN || true); echo "--- relevant services ---"; (systemctl --no-pager --type=service --state=running 2>/dev/null | grep -Ei "sglang|neuron|vllm|llm" || true)'
```

Observed output:

```text
dev-codex@i-1.gpushare.com: Permission denied (publickey,password).
```

A read-only local SSH configuration check confirmed the effective target user
was `dev-codex`, port `27460`, with default identity paths only. No host-specific
entry for `i-1.gpushare.com` was present.

## Findings

| Requested item | Result |
|---|---|
| Current GPU PID(s) | Not observable; SSH authentication blocked |
| Command/owner classification | Not observable |
| VRAM/utilization | Not observable |
| Neuron process active | Cannot determine |
| Port 30000 occupied | Cannot determine |
| Safe recommendation | Pending authenticated read-only access; preserve the Neuron experiment and do not resume/alter SGLang until state is verified |

## Changed resources

Only this audit report was created. No remote resource was changed.

## Verification evidence

The remote SSH command was rejected before any requested read-only audit command
could run. Therefore there is no valid remote GPU/process/port evidence and no
basis to recommend `wait` versus `resume` from current state.

## Followups

Provide valid authorized read-only SSH authentication for `dev-codex@i-1.gpushare.com:27460`,
then rerun this same audit under a fresh Task ID.

## Open issues

- Authentication credentials/key authorization are unavailable or rejected.
- GPU ownership, Neuron liveness, SGLang state, and port 30000 occupancy remain unknown.
