# VERIFY-GATEA-AND-TREE-20260917

Task: VERIFY-GATEA-AND-TREE-20260917 — independent read-only reconnaissance of the
Gate A drop-predicate scope, the F1 relocation-destination reserve, the required-corrections
matrix, the frozen `/opt` production tree, and git facts. Report facts with file:line
citations. No modifications, no workloads.

Scope: read-only inspection of
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`) and
`/opt/sglang/local-prod-v1.2.1-candidate`; read-only git queries; one result artifact written.
No git mutation, no fetch, no server/GPU/test execution, no writes to the reviewed files.

Result: DONE. Answers A–E below. All facts are line-cited or verbatim command output.

---

## A. Gate A drop-predicate scope

### A.1 `parse_storage_events` collection site

File: `3090-dev/gates/production/gate_common.py` (lines 690–718).

Exact collection line:
- `3090-dev/gates/production/gate_common.py:716` — `elif "without backup due to host memory pressure" in ln:`
- `3090-dev/gates/production/gate_common.py:717` — `ev["dropped_no_backup"].append(ln.rstrip("\n"))`

Exact triggering substring (verbatim from :716): `without backup due to host memory pressure`

The predicate is a bare substring test over every console line passed to the function. There is
no per-prompt, per-prefix, graded-target, or subtree-root filter anywhere in `parse_storage_events`
(:697–718), nor is the function given target ids; its only argument is `lines`.

Upstream producer of the matched log line:
- `python/sglang/srt/mem_cache/hiradix_cache.py:1343-1347` —
  `"write_back: KV cache on device are dropped without backup due to host memory pressure, subtree root %d, num_nodes %d"`, `root.id`, `len(nodes)`. The message carries a subtree root id, but the gate does not parse or use it.
- `python/sglang/srt/mem_cache/unified_radix_cache.py:3246-3250` — `"write_back: KV subtree dropped without backup due to host memory pressure, root node %d"`, `node_id`. Same: id emitted, not consumed by the gate's predicate.

### A.2 Binding: target-only vs any-prefix

Fact: the predicate is **NOT bound to the graded target prompt**. It is a global substring test in
`parse_storage_events` (`gate_common.py:716-717`) applied to every line of the console window. Any
prefix's (any subtree's) drop line, including an unrelated filler's drop, is collected into
`dropped_no_backup`; the collected entry is the raw line text (`:717`), with no id extraction.

`dropped_no_backup` is consumed (a) as a list and (b) via `slim_storage_events`
(`gate_common.py:747-748`): `dropped_no_backup_n = len(...)` and a tail of 3 raw lines. No call
site narrows the list to the graded ids.

Conclusion for A.2: **an unrelated filler drop IS collected.** The harness cannot distinguish a
target drop from a filler drop through this predicate, because it never inspects the emitted
`subtree root`/`root node` id.

### A.3 Invalidation sites in `gate_a_content_integrity.py`

- `3090-dev/gates/production/gate_a_content_integrity.py:531` — `ev = gc.parse_storage_events(gc.read_new_lines(console_path, off))` inside `_persist_targets`.
- `:532` — `if ev.get("dropped_no_backup"):`
- `:534-538` — `gate.invalidate("kv subtree dropped without backup due to host memory pressure " ... "the host pool is still mis-sized for the graded prompt")`
- `:539` — `return None` (aborts the persist phase).
- `:327-328` (main) — `if not persist["ok"]: gate.invalidate(persist["reason"]); return _finish(gate)`.

This invalidate fires on the **first non-empty `dropped_no_backup` list within a filler window**
(`_persist_targets` loops fillers at `:523` and re-parses at `:531`; the check is at `:532`).
The message asserts the host pool is "mis-sized for the graded prompt", but the predicate that
triggered it is the unscoped substring test from A.1/A.2. Therefore a filler-only drop — with the
graded target intact — takes the `:532` branch and INVALIDates the run, because the decision is made
on the list being non-empty, not on whether a target ref/page was dropped.

Also relevant: `:607-609` — `gate.check("persist_no_drop_without_backup", True, detail={"events": 0, ...})` is a
**hard-coded True**, so on the success path the check is asserted true unconditionally; the only
effective drop gate is the invalidate at `:532-538`.

Note also `:622` (`"dropped_no_backup_n": len(ev.get("dropped_no_backup", []))` in the failure
return) is reporting only.

Answer A.3: **YES — a filler-only drop can INVALIDATE a run whose graded target is intact.**
Evidence: `gate_a_content_integrity.py:532` branches on non-empty list, `:534-538` invalidates,
`:327-328` terminates; and the list predicate (`gate_common.py:716-717`) has no target scoping.

### A.4 Invalidation sites in `gate_a_f1_cold_l1.py`

`gate_a_f1_cold_l1.py` has three drop-driven effects:

1. Write-back/persist phase (`_persist_chain`, :520-534):
   - `:527` `ev = gc.parse_storage_events(gc.read_new_lines(console_path, off))`
   - `:528` `if ev.get("dropped_no_backup"):`
   - `:530-534` returns `{"ok": False, ... "reason": "kv subtree dropped without backup due to host memory pressure during write-back; host pool still mis-sized for the graded chain"}`
   - main `:270-272` `if not persist["ok"]: gate.invalidate(persist["reason"]); return _finish(gate)` → INVALID.
   - `:308-310` `gate.check("pre_no_drop_without_backup", persist.get("dropped_no_backup_n", 0) == 0, ...)` feeds the pre-sweep precondition gate at `:311-319`, whose failure path invalidates (`:315-318`).

2. Sweep phase (`_sweep_to_wrap`, :655-662):
   - `:655` re-parse; `:657` `out["dropped_no_backup_n"] = len(ev.get("dropped_no_backup", []))`
   - `:658-662` sets `out["abort_reason"] = "kv subtree dropped without backup due to host memory pressure during the sweep (...)"` and returns.
   - main `:324-326` `if sweep.get("abort_reason"): gate.invalidate(sweep["abort_reason"]); return _finish(gate)` → INVALID.

3. Post-reclaim / cold-window checks:
   - `:390-392` `gate.check("post_no_drop_without_backup", post_reclaim["dropped_no_backup_n"] == 0, ...)`;
     `post_reclaim["dropped_no_backup_n"]` is assigned at `:761` from `sweep.get("dropped_no_backup_n", 0)`.
   - `:403-414` if that check is not ok → `gate.invalidate("reclaim executed but its post-state ... no-drop) -- measured request withheld")`.
   - `:463-465` `gate.check("cold_window_no_drop_without_backup", not cold_events.get("dropped_no_backup"), detail={"events": len(...)})` — this is a registered required check; any non-empty list makes it FAIL. Note it is **not** in the invalidate guard at `:466-469` (that guard only covers `cold_request_executed` and `cold_evidence_present`), so a non-empty cold-window drop list is recorded as a failed required check (verdict FAIL per `gate_common.py:321-324`), not as INVALID.

Every one of these is driven by the same unscoped list from `gate_common.py:716-717`.

Answer A.4: **YES — a filler-only drop can INVALIDATE** (persist at `:528-534`; sweep at `:658-662`
→ `:324-326`), and additionally can make a required check FAIL (cold window at `:463-465`), with the
graded target possibly intact, because the source predicate is not target-scoped.

---

## B. F1 relocation-destination reserve

### B.1 Every pre-measurement precondition path in `gate_a_f1_cold_l1.py`

Ordered `gate.check(...)` calls that execute before the measured cold request at `:451`
(`cold = gc.generate(args.port, ids_a, args.max_new)`), with the invalidate path each contributes to:

| line | check name | invalidate/effect |
|---|---|---|
| `:161-164` | `tree_present` | `:168-170` invalidate if preflight fails (note: `tree_present` itself is a required check) |
| `:167` | `preflight_sglang_file_in_tree` | `:168-170` invalidate |
| `:182` | `chain_ok` | `:186-188` invalidate |
| `:183-185` | `chain_fits_context` | `:189-191` invalidate |
| `:201-202` | `port_free_before_launch` | `:203-205` invalidate |
| `:229` | `server_healthy` | `:233-235` invalidate |
| `:230-232` | `server_not_inheriting_lock` | required check (verdict FAIL if not ok) |
| `:237-239` | `server_pythonpath` | required check |
| `:241` | `kv_dtype_gate` | required check |
| `:247-250` | `host_pool_stages_graded_chain` | `:251-257` invalidate |
| `:263-264` | `warm_device_resident` | required check |
| `:295-298` | `pre_target_in_index` | `:311-319` invalidate (group guard) |
| `:299-301` | `pre_head_present` | `:311-319` invalidate (group guard) |
| `:302-303` | `pre_target_slots_known` | `:311-319` invalidate (group guard) |
| `:304-307` | `pre_victim_candidates_known` | `:311-319` invalidate (group guard) |
| `:308-310` | `pre_no_drop_without_backup` | required check (NOT in the `:311-314` group guard) |

The explicit "pre-sweep preconditions failed" invalidate at `:315-318` is gated by exactly four
checks (`:311-314`): `pre_target_in_index`, `pre_head_present`, `pre_target_slots_known`,
`pre_victim_candidates_known`.

Additional pre-measurement invalidate paths not tied to a named `gate.check`: `:186-191`
(`chain_ok`/`chain_fits_context`), `:203-205`, `:233-235`, `:251-257`, `:270-272` (persist failure),
`:324-326` (sweep abort), `:334-335`/`:396-402` (post-sweep), `:420-425` (flush), `:430-431`
(cold filler), `:444-448` (cold-pre membership).

### B.2 Grep for reserve / destination / headroom / relocat

Command: `grep -in "reserve\|destination\|headroom\|relocat" 3090-dev/gates/production/gate_a_f1_cold_l1.py`

Observed matches (complete): lines 14, 15, 16, 24, 27, 33, 34, 250, 360, 364, 556, 622, 623, 639,
666, 670, 702, 718, 721, 724, 727, 732, 781, 808, 820.

Classification of those matches:
- Docstring/comment only: `:14-16`, `:24`, `:27`, `:33-34` (describes refusal as INVALID), `:718`, `:724`.
- `kv_headroom_tokens` in the **host-pool** sizing detail (`:250`): this is host KV-pool headroom, not
  relocation destination capacity.
- `relocated_count`/`reclaim_relocated_n` event counting (`:360`, `:364`, `:556`, `:666`, `:670`, `:702`, `:721`, `:727`, `:781`, `:808`, `:820`).
- `relocation_headroom_bytes` / `reclaim_relocatable` / `fail_closed_reason` appear at `:622-623`
  **only inside `_slim_membership`** — as keys copied out of the offline snapshot dict for reporting.

There is **no** match of the form "reserve", no `reserve`-named env var, config, or arithmetic in
this file. Grep of the whole gate dir for `reserve`/`relocation_reserve`/`destination_capacity`:
only `README.md` prose hits (lines 193, 247, 292, 315) — no code.

Pre-measurement **checks** that reference relocation at all: NONE. The only relocation-capacity
fields are produced by `wal_forensics.py:438-439` (`headroom = max((free_tails[s] for s in range(num_slots) if s != v), default=0)`, `:453` `relocation_headroom_bytes`, `:454` `reclaim_relocatable = headroom >= v_live_bytes`, `:465-471` `fail_closed_reason`), and they are surfaced by the gate only as *reported data* (`_slim_membership`, `:619-623`), never as a `gate.check`.

### B.3 Pre-assert that a relocation destination capacity exists BEFORE the measured request

**ABSENT.**

Evidence:
- No `gate.check(...)` in the pre-measurement set (B.1) reads `relocation_headroom_bytes` or
  `reclaim_relocatable`. The only `gate_reference` to those keys is `gate_a_f1_cold_l1.py:622-623`,
  inside `_slim_membership`, which is a report-shaping function, not a check.
- The first point at which relocation adequacy could block a verdict is **post-measurement**: the
  `wrap_into_victim_observed` / `victim_reclaim_executed` checks at `:357-366` are evaluated after
  the sweep (which follows the persist/pre-snapshot work and precedes the cold request), and the
  refusal is handled at `:394-402` with `gate.invalidate("no circular-reclaim of a live target slot
  was executed; the head-slot recycle precondition is not established before the measured request"
  ...)`. The F1 docstring itself lists this refusal as the INVALID case at `:33-35`.
- The `--slots-margin` geometry knob (`:80`, `:116-117`) is a slot-count margin input to
  `file_size`; it is not a check and it does not reserve or assert destination capacity.

Consequence observed from the code alone: the file does **not** establish relocation-destination
capacity as a precondition; that capacity is only discovered as missing after the sweep, via a
refusal that invalidates the run. This is a fact statement; no fix is proposed here.

---

## C. Required-corrections matrix

Source: `.memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md`,
section `### Required harness corrections (owner-preauthorized)` (heading at line 80), 4 bullets at
lines 82–92. Current committed gate files: `3090-dev/gates/production/{gate_common.py,
gate_a_content_integrity.py, gate_a_f1_cold_l1.py}` (clean vs HEAD; `git diff --stat HEAD -- <these>`
empty; tracked per `git ls-files`).

