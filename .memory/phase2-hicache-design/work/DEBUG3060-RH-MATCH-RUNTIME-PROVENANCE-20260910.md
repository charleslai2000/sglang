# DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910

status: done
entry: ACCEPT
task_id: D3060-RH-MATCH-PREPARE-RUNTIME-MISMATCH-20260910
invocation_id: INV-20260910-DEBUG-RUNTIME-PROVENANCE-R1
orchestration_epoch: 20260910-rh-runtime-provenance
role: debugger-deep
capability_level: L2

## Binding and communication

- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs:
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/SCOUT3060-RH-MATCH-PREPARE-BYPASS-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-PROBE-SHORT-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-DEPLOY-20260910.md`
  - `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/escalations/ESC-20260910-RH-MATCH-RUNTIME-MISMATCH.md`
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (`pwd` and Git root agree).
- Native event call: attempted for `ENTRY`; the server returned unavailable. A terminal `DONE` call was also attempted, but the callable was then absent from the runtime. Communication path degraded. Last successfully sent event: none.
- Scope observed: read-only local and remote inspection only. No HTTP, restart, signal, process attach, source edit, or HiCache mutation was performed.

## Causal classification

**Confirmed classification: the missing event is an observability failure inside or at the boundary of `_emit_rh_match_prepare`, not a legal READY_HORIZON policy bypass and not a source/bytecode provenance mismatch.**

The exact inner failure is not recoverable from the existing runtime because the emitter has a bare `except Exception: pass` around both field construction and `logger.info` (`scheduler.py:4442-4470`). The most likely subcase is an exception while evaluating one of the dynamic telemetry fields before `logger.info` is called. A message-selective live logging filter/handler remains a lower-confidence alternative; it cannot be excluded without inspecting the live Python heap, which passive `/proc` inspection cannot expose and this dispatch did not attach to the service.

Confidence:

- semantic-bypass rejected: high (about 0.93)
- alternate imported source / stale pyc rejected: high (about 0.95)
- swallowed telemetry-expression or logger-call exception: leading explanation, moderate-high (about 0.75)
- message-selective logger filtering/routing: remaining alternative, low-moderate (about 0.20)

Percentages are hypothesis weights, not independent probabilities.

## Timeline reconstruction for RID `33b6b9918d62429ba22f15aa61ca54c4`

All observations are from the raw replacement log `/tmp/sglang3060-rh-match-emit-03a170-20260910.log`; it was 375,089 bytes at audit time.

1. The request reached execution in the prior bounded probe: HTTP 200, `prompt_tokens=55022`, same RID.
2. Raw log byte offset 47,653 records `[P2A] evt=prefetch_issued` with `prefetch_length=55021`.
3. At raw offset 47,778, restore state becomes `RESTORING`.
4. The first request-correlated P3 record begins at raw offset 48,997: `rh_preadmission.v1`, `rh_pass_seq=879591`, `decision_id=<RID>:rh:879591`, `decision=issue`, `issue_origin=READY_HORIZON`, `attempt_id=<RID>:prefetch:1`, and crucially `staging_eligible=True`, `restore_potential=True`.
5. At raw offset 48,997, its monotonic timestamp is `8681671333158178` ns. The stage record begins at raw offset 48,997 plus its preceding record length; its timestamp is `8681671333249350` ns, only **91,172 ns** later. It has the same decision and attempt IDs, `schema=rh_stage.v2`, `result=issued`, and `restore_state_after=RESTORING`.
6. A whole-file raw-byte schema search found 24 `rh_preadmission.v1`, one `rh_stage.v2`, 22 `rh_admission.v2`, and zero `rh_match_prepare.v1` or `rh_ready_host.v1` occurrences. Targeted `dd | xxd` output around offsets 47,000, 47,600, 48,000, and 48,650 contains the P2A, P3 preadmission, and P3 stage bytes and no omitted match record.
7. The next RH decision for this RID is `exclude` because of `negative_cache`; it does not explain the already-issued stage.

`staging_eligible=True` is produced from the prepared-match map in the audited source. `_ready_horizon_pass` first prepares each frontier request (`scheduler.py:4665-4669`), then constructs views, and only prepared-map entries can become `plan.to_issue`; the issue loop invokes stage (`scheduler.py:4760-4767`, `4833-4857`). The successful prepare branch calls `_emit_rh_match_prepare` immediately before returning its prepared object (`4567-4576`). Therefore, the raw stage record proves a prepared match was available and makes a normal bypass incompatible with this exact source flow.

## Remote provenance evidence

- Live service PID was still `127023`, launched as `/root/sglang-env-3060-4b/bin/python -m sglang.launch_server ... --enable-ready-horizon ...`; its cwd is `/root`, executable `/usr/bin/python3.11`, and environment has no `PYTHONPATH` or `PYTHONHOME` override. `PATH` begins with the stated virtual environment.
- The current remote source is `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py`, SHA-256 `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb8466`, exactly equal to local commit `03a170ef4f35fe1d87d80a7b6f09e83261aef94e`.
- A non-service proxy interpreter using that exact virtualenv, cwd, and inherited import setup (with `PYTHONDONTWRITEBYTECODE=1`) returned:
  - `find_spec('sglang').origin = /root/sglang-3060-12g-hicache/python/sglang/__init__.py`
  - `find_spec('sglang.srt.managers.scheduler').origin = /root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py`
  - imported `module.__file__` equal to that scheduler path.
  - `sys.path` includes the virtualenv site-packages and the editable-package finder path; no miniconda SGLang directory appears.
- The adjacent scheduler pyc is `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/__pycache__/scheduler.cpython-311.pyc`, SHA-256 `fc1c8aa82c7590d0ae34b8967cf1b105f9839263704d11c5c975c78877d638c6`. Its CPython timestamp header has flags `0`, mtime `1788961092`, and source size `368658`; these exactly equal the deployed source integer mtime and size. It was written after the source (21:39:26 vs. 21:38:12), so it is valid for that source rather than stale bytecode.
- A separate old miniconda scheduler and old backups exist on disk, but neither is selected by the proven virtualenv editable import resolution. There is no evidence they are imported by PID 127023.

This is strong provenance evidence, but direct readout of the running interpreter's in-heap `sys.modules` is explicitly missing: no debugger/ptrace/eval attach was performed because it could pause or otherwise disturb the live service and was outside this read-only audit's safe method.

## Logger evidence and competing hypotheses

`scheduler.py` defines exactly one module logger: `logging.getLogger(__name__)` at line 386. Both `_emit_rh_match_prepare` and the observed `rh_stage.v2` call `logger.info` on that same logger (lines 4442-4468 and 4833 onward). Thus a simple logger-level disablement or ordinary handler absence cannot explain stage being captured while match is not.

The proxy import's default logger state was observed, but is **not asserted as the live process state**: scheduler logger level `NOTSET`, effective root level `WARNING`, `propagate=True`, zero handlers and filters. The real launcher clearly configures output later because the live P3 stage record is present. Passive process inspection cannot safely enumerate that process's live logger object names, effective levels, handlers, or filters. This missing evidence leaves a custom message-sensitive handler/filter as a residual alternative.

The leading alternative is better supported by the code: the emitter evaluates potentially dynamic operations (`str(anchor)`, `len(prefix_indices)`, `host_hit_length`, and object attribute access) inside the same broad silent exception boundary as `logger.info`. Any one exception prevents a match record without changing scheduler control flow. The 91-us preadmission-to-stage transition is consistent with exactly that silent continuation.

## Minimum next fix and verification oracle

No fix was applied in this dispatch.

The minimum downstream **telemetry-only** fix is to replace the bare silent catch at `scheduler.py:4469-4470` with a failure marker that cannot evaluate request-derived objects, for example a fixed `[P3] evt=rh_match_prepare_emit_failed schema=rh_match_prepare_emit_failed.v1 rid=<already captured safe rid>` record plus exception type, protected by a final narrow logging-failure guard. Preserve the current `rh_match_prepare.v1` schema and all scheduling behavior; do not add a stage bypass or alter prepared-map policy.

The verification oracle for a fresh coder/tester/devops dispatch is:

1. A focused unit test makes one telemetry field accessor (for example `prefix_indices` or `host_hit_length`) raise. It must prove scheduler behavior and stage eligibility are unchanged, `rh_match_prepare.v1` is absent only for that injected fault, and exactly one `rh_match_prepare_emit_failed.v1` marker carries the RID and exception class.
2. A normal focused test asserts the existing `rh_match_prepare.v1` record and its nullable fields still appear.
3. Only after those tests pass, one newly authorized bounded live probe must show either a normal `rh_match_prepare.v1` before the same RID's `rh_stage.v2`, or the explicit failure marker. The absence of both is a failed oracle and specifically reopens the live handler/filter hypothesis.

## Artifacts and evidence

artifacts:

- this report
- remote raw log: `/tmp/sglang3060-rh-match-emit-03a170-20260910.log` (read only)
- prior raw response: `/tmp/rh-match-emit-probe-short-03a170-20260910.raw`

evidence:

- local `HEAD=03a170ef4f35fe1d87d80a7b6f09e83261aef94e`; local/remote scheduler SHA match
- remote PID 127023 cmdline, cwd, executable, selected environment, editable import resolution, source/pyc metadata and hashes
- raw schema offsets/counts and byte hexdumps around the RID's issue, preadmission, and stage records
- `python/sglang/srt/managers/scheduler.py:386, 4442-4470, 4567-4576, 4665-4669, 4760-4767, 4833-4857`
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py:502-545`
- supplied scout, operations, and escalation reports listed in the binding

summary: done; source, editable import resolution, and validated pyc align with commit 03a170. The raw RID timeline proves a prepared match fed READY_HORIZON stage, while the match emitter produced no bytes. The only source construct that permits that continuation is its broad swallowed telemetry exception; a message-sensitive live logger filter remains unobserved but secondary.

followups: fresh bounded downstream invocation for the telemetry-only catch replacement and focused tests; then a separately authorized single live verification probe. No restart, process attach, or policy change is indicated by this diagnosis.

open_issues:

- The exact exception class/value inside `_emit_rh_match_prepare` is unrecoverable from this build because it is swallowed.
- Live process logger handlers, filters, and levels were not directly observable without an intrusive attach; proxy logger state is not a substitute.
- No claim is made about HiCache performance, restore value, cache-hit value, allocator behavior, or Mamba behavior.
