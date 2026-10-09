ENTRY: ACCEPT

status: done

Task ID: TST-20260908-P0-RESIDENCY-R17-TIMING-ASYNC-TRACE
Orchestration epoch: phase2-hicache-design/2026-09-08
Role: test-runner

## Scope and environment

Read-only execution in `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, using only the
three authorized source/gate files. No remote or live system was accessed. No files were modified
by the test run or instrumentation. The repository-local `AGENTS.md` was read; its applicable
instruction is the Pattern Intake/Novel Mechanism gate, which does not authorize implementation
changes for this test-only invocation.

## Exact focused command and result

Command:

```text
python3 3090-dev/test_p0_residency_barrier_emitter.py
```

Exit status: `1`

Exact relevant output:

```text
Six-field leaf/parent sidecar and no-last-write-wins checks: PASS
Exact NodeId/string lookup, missing, and ambiguity checks: PASS
Final-node-only eligibility and bounded parent diagnostic: PASS
Async durability readiness and exact-free retry: PASS
Traceback (most recent call last):
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1303, in <module>
    main()
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 1028, in main
    check_component_snapshot_blocker(regression_namespace, regression_records)
  File "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py", line 984, in check_component_snapshot_blocker
    assert blockers
AssertionError
```

## One-off in-memory trace

The following was run as a one-off `python3 -c` command. It imported the fixture, extracted the
production helper functions in memory, created the same async cache, and printed state after each
requested transition. It did not write source, test, or pycache files.

| point | lifecycle | detach registered/sealed | expected/completed | queue | retired/barriers | outcome/reason |
|---|---|---|---|---|---|---|
| after two `note_detach` | `BUILD_CREATED` | `False` / absent | `2 / 0` | locked, primary empty, extra empty | `-/ -` | first `detach_not_sealed`; attempts `2` |
| after `_t38c_residency_seal_detach` | `DETACH_SEALED` | `True / True` | `2 / 0` | locked, both empty | `-/ -` | `durability_not_ready`; attempts `3` |
| after KV `note_completion` | `DETACH_SEALED` | `True / True` | `2 / 1` | locked, both empty | `-/ -` | still `durability_not_ready`; attempts `4` |
| after MAMBA `note_completion` | `DETACH_SEALED` | `True / True` | `2 / 2` | locked, both empty | `-/ -` | still waiting for durability; attempts `5` |
| after `durability_ready` reconcile | `RESIDENCY_PUBLISHED` | `True / True` before terminal cleanup | `2 / 2` | locked, both empty | `-/ 1 barrier` | published, `all_detached_frees_complete`; attempts `6` |

Detailed trace facts: the first two detach calls each reconciled while unsealed and recorded
`detach_not_sealed`; sealing registered manifest `{('kv','device'), ('mamba','host')}`. Completion
then added one token at a time. Once durability readiness was added, the publication record had
`expected_release_count: 2`, `completed_release_count: 2`, `queue_snapshot_locked: true`,
`primary_queue_empty: true`, `extra_queue_empty: true`, and `reason: all_detached_frees_complete`.
Terminal cleanup removed detached/completed entries and retained one residency barrier.

## First blocking predicate and classification

For the requested async durability retry scenario, there is no blocking predicate: publication
occurs at the final reconcile. The focused fixture's async check is therefore a PASS, not the
reported failure.

The first failing predicate in the full fixture is the fixture assertion `assert blockers` in
`check_component_snapshot_blocker` (line 984). This is a fixture-contract mismatch with the
current production helper behavior, not an async durability retry failure. The failure occurs
after the async check has already passed; no production predicate was shown to prevent async
publication.

## Minimal fix proposal (not applied)

Under a fresh Task ID, align the component-snapshot blocker fixture with the intended contract and
the current production behavior, or revise the production behavior only after an independently
accepted contract decision. Do not weaken the async component/token predicates based on this run.
This report makes no implementation recommendation beyond that routing boundary.

## Summary and followups

- Full focused fixture: failed, exit `1`, at `check_component_snapshot_blocker`, `assert blockers`.
- Async durability retry: reproduced and traced; it publishes successfully after readiness.
- No py_compile was needed.
- No remote/live claim: no remote or live execution occurred.
- Extra corpus, diagnosis, implementation, or test work requires a fresh Task ID.

open_issues:
- The component-snapshot fixture failure requires reroute to the appropriate tester/debugger or
  contract owner; this test-runner invocation does not diagnose or modify it.