### Bullet 1 (line 82-83): "bind the drop predicate to the graded target only; mark filler disposable; a filler drop must not INVALIDate the target, but any target page/ref drop must fail closed"

**ABSENT.**

Evidence:
- Predicate is still the unscoped substring test: `gate_common.py:716-717` (`"without backup due to host memory pressure" in ln`). No id filter.
- Content gate still invalidates on any non-empty list: `gate_a_content_integrity.py:532-538`.
- F1 still invalidates on any non-empty list: `gate_a_f1_cold_l1.py:528-534`, `:658-662` (via `:324-326`), `:761` + `:390-392` + `:403-414`.
- Grep `grep -rin "disposable\|filler.*drop\|drop.*filler" 3090-dev/gates/production/*.py` returns only
  `f2_restart_recovery.py:29`, `:88`, and `gate_a_content_integrity.py:93` — all of which use
  "disposable" to describe the **extent store**, not filler disposal; no code marks a filler drop as
  disposable.
- README still states the opposite scoping (any event is INVALID): `3090-dev/gates/production/README.md:145-146`.

### Bullet 2 (line 84-86): "reserve an explicit relocation destination ... do not fill the store ~100 % live and then require relocation to succeed; do not dodge the wrap by making the store enormous"

**ABSENT** (no reservation exists).

