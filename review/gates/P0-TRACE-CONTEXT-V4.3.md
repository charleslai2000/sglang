ENTRY: ACCEPT

# P0 trace-context V4.3 independent gate review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V4.3`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Product trace-gate verdict: **REJECT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Revision identity and scope

Reviewed the dirty worktree at commit `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`
on branch `3090-24g-opt`, against
`review/gates/P0-TRACE-CONTEXT-V4.2.md` and the V4.3 coder report
`COD-20260908-P0-TRACE-CONTEXT-V4.3.md`.

Current SHA-256 identities:

- `trace_context.py`: `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e`
- `hybrid_cache_controller.py`: `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501`
- `unified_radix_cache.py`: `238549049bb801de5fdd2320db943e9777bf4ec332c168cb0fad275498c7dade`
- `hiradix_cache.py`: `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845`
- `test_p0_trace_context_v4.py`: `7f1057853daecc52c214b967e9ee3f9fb26bbbdc1b39eb5b594392fe6d6a931d`
- `mamba_component.py`: `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f`
- `extent_allocator.py`: `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b`
- `extent_file_backend.py`: `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600`

The V4.3 delta adds the inert token, paired release queues, rank ACK
aggregation, and session-token retirement. The worktree also contains the
pre-existing dirty Mamba/extent changes and unrelated vehicle/tool files;
they were not modified or silently accepted as part of this gate. The Mamba
component hash is unchanged from the V4.2 report. No remote engine or vehicle
was run.

## Evidence

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-rev-v43 python3 -m py_compile` on
  trace context, Unified, controller, HiRadix, Mamba, extent allocator,
  extent backend, and the focused fixture — **PASS**.
- Independent `ast.parse` on the same eight files — **PASS**.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4.3 focused checks: PASS`.
- `git diff --check` — **PASS**.
- Targeted `python3 -m pytest 3090-dev/test_p0_trace_context_v4.py -q` —
  **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
- Independent AST-extracted probe of `_t38c_retire_session_trace` with a
  candidate containing `"trace_context": None` — **FAIL reproduced**:
  `AttributeError: 'NoneType' object has no attribute 'get'`.
- Direct module import for a runtime object probe was unavailable because this
  environment lacks `orjson`; the lifecycle finding was nevertheless
  reproduced from the exact function body without importing the application.

## Findings

### F-1 — High / blocking: session retirement crashes on marker-off candidates

Locations: `unified_radix_cache.py:744-759`, especially line 749; candidate
creation is at `unified_radix_cache.py:4575-4622`, and the public retirement
paths are `unified_radix_cache.py:5462-5480`.

`_t38c_retire_session_trace` evaluates:

```python
candidate.get("trace_context", {}).get("session_id")
```

When the marker is off, `operation.trace_context` is `None`, so candidate
creation stores `"trace_context": None`. Candidate evidence is still recorded
for a completed storage ACK. A later `release_session`, `release_radix_session`,
or session reopen then dereferences `None` and raises `AttributeError` before
retiring evidence, queued completion state, and slot contexts. The independent
probe reproduced this exact exception.

Acceptance impact: **merge-blocking**. This violates the required
queued-completion/session/reset retirement contract and regresses normal
marker-off session lifecycle behavior. The focused fixture only checks a
trace-context model and does not execute retirement against a `None` context.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE`.
Make candidate context matching null-safe, preserve marker-off session APIs,
and add a regression test with stored evidence whose context is absent.

### F-2 — Medium / compatibility acceptance open: rank-topology fallback is not authoritative

Location: `hybrid_cache_controller.py:507-518`.

The preferred `torch.distributed.get_process_group_ranks()` path captures the
actual process-group ranks. If that API is unavailable, the fallback uses
`list(range(world_size))`, which is not the actual rank set for a non-contiguous
TP process group. The subsequent aggregate ACK check compares observed actual
ranks against this synthetic set and can fail closed without ever accepting a
valid multi-rank operation. This is safer than a false combined barrier, but it
does not meet the requirement that expected topology be authoritative across
supported runtime versions.

Acceptance impact: **non-blocking follow-up for the current rejection**, but
multi-rank acceptance remains compatibility-dependent until the topology source
is authoritative or the unsupported runtime is explicitly gated.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.3-RANK-TOPOLOGY`.

## Positive checks and bounded non-findings

- The release producer publishes one page and one token under
  `_t38c_release_handoff_lock`; marker-off and missing-context releases use
  `INERT_RELEASE_TOKEN`. Unified and HiRadix consume paired metadata through
  `_t38c_pop_host_mem_release_pair`, preserving page/token FIFO alignment.
- `complete_slot_context` is exact-token-only and rejects both `None` and the
  inert token. The V4.2 same-digest fallback is removed from that helper.
- Mamba multi-rank proof uses `all_gather_object` and matches exact
  operation/attempt/node/hash before requiring every expected rank. Single-rank
  proof uses the actual rank and requires the expected set; no mutable current
  selector was found.
- Mamba key count, ordered key-set digest, expected/succeeded page counts, and
  operation/attempt/node/hash fields are propagated through the ACK/candidate/
  barrier path. Empty Mamba evidence is fail-closed.
- Reset clears trace evidence, completion/barrier sets, slot contexts, and the
  controller handoff queues. The intended session cleanup includes completed
  queued tokens, but F-1 prevents accepting the lifecycle as implemented.
- The narrow HiRadix change only switches the Hybrid-controller path to paired
  consumption; the fallback for the legacy controller remains page-only. No
  new marker-off page-freeing mutation was found in the HiRadix diff.
- The inherited V4.2 marker-off storage-query compatibility concern remains
  open: V4.3 does not gate or revert the additional `_storage_hit_query`
  behavior. This is not reclassified as fixed by this review.

## Verdict and P0 distinction

The V4.3 product trace gate is **REJECTED** because F-1 is blocking. The
focused fixture, compile, AST, and diff checks do not overcome the reproduced
marker-off session-retirement exception. F-2 and the inherited marker-off
query compatibility issue remain follow-ups.

P0 runtime acceptance remains **BLOCKED** independently of this product
verdict. Keep P0 blocked until the live **S=25 RH-off** vehicle passes with
barrier-before-lookup ordering, 25/25 build evidence, exact `s00002` A-E
classification, cleanup, and runtime health. This review did not run that
vehicle or any remote engine.

## Status packet

- Status: `done`
- Artifacts: this gate report only; no reviewed artifact, vehicle, memory file,
  or remote process was modified or run.
- Evidence: prior-gate/design review, dirty revision and hash capture, source
  and queue/rank/lifecycle inspection, exact retirement probe, py_compile PASS,
  AST PASS, focused fixture PASS, diff-check PASS, and pytest dependency
  blocker.
- Followups: fresh Task IDs are listed for F-1 and F-2; no extra work was
  accepted under this invocation.
- Open issues: F-1 session retirement crash, F-2 topology fallback,
  inherited marker-off query compatibility, pre-existing extent/vehicle dirty
  scope, unavailable pytest dependency, and required live S=25 RH-off vehicle
  evidence.
