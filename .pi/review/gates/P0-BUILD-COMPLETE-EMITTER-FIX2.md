ENTRY: ACCEPT

# P0 durable V3 `build_complete` emitter FIX2 independent gate review

- Task ID: `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX2`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT** (unit emitter gate only)

## Scope and authoritative inputs

Read-only review of:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- `tools/p0_session_barrier_vehicle.py`
- `python/sglang/srt/mem_cache/trace_context.py`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- accepted `review/gates/P0-BUILD-COMPLETE-EMITTER-FIX1.md`
- rejected `review/gates/P0-BUILD-COMPLETE-EMITTER.md`
- `DEVOPS-20260908-P0-S25-LIVE-R4-EXACT.md`

The expected `COD-20260908-P0-BUILD-COMPLETE-EMITTER-FIX2.md` summary was not
present in the designated memory work directory. This review therefore relies on
the implementation, focused fixture, accepted FIX1 gate, architecture contract,
and the supplied R4 terminal report rather than coder claims. The worktree is
also dirty with unrelated earlier Phase-2 changes and has no task-specific commit
boundary; attribution of the aggregate diff remains a caveat.

No product, vehicle, launcher, ledger, or prior gate artifact was modified by
this review. Only this gate report was written in the product worktree.

## R4 failure and FIX2 verification

The supplied R4 report records a scheduler exception:
`AttributeError: 'int' object has no attribute 'get_last_hash_value'`, with
zero eligible sessions and terminal verdict `NOT_VERIFIED`. This is consistent
with the current TreeCore contract: `NodeId = int` in
`unified_cache/unified_tree_core_interface.py:15-17`, `node_by_id` resolves that
handle through the arena at `unified_cache/unified_tree_core.py:529-534`, and
`UnifiedTreeCore` exposes integer node IDs from insert results at
`unified_cache/unified_tree_core.py:853-858`.

FIX2 closes that runtime representation mismatch in
`unified_radix_cache.py:928-944`:

1. It obtains the finalized `result.last_device_node` handle.
2. If the handle is not already a node object with `get_last_hash_value`, it
   resolves it through `self.tree_core.node_by_id(handle)`.
3. Missing/invalid handles fail closed on the tree lookup exceptions.
4. The resolved node is then checked for non-root identity, non-empty string ID,
   and non-empty string final hash before any event is logged.

The production path assigns the same returned handle to `req.last_node`, records
node context, and invokes the emitter before cleanup at
`unified_radix_cache.py:1883-1899`. The source and the actual TreeCore interface
therefore agree on the integer runtime path exposed by R4.

## Requirement review

### Exact node, hash, and context readback — PASS

The emitter uses the resolved finalized node, derives `node_id` from that node,
reads `final_kv_hash` from that same node, and requires
`_t38c_trace_context_for_node(node_id) == context` at
`unified_radix_cache.py:938-947`. It does not substitute a request ID,
operation ID, ancestor, or response header for the node/hash readback.

The focused fixture's integer case at
`test/registered/unit/mem_cache/test_p0_trace_context_v4.py:160-166` resolves handle `17` through a
fake `node_by_id`, then asserts the emitted ID and hash. An independent
AST-extracted probe additionally recorded exactly one lookup of integer handle
`17` and observed `node_id=leaf-17`, `final_kv_hash=hash-17`.

### Missing/invalid fail-closed behavior — PASS

The fixture covers missing integer and object handles at lines 168-177, and the
invalid result/root/empty-hash cases at lines 201-209. The independent probe
also exercised missing integer, unhashable list, and arbitrary object handles;
all returned without an exception and emitted zero records. Root resolution is
checked after lookup at lines 936-937, so an integer root ID cannot publish.

### FIX1 conflict-aware binding — PASS

The accepted FIX1 logic remains present at
`unified_radix_cache.py:851-880`: it detects differing candidate contexts or
prior ambiguity and stores `None` in the node-only index rather than allowing a
later context to become authoritative. An independent source-extracted probe
bound one node to `s1/r1`, attempted `s2/r2`, and observed the index remain
`None`. This preserves the emitter's exact readback failure at line 946 and
prevents a conflicting build identity.

### Marker, V3, RID, finished, abort, and warm semantics — PASS