Evidence: same as B.3. Grep for `reserve | destination | headroom | relocat` in
`gate_a_f1_cold_l1.py` yields no reservation logic (only docstring/comment, host-pool headroom,
event counters, and report-only snapshot keys). No pre-measurement `gate.check` asserts
destination capacity. The geometry (`gate_a_f1_cold_l1.py:107-129`) computes `file_size` from
`chain_slots + 2*filler_slots + slots_margin`; there is no per-victim destination reserve and no
assertion that headroom >= victim live bytes. `wal_forensics.py:454` computes
`reclaim_relocatable` but nothing consumes it as a check.

### Bullet 3 (line 87-88): "geometry must trigger circular reclaim with a victim slot holding target live refs and a real recycle event"

**PARTIALLY PRESENT.**

Evidence present:
- Geometry intends wrap: docstring `:8-12`; `compute_geometry` `:107-129` (`file_size` sized to chain +
  2× filler slots + margin, `:116-117`).
- Checks exist for the victim holding live target refs (`:372-377` `victim_held_live_target_refs`,
  from `_snapshot_membership` pre-sweep), a real recycle/relocation event
  (`:357-366` `wrap_into_victim_observed`, `victim_reclaim_executed`), generation change
  (`:367-371`), and head resolution (`:378-380`).
