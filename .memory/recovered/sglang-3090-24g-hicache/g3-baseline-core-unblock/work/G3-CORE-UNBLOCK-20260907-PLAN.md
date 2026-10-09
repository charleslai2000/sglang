# G3-CORE-UNBLOCK-20260907 — E3 task-manager report

ENTRY: ACCEPT

status: done

frontier: waiting

The newly confirmed old E2 wrapper PID `368185` is still active: C1 is complete
and C4/repeat-1 is running. The E3 smoke is therefore waiting until that wrapper
and all of its children/telemetry exit and the service/GPU are idle. No E3 traffic
may start concurrently.

## Objective and scope

The E3 authorization was converted into an executable DAG for:

1. audit of pre-existing random-ids activity;
2. one-request native-SGLang smoke with `random-ids --tokenize-prompt`;
3. independent smoke gate verification;
4. unchanged-v1 Production Profile A at C1/C4/C5;
5. independent A verification;
6. an exclusive, separately specified true-C16 Profile B launch/admission;
7. serialized B decode and prefill matrices;
8. B restoration and independent verification.

The plan was amended for the confirmed E2 wrapper activity. Its data remains
excluded from E3 and cannot be merged or treated as admitted evidence without a
separate independent admission decision.

Only the authorized experimental host `175.155.64.171:22109` is in scope. The
service at `127.0.0.1:8035`, PID `298123`, must remain unchanged through A and
must not receive C8/C16 traffic. No ShareGPT download, `random` dataset, random
text, benchmark-side GGUF loading/parsing, product/MMQ edit, or other host is in
scope.

## Inputs and confirmed baselines

Read in full or by targeted evidence extraction:

- repository `AGENTS.md`;
- `.memory/g3-baseline-20260907/ledger.md`, `context.md`, and prior `plan.md`;
- all prior task reports and raw evidence under `.memory/g3-baseline-20260907/work/`;
- `HANDOFF-CONTINUE.md`.

Relevant confirmed facts:

- E2 A is blocked, with no claimable measurement: the old runner OOMed before
  `/generate`; that evidence remains immutable and is not reused as E3 results.
- The GGUF-safe runner patch is settled and byte-identical locally/remotely at
  SHA-256 `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`.
- E2 runbook v2 resolved exact-length synthetic binding to
  `random-ids --tokenize-prompt`; decoded text without the flag was not exact.
- The deployed interpreter is `/data/sglang-qwen35-env/bin/python`, source is
  `/data/sglang-qwen35/python`, and deployed SGLang is `0.5.10.dev0`.
- A protocol is C1/C4/C5 with ISL 2048, OSL 512, prompts 20/40/50. E2 B decode
  protocol is C1/C4/C8/C16 with ISL 1024, OSL 1024, prompts 32/32/64/128.
  E2 B prefill is C1/20 prompts at ISL 2048/8192/32768 with OSL 32.
- `/metrics` and usable `pmon` attribution are unavailable; required telemetry is
  dmon, one-second GPU queries, `/v1/loads?include=all`, and before/after queries.

## Plan artifact

The append-only E3 DAG is in:

`.memory/g3-baseline-20260907/plan.md` under `Epoch E3 — G3 core unblock DAG`.

The nodes, owners, dependencies, disjoint write sets, process scopes, acceptance
criteria, evidence requirements, serialization reasons, and child-dispatch contract
are recorded there. The strict dependency chain is:

```text
AUDIT
  -> SMOKE-EXEC -> SMOKE-VERIFY
  -> PROD-A-EXEC -> PROD-A-VERIFY
  -> B-RUNBOOK -> B-LAUNCH-ADMIT
  -> B-DECODE -> B-PREFILL -> B-RESTORE -> B-VERIFY
  -> SYNTHESIS
```

The only current ready node is `G3-E3-AUDIT-20260907`. Formal traffic is not
admitted until the smoke verifier proves all five user-required gates. Profile B
is strictly serialized after independent A acceptance and its own launch runbook.

## Acceptance design

The smoke verifier must independently establish all of the following from raw
evidence, not executor claims:

- native `--backend sglang`, one successful request;
- fixed 2048/512 lengths, ratio 1.0, seed 42, `random-ids`,
  `--tokenize-prompt`;
- no benchmark-client GGUF load/parse, with small/stable client RSS;
- no network or dataset download;
- server-observed exact input length;
- unchanged A service identity and health.

A is accepted only after nine successful, independently flushed measured repeats
with exact commands and complete raw artifacts. Exactly three kernel warmup
requests are permitted only for the initial run of each service/profile; all
later repeats use `--warmup-requests 0`. The one-request smoke uses warmup 0.
B is accepted only after its
temporary service demonstrates observed `max_running_requests >= 16`, completes
both frozen matrices with three flushed repeats per point, restores the v1 service,
and passes independent recomputation and invariant review.

## Open issues and followups

The exact Profile-B launch/transition is intentionally unresolved and is a hard
planning gate, not an invitation to improvise. A `devops` runbook task must freeze:

- a currently free temporary port (8036 is not reserved);
- full launch and rollback argv;
- Mamba-slot/cache sizing and `max_total_num_tokens` sufficient for the 32K case;
- safe GPU memory fraction and process ownership;
- explicit stop/start/restore PID-tree procedure;
- evidence that all required capacity flags already exist in the deployed source.

If any of these cannot be established without a product/MMQ edit or an unapproved
host change, B is `blocked` and requires a fresh Task ID. No child may lower the
`max_running_requests >= 16` admission threshold or merge prior-run artifacts.

The E3 plan itself makes no benchmark calls, SSH changes, service transitions, or
product edits. No children were spawned, as required for this planning task.

Followups:

- dispatch `G3-E3-AUDIT-20260907` first;
- wait for E2 wrapper PID `368185` and its children/telemetry to finish, then
  independently confirm the service/GPU is idle before dispatching smoke;
- dispatch smoke execution only after the audit is clean and the drain gate passes;
- dispatch A only after independent smoke verification is PASS;
- dispatch B runbook/launch only after independent A verification is PASS;
- keep MMQ implementation and post-MMQ reruns outside this E3 baseline DAG and
  require fresh Task IDs.

Evidence paths read: `.memory/g3-baseline-20260907/ledger.md`,
`.memory/g3-baseline-20260907/context.md`, `.memory/g3-baseline-20260907/plan.md`,
`.memory/g3-baseline-20260907/HANDOFF-CONTINUE.md`, and the prior reports/raw files
under `.memory/g3-baseline-20260907/work/`.

Invocation final status: done
