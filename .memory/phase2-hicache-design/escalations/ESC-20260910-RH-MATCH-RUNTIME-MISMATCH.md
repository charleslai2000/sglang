# Escalation packet: 3060 RH match-prepare runtime mismatch

```yaml
task_id: D3060-RH-MATCH-PREPARE-RUNTIME-MISMATCH-20260910
invocation_id: 20260910T-FRESH-DEBUG-RH-MATCH-02
epoch: E3060-RH-MATCH-EMIT-20260910
current_level: L3
target_level: L2
owner_role: debugger-deep
decision_role: debugger-deep
return_role: devops-executor/coder
parent_invocation: 20260910T-FRESH-OPS-PROBE-SHORT-01
decision_owner: orchestrator
```

## Precise question

Why did the hash-pinned 3060 service execute request `33b6b9918d62429ba22f15aa61ca54c4`, emit `rh_stage.v2`, but emit zero `rh_match_prepare.v1`, after commit `03a170ef4f35fe1d87d80a7b6f09e83261aef94e` was deployed?

## Confirmed facts

- Local branch is `3060-12g-qwen35-4b`; accepted commit is `03a170ef4f35fe1d87d80a7b6f09e83261aef94e`.
- Independent tester and reviewer accepted the narrow code gate; 19/19 focused tests, compile, AST, and diff checks pass.
- Remote scheduler SHA is `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb8466`, matching local `scheduler.py`.
- The remote service remained on known PID `127023`, health HTTP 200 before and after the probe.
- The corrected single request used only `text` and `sampling_params`, returned HTTP 200, and reported `prompt_tokens=55022`; model execution is proven.
- Request-correlated post-probe events: two `rh_preadmission.v1`, one `rh_stage.v2`; zero `rh_match_prepare.v1`, `rh_ready_host.v1`, and `rh_admission.v2`.
- Prior source audit said the expected preparation path should call the match emitter; prior live audit also saw stage without match.

## Attempted approaches and results

- Nullable-field eager formatting fix: code gate passed, but live event remained absent.
- First probe with unsupported `rid`: rejected before model execution; not evidence for runtime behavior.
- Second probe with repeated long phrase: rejected at 1,265,001 tokens; not evidence for runtime behavior.
- Third probe with single-character 55K-token shape: executed successfully, still no match event.

## Unresolved alternatives

1. The observed stage branch bypasses `_prepare_ready_horizon_match` and its emitter.
2. The emitter call executes but its logger is filtered or routed away.
3. The running process loads a different bytecode/module despite the source hash.
4. A runtime exception still escapes before the logger call.

## Error cost and why L3 cannot decide

Further probes or another source patch without distinguishing these alternatives can waste the experimental host and obscure whether the defect is policy flow, process provenance, or instrumentation. The evidence conflicts between source control-flow expectations and the live event stream, requiring causal reconstruction across scheduler branches, process import provenance, and logger state.

## L2 question and constraints

Inspect local and remote source/call sites, process command/PYTHONPATH/bytecode provenance, logger names/levels/handlers, and raw request-correlated log lines. Do not edit source, restart the service, send HTTP requests, touch unrelated GPU processes, or modify HiCache storage. Return one causal classification and the minimum next action; any fix or probe must be a fresh downstream task.

## Immutable evidence

- `work/OPS3060-RH-MATCH-EMIT-PROBE-SHORT-20260910.md`
- `work/OPS3060-RH-MATCH-EMIT-DEPLOY-20260910.md`
- `work/SCOUT3060-RH-TELEMETRY-AUDIT-20260910.md`
- `work/OPS3060-RH-TELEMETRY-RUNTIME-20260910.md`
- `review/gates/REVIEW-20260910-RH-MATCH-EMIT.md`