- The sweep explicitly targets unique-prefix traffic to advance the cursor
  (`:630-637` docstring; `:648` `_filler_ids(500 + i, args.sweep_tokens)`; `:870-874`).

Evidence of partiality:
- These are **post-sweep** checks (all after `:322`), not pre-measurement geometry assertions.
- The refusal path is INVALID, not corrected geometry: `:394-402` and docstring `:33-35`.
- The trigger is probabilistic over the sweep loop with a consecutive-refusal bound (`:83-84`,
  `:678-688`), not a geometry guarantee; the previous campaign recorded a refusal
  (`.memory/.../PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md:63-69`).

### Bullet 4 (line 89-92): "pre-assert (before any measured request) the §3 preconditions: Gate A = target in Extent index, DEVICE miss, HOST miss, STORAGE-hit candidate, host pool sized; F1 = victim slot id known, victim holds target live refs, relocation destination capacity exists, actual recycle event, victim generation changed, target relocation count > 0. Missing any ⇒ INVALID without burning GPU."

**PARTIALLY PRESENT.**

Gate A (`gate_a_content_integrity.py`) sub-items:
- target in Extent index: PRESENT — offline membership compiled into `_membership_both` (`:635-657`)
  and required before success via the `ok` gate at `:549-554`, `:562`, checked at `:601-602`
  (`persist_target_in_extent_index`).
- host pool sized: PRESENT — `:271-285` `host_pool_stages_graded_prompt` + invalidate.
- DEVICE miss / HOST miss pre-assertion: ABSENT as a pre-request check. The only device/host
  assertions are on the **post-hoc measured arms**: `:488-491` (`l3_*_device_miss`) and
  `:492-493` (`gate.record(f"{prefix}_host_tokens", ...)` is a non-required record, not a check).
  The docstring claims "device/host absence guaranteed by the filler volume" (`:20-21`) but there is
  no runtime `gate.check` for host==0 or device==0 before the measured request.
- STORAGE-hit candidate pre-assertion: **ABSENT.** Grep
  `storage_hit|storage-hit|STORAGE-hit|host_miss|device_miss|candidate` over
  `gate_a_content_integrity.py` yields only `:488`, `:490` (post-hoc device-miss) and the docstring
  lines; there is no pre-request storage-hit-candidate check.
- INVALID-without-burning-GPU: PRESENT only in the sense that preconditions that do exist
  (host pool `:271-285`, preflight `:163-165`, port/lock) invalidate before measured arms.

F1 (`gate_a_f1_cold_l1.py`) sub-items:
- victim slot id known: PRESENT pre-measurement — `:288-293` (`pre_sweep_target_slots`) and
  `:304-307` (`pre_victim_candidates_known`), grouped at `:311-319`.
