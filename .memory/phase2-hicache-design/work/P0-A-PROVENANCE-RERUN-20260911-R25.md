status: blocked

artifacts: []

evidence:
- The executor's first local command failed shell parsing before SSH/scp (`unexpected EOF while looking for matching quote`).
- No remote target was contacted; no backup, transfer, hash gate, or pytest occurred.

summary:
- R25 produced no P0-A evidence and must not affect the prior corrected green-run evidence except that provenance remains unresolved.

followups:
- Dispatch a fresh executor using Python `subprocess.run([...])` argument lists or a safely generated script, not nested shell quoting.

open_issues:
- Clean independently auditable P0-A rerun still outstanding.