The guard at `unified_radix_cache.py:902-910` requires the marker, insert path,
non-abort result, a finished request, and the TP publication rule. Lines
912-926 require exact `p0_durable.v3` context, non-null generation, non-empty
session/build RID, no warm RID, and `req.rid == context["build_rid"]`. The event
uses the existing durable logger and supplies `warm_rid=None`, null storage
operation/attempt IDs, and `result=True` at lines 949-962. The focused fixture
covers marker-off, explicit abort/non-insert, unfinished, warm RID mismatch,
and missing-context cases at lines 179-231.

### TP publication — PASS

`_t38c_is_tp_group_leader` at `unified_radix_cache.py:882-896` permits TP=1,
requires initialized distributed state and `get_rank(group=self.tp_group) == 0`
for TP>1, and fails closed for missing/ambiguous state. It has no global-rank
fallback. The fixture exercises leader, non-leader, uninitialized, and missing
group cases at `test_p0_trace_context_v4.py:235-275`.

### Boundary and ordering — PASS

The call at `unified_radix_cache.py:1883-1893` follows insert result creation,
`req.last_node` assignment, and node-context binding, and precedes component
cleanup. The fixture statically asserts bind < emit < cleanup at
`test_p0_trace_context_v4.py:136-140` and checks the logical ordering of
`build_complete` before later persistence/barrier evidence at lines 142-152.
No emitter call is present in the unfinished path.

### Duplicate and reopen semantics — PASS

The implementation does not introduce mutable build deduplication state. Exact
repeated identities remain exact duplicates, as allowed by the contract, while
the RID and generation gates prevent a warm or reopened generation from
reusing the old build identity. The fixture checks two exact duplicate records
and a new generation/build RID at `test_p0_trace_context_v4.py:277-312`.
The vehicle continues to count identity conflicts and reject non-exact joins;
no vehicle change was made.

### Compatibility and scope — PASS with attribution caveat

The change preserves the existing V3 logger/context path, does not emit a V2
compatibility build event, and does not change vehicle, launcher, durability, or
storage semantics. The reviewed FIX2 surface is the normalization/readback
branch and its focused integer fixture. The broader dirty checkout contains
unrelated product and fixture modifications, so full-worktree authorship cannot
be independently attributed to FIX2.

## Independent evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**;
  `P0 trace-context V4.3 focused checks: PASS`.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-build-complete-fix2
  python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**.
- Independent AST parse of both reviewed files — **PASS**.
- Independent AST-extracted integer lookup/readback probe — **PASS**; exact
  integer lookup, node ID, hash, and event identity were observed.
- Independent invalid-handle probe — **PASS**; missing, unhashable, and
  arbitrary handles emitted no event and raised no exception.
- Independent AST-extracted FIX1 conflict probe — **PASS**; conflicting node
  contexts left the node-only index `None`.
- `git diff --check --
  python/sglang/srt/mem_cache/unified_radix_cache.py` — **PASS**.
- `git diff --no-index --check /dev/null
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — exit `1` because the fixture is
  untracked and differs from `/dev/null`; no whitespace diagnostics were
  produced.
- No engine, pytest, launcher, remote, deployment, or fresh live S=25 vehicle
  run was performed by this unit review.

## Findings

No blocking or non-blocking implementation findings identified for the FIX2
unit gate.

## Verdict

`done`; gate **ACCEPT** for the narrow product emitter and focused fixture.
FIX2 addresses the actual R4 integer-node runtime failure while preserving the
accepted FIX1 conflict, fail-closed, V3 identity, lifecycle, TP, and ordering
semantics. This verdict does not convert the supplied R4 run into acceptance:
that run remains `NOT_VERIFIED` with zero eligible sessions and must be followed
by a fresh authorized live run and independent runtime gate.

## Followups

- Dispatch the fresh live S=25 RH-off runtime run against this accepted unit gate.
- Independently verify 25/25 exact V3 identity joins, causal build/KV/Mamba/
  durability/residency/warm ordering, and no runtime exception.
- Preserve the R4 evidence bundle unchanged as a failed diagnostic baseline.
- Provide or archive the missing FIX2 coder summary if task provenance requires a
  complete dispatch packet.

## Open issues

1. Live runtime/vehicle acceptance remains outstanding; R4 is terminal
   `NOT_VERIFIED` with the integer-node exception.
2. The designated FIX2 coder summary artifact was not present in the memory work
   directory.
3. The dirty worktree has no task-specific commit boundary, so aggregate diff
   attribution remains a process caveat.
4. Existing V4.3 rank-topology concerns remain outside this emitter gate.