- victim holds target live refs: **PARTIALLY** — pre-sweep membership is recorded and
  `target_slot_details` is stored (`:288-293`), but the explicit check
  `victim_held_live_target_refs` is **post-sweep** (`:372-377`), after the sweep has run.
- relocation destination capacity exists: **ABSENT** (see B.3).
- actual recycle event: PARTIAL/post-hoc — `:357-366` after the sweep.
- victim generation changed: post-hoc — `:367-371`.
- target relocation count > 0: post-hoc — `relocated_count` at `:726-728` / `:781`.

Overall Bullet 4: **PARTIALLY PRESENT.** Some pre-assertions exist (Gate A host pool + target-in-index;
F1 victim-slot-known), but the named relocation-destination capacity is absent, and several named
items (Gate A DEVICE/HOST miss and STORAGE-hit candidate; F1 live-ref/recycle/generation/relocation
counts) are only checked after the measured request or not at all as pre-requests.

---

## D. Frozen production tree facts (read-only)

Path: `/opt/sglang/local-prod-v1.2.1-candidate`

### D.1 Existence and top-level layout

EXISTS. `ls -la /opt/sglang/local-prod-v1.2.1-candidate`:

```
lrwxrwxrwx env -> /home/ubuntu/venvs/sglang-3090
dr-xr-xr-x launcher
drwxrwxr-x manifest
dr-xr-xr-x src
dr-xr-xr-x tools
```

Relevant subdirs: `src/` (the frozen source, `src/python/sglang/...`, `src/3090-dev/...`,
`src/rust/...`), `launcher/launch.sh`, `manifest/`, `tools/{l3_namespace.py,preflight_identity.py,validate_telemetry.py}`.

### D.2 `prod-service/bin/supervise.sh` and `prod-service/conf/service.env`

There is **no top-level `prod-service/`**. `find . -type d -name prod-service` returns exactly:
`./src/3090-dev/tools/prod-service`. The tree also carries a second copy at
`./src/3090-dev/deploy/{bin,conf}`.

Both requested files exist under the in-tree path:
- `/opt/sglang/local-prod-v1.2.1-candidate/src/3090-dev/tools/prod-service/bin/supervise.sh`
  sha256 `d3a1742e24c3d08c97ae6efe351e69fdc277db87de10db0abefa74ae2785f2e6`
- `/opt/sglang/local-prod-v1.2.1-candidate/src/3090-dev/tools/prod-service/conf/service.env`
  sha256 `8f5fe73bf5a2e297b11c830ab7b8757fb8ee9d89e3a6f421f8f1ebbb2ad8ec4b`

(Second copy: `src/3090-dev/deploy/bin/supervise.sh` sha256
`d3a1742e24c3d08c97ae6efe351e69fdc277db87de10db0abefa74ae2785f2e6` — identical to the tools copy;
`src/3090-dev/deploy/bin/start.sh` sha256
`f228e05558f971ac71da042e4b9c5c27e422892e6c9dd8d599170fd0aeeaddae`; `src/3090-dev/deploy/conf/service.env`
sha256 `e34f08bbd387716bebd5fe44df34cd8a437d43bb0ca6c14bb58d30ac87e46d71`.)

Identity strings in `.../tools/prod-service/conf/service.env` (verbatim):
- `:23` `PROD_TREE_DEFAULT=/opt/sglang/local-prod-v1.2-candidate`
- `:24` `PROD_IDENTITY_DEFAULT=LOCAL-PROD-v1.2`
- `:25` `PROD_TREE_V12=/opt/sglang/local-prod-v1.2-candidate`
- `:26` `PROD_IDENTITY_V12=LOCAL-PROD-v1.2`
- `:27` `PROD_TREE_V1=/opt/sglang/local-prod-v1`
- `:28` `PROD_IDENTITY_V1=LOCAL-PROD-BASELINE-v1`
- `:29` `PROD_TREE_V11=/opt/sglang/local-prod-v1.1-candidate`
- `:30` `PROD_IDENTITY_V11=LOCAL-PROD-v1.1`
- `:31` `PROD_TREE_V112=/opt/sglang/local-prod-v1.1.2-candidate`
- `:32` `PROD_IDENTITY_V112=LOCAL-PROD-v1.1.2`
- `:37` `TEST_TREE_DEFAULT=/opt/sglang/local-prod-v1.1.2-candidate`
- `:54` `SCAFFOLD_ROOT=/tmp/opencode/prod-service-20260917`
- `:75` export list omits `PROD_TREE_V121`/`PROD_IDENTITY_V121` (only DEFAULT, TEST_TREE_DEFAULT and named v1/v1.1/v112 variants are exported; see also the scaffold copy below).

NOTE: the in-tree `service.env` does **not** include `PROD_TREE_V121` / `PROD_IDENTITY_V121`; the
scaffold copy at `/tmp/opencode/prod-service-20260917/conf/service.env` does
(`:23` `PROD_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate`, `:24` `PROD_IDENTITY_DEFAULT=LOCAL-PROD-v1.2.1`,
`:25-26` `PROD_TREE_V121`/`PROD_IDENTITY_V121`, sha256 `ded18d223e5c0550c0ce68836c9561632ccf81ccd5f8bb84b33966ac61b9f728`).

Identity literal in the in-tree supervisor binary: `src/3090-dev/tools/prod-service/bin/supervise.sh`
hard-codes the literal `"LOCAL-PROD-v1.1.2"` at `:60` (`state_write ... "LOCAL-PROD-v1.1.2" "starting"`)
and at `:143` (`... "LOCAL-PROD-v1.1.2" "serving"`). The **scaffold** supervisor does not: it reads the
tree's own manifest (`/tmp/opencode/prod-service-20260917/bin/supervise.sh:59-63`,
`IDENTITY="$(jq -r '.name // empty' "$TREE/manifest/identity.json" ...)"`, `:65` die if absent).

Tree pointer / `PRED_TREE` in service.env: **ABSENT.** `grep -rn "PRED_TREE\|TREE_POINTER\|tree_pointer\|TREE="` over
both in-tree `service.env` copies and the scaffold copy returns no match. The analogous tree-pointer
variables are the `PROD_TREE_*` lines quoted above.

### D.3 `bin/start.sh` — supervisor invocation and SCAFFOLD vs in-tree

Requested `bin/start.sh` exists only in-tree (there is no top-level `bin/`). Files:
`src/3090-dev/tools/prod-service/bin/start.sh` and `src/3090-dev/deploy/bin/start.sh`, both sha256
`f228e05558f971ac71da042e4b9c5c27e422892e6c9dd8d599170fd0aeeaddae`.

Exact invoking lines (`src/3090-dev/tools/prod-service/bin/start.sh:80-82`):

```
setsid bash "$SCAFFOLD_ROOT/bin/supervise.sh" \
  "$ROLE" "$TREE" "$PORT" "$RUN_ID" "$NAMESPACE" "$LOG_DIR" "$START_TS" \
  >>"$LOG_DIR/supervisor.log" 2>&1 < /dev/null &
```

It executes the **SCAFFOLD copy**, not the in-tree copy: the path is `$SCAFFOLD_ROOT/bin/supervise.sh`,
and `SCAFFOLD_ROOT` resolves via `bin/common.sh:13` (`SCAFFOLD_ROOT="${SCAFFOLD_ROOT:-/tmp/opencode/prod-service-20260917}"`)
and `bin/common.sh:15` (`source "$SCAFFOLD_ROOT/conf/service.env"`) to
`/tmp/opencode/prod-service-20260917/bin/supervise.sh`. Same line numbers/logic in the `deploy` copy
(`:80-82`), confirmed identical by `diff` (IDENTICAL).

Corroborating sha comparison: scaffold `bin/start.sh` sha256
`f228e05558f971ac71da042e4b9c5c27e422892e6c9dd8d599170fd0aeeaddae` == in-tree `start.sh` sha256;
and `diff` of the two start.sh files printed `IDENTICAL`. However the scaffold's `supervise.sh` differs
from the tree's (`946aecd6...` vs `d3a1742e...`), and `diff` of the two `service.env` files reports
the identity/default differences (deploy copy: `PROD_TREE_DEFAULT=/opt/sglang/local-prod-v1.1.2-candidate`,
`PROD_IDENTITY_DEFAULT=LOCAL-PROD-v1.1.2`; tools copy: v1.2/v1.2 + `_V12` entries). So `start.sh`
from the tree invokes the **scaffold** supervisor/conf, which is not byte-identical to the tree's
own copies.

### D.4 Native-write references in `extent_file_backend.py`

File: `/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
sha256 `a5c99fd1cc32b64518ceaed01cac46c53b5622395d259a897c674e317cdd0cbd`.

Counts (verbatim command output):
- `grep -c "native_write\|SGLANG_L3_NATIVE_WRITE_PATH"` → `31` (matching lines)
- `grep -o ... | wc -l` → `32` (total occurrences; line 145 contains two: `_NATIVE_WRITE_WORKSPACE_ENV` and the `SGLANG_L3_NATIVE_WRITE_PATH` prefix)

Representative lines: `:135` (comment), `:144` `_NATIVE_WRITE_ENV = "SGLANG_L3_NATIVE_WRITE_PATH"`,
`:145` `_NATIVE_WRITE_WORKSPACE_ENV = "SGLANG_L3_NATIVE_WRITE_PATH_WORKSPACE"`, `:151`
`_native_write_path_enabled`, `:604`, `:1978`, `:2326-2328`, `:2369-2409`, `:2472`, `:2516`,
`:2578-2579`, `:2775-2781`.

(Repo-worktree twin `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` has the same
sha256 `a5c99fd1cc32b64518ceaed01cac46c53b5622395d259a897c674e317cdd0cbd` and the same counts 31/32.)

### D.5 `rust/l3wal` crate

PRESENT. Path: `/opt/sglang/local-prod-v1.2.1-candidate/src/rust/l3wal` (contains `Cargo.toml`,
`src/`, with `src/lib.rs`). Sibling crates under `src/rust/`: `sglang-grpc`, `sglang-mm`,
`sglang-server`, plus `Cargo.lock`, `Cargo.toml`, `rust-toolchain.toml`, `target/`.

### D.6 `manifest/identity.json` identity fields

File `/opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json` (verbatim values):
- `:17` `"SOURCE_COMMIT": "b2bbd6ea28"`
- `:18` `"TREE_HASH": "3bd285d51e3fdb0c338400dd0203bf8d131f26504baf1076084eea372849f7c8"`
- `:86` `"source_tree": "/tmp/opencode/v1.2.1-stage"`
- `:57` `"name": "LOCAL-PROD-v1.2.1"`, `:87` `"status": "FROZEN"`, `:88` `"template_identity": "LOCAL-PROD-v1.1"`
- `:19` `"freeze_tool": "v1.1.2-freeze-20260917"`, `:20` `"frozen_at_utc": "2026-09-17T18:36:32Z"`
- `:16` `"RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376"`
- `:108`, `:113` `tree_manifest_digest_sha256` / `tree_manifest_sha256_self` also `3bd285d5...`
- `:99` `"file_count": 14788`, `:101` `"src_file_count": 14784`

The companion `manifest/identity-pins.json` repeats `SOURCE_COMMIT: "b2bbd6ea28"`,
`TREE_HASH: "3bd285d5..."`, `source_tree: "/tmp/opencode/v1.2.1-stage"`, `identity: "LOCAL-PROD-v1.2.1"`.

---

## E. Git facts (read-only; no fetch, no mutation)

All commands run with `git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`.

### E.1 Branch and HEAD

- `git rev-parse --abbrev-ref HEAD` → `3090-24g-opt`
- `git rev-parse HEAD` → `910e5a01c05da1311925bc5fd174f9a0ec04b3a3`
- `git log --oneline -5`:
  ```
  910e5a01c0 docs(memory): session-close handoff for the M1 production session
  a6beb3004c docs(memory): reconcile production commit identity (b2bbd6ea28 / 8c8cdcea03)
  9c4685e1bb chore(freeze): record the v1.2.1 candidate pins and approved delta
  a25c80902a docs(freeze): cite the recorded AUTH-OFF ruling in the launcher audit
  8c8cdcea03 fix(prod-service): publish the served tree's real identity, not a literal
  ```

### E.2 Commit `910e5a01c0`

EXISTS. `git cat-file -t 910e5a01c0` → `commit` (exit 0).

It **contains** `.memory/phase2-hicache-design/HANDOFF-20260917-SESSION-CLOSE.md`:
- `git show --stat 910e5a01c0` header: `910e5a01c05da1311925bc5fd174f9a0ec04b3a3`, author `opencode <opencode@local>`, date `Thu Sep 17 19:23:18 2026 +0000`, subject `docs(memory): session-close handoff for the M1 production session`; stat `.../HANDOFF-20260917-SESSION-CLOSE.md | 221 +++...` ("1 file changed, 221 insertions(+)").
- `git ls-tree -r --name-only 910e5a01c0 | grep HANDOFF-20260917-SESSION-CLOSE` →
  `.memory/phase2-hicache-design/HANDOFF-20260917-SESSION-CLOSE.md`
- `git diff-tree --no-commit-id --name-only -r 910e5a01c0` → exactly
  `.memory/phase2-hicache-design/HANDOFF-20260917-SESSION-CLOSE.md`

Note: HEAD itself equals `910e5a01c0`, so the SESSION-CLOSE doc is **committed at HEAD**, which is why
it does not appear in `git status --porcelain` (see E.3).

### E.3 `git status --porcelain` (verbatim output)

```
 M .memory/phase2-hicache-design/ledger.md
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```

Untracked (`??`) entries, explicitly:
1. `.memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md`
2. `.memory/phase2-hicache-design/agents/`
3. `.memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md`
4. `.memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md`
5. `.memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md`
6. `3090-dev/gates/gguf-sampled-smoke/`
7. `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py`

Presence confirmation requested:
- `HANDOFF-20260917-SESSION-CLOSE.md`: **NOT present in status** — `git status --porcelain | grep -c "HANDOFF-20260917-SESSION-CLOSE"` → `0`; it is committed at HEAD (E.2).
- Other HANDOFF doc: present untracked — `HANDOFF-20260917-PRODUCTION-PRIORITY.md` (item 1).
- EPOCH doc: present untracked — `work/EPOCH-RESUME-20260917-R2.md` (item 3).
- GGUF docs: present untracked — `work/GGUF-ARTIFACT-PROVENANCE-20260917.md` (item 4), plus tracked-dirty `python/sglang/srt/utils/hf_transformers/gguf_native.py` (` M`).
- `3090-dev/gates/gguf-sampled-smoke/`: present untracked (item 6).
- `test/registered/unit/utils/test_gguf_native_tokenizer_ids.py`: present untracked (item 7).

Also tracked-and-modified (` M`): `.memory/phase2-hicache-design/ledger.md`,
`python/sglang/srt/utils/hf_transformers/gguf_native.py`.

### E.4 `origin/3090-24g-opt` and ahead/behind

The origin ref IS present locally: `git show-ref` shows
`ad749d6f283b7d6c59a8df928304325eda90e98b refs/remotes/origin/3090-24g-opt` and
`910e5a01c05da1311925bc5fd174f9a0ec04b3a3 refs/heads/3090-24g-opt`.

`git rev-list --left-right --count origin/3090-24g-opt...HEAD` (verbatim) → `0	38`.

Interpretation: left count 0 = commits on `origin/3090-24g-opt` not in HEAD; right count 38 = commits
on HEAD not in `origin/3090-24g-opt`. So HEAD is **ahead of `origin/3090-24g-opt` by 38 commits and
behind by 0**. (No fetch was run per instructions; this reflects the locally cached remote-tracking ref.)

Also relevant, `CONTEXT` in `.memory/.../PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md:12` records HEAD as
`7d08fb26...`, which does not match the current HEAD `910e5a01c0...`; that doc is untracked (E.3 item 5).
Reported as an observed discrepancy, not adjudicated here.

---

## Defects / blockers

No blocker prevented completing A–E. Observations that are defects against the handed-off
assertions (facts, no fixes proposed):

1. `parse_storage_events` drop predicate is globally scoped (`gate_common.py:716-717`); both
   Gate A and F1 invalidate on any prefix's drop, so a filler-only drop can invalidate an intact
   target (`gate_a_content_integrity.py:532-538`; `gate_a_f1_cold_l1.py:528-534`, `:658-662`).
2. F1 has no pre-measurement relocation-destination-capacity assertion (B.3: ABSENT);
   `reclaim_relocatable`/`relocation_headroom_bytes` are report-only (`:622-623`).
3. Required-corrections bullets: #1 ABSENT, #2 ABSENT, #3 PARTIALLY PRESENT, #4 PARTIALLY PRESENT
   (C).
4. The in-tree `prod-service` copy is not at the tree root (`src/3090-dev/tools/prod-service`), its
   `start.sh` invokes the **scaffold** `/tmp/opencode/prod-service-20260917` supervisor
   (`start.sh:80-82` via `common.sh:13,15`), and its supervisor hard-codes `"LOCAL-PROD-v1.1.2"`
   (`supervise.sh:60,143`) while the tree's own manifest identity is `LOCAL-PROD-v1.2.1`
   (`manifest/identity.json:57`). The scaffold `service.env` differs from the in-tree copies.
5. `PRED_TREE` is ABSENT in all examined `service.env` and supervisor copies (D.2).

## Remaining claims / exclusions

- No runtime was executed; all statements about gate behavior are read from source control flow and
  log-string producers, not from a run.
- The scaffold/tree path checks were limited to `/tmp/opencode/prod-service-20260917` and the
  `local-prod-v1.2.1-candidate` tree; other `/opt/sglang/local-prod-*` trees were not inspected.
- "Filler-only drop" refers to the harness's unrelated unique-prefix filler traffic
  (`gate_a_f1_cold_l1.py:870-874`; `gate_a_content_integrity.py:676-682`); no live run was observed.
- The `git rev-list --left-right` counts rely on the locally cached `origin/3090-24g-opt`; no fetch
  was performed, so they are not guaranteed to reflect the server-side remote.
- I did not inspect `/var/log`, did not touch `/opt` write bits, and did not modify any reviewed file.
  The only write is this result artifact (plus the `agents/` directory, which was untracked before
  and after).

Terminal state: DONE
