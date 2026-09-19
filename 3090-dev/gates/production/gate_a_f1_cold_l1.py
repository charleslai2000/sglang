#!/usr/bin/env python3
"""Gate A-F1 -- post-reclaim cold-L1 head proof (F1).

Scenario (deterministic, bounded, no 47 GB fill):
  1. prime a >=62K-token chain and force its write-back to the storage tier;
  2. determine, offline from THIS run's own WAL, which extent slot holds the
     chain head (the victim the circular cursor will wrap into);
  3. SWEEP with UNRELATED UNIQUE prefixes -- every request allocates brand-new
     storage keys/slots -- until the cursor wraps into the victim slot.  The
     predecessor used prefix-matching traffic (``chain + unique suffix``), which
     reuses the chain's existing refs and allocates almost no new slots, so the
     cursor never wrapped even after 1.49 GB of writes;
  4. prove (do not infer) the reclaim: the victim held LIVE target refs; the
     allocator had no free destination outside the normal reclaim path; a
     reclaim/relocation/generation-bump event names the victim slot; the victim
     generation changed; the head's refs now resolve to relocated space;
  5. force L1/L2 cold with a STRICT ``/flush_cache`` (a non-2xx / timed-out
     flush is INVALID -- it is never recorded as OK), plus one unrelated
     cold-filler round, then re-prove the target is still in the index;
  6. issue the cold request for the chain and require a storage-sourced restore
     with the exact DEVICE-reference token ids.

Expectation modes (``--expect``):
  fixed   : the reclaim relocated the victim's live refs; the cold request
            restores from storage (storage > 0, device == 0, no zero-hit miss)
            with exact ids and offline ``batch_exists`` == expected.
  unfixed : the reclaim dropped the head (no relocation); the cold request shows
            storage == 0 / zero-hit miss while the offline replay shows the head
            absent and the rest of the chain present.

INVALID (never PASS/FAIL) when a precondition is not established, including:
  * no wrap attempted at all;
  * the wrap was REFUSED by the product's fail-closed relocation (no
    destination capacity outside the victim) -- the head-slot recycle was not
    exercised;
  * the victim slot held no live target refs;
  * a non-2xx / timed-out flush_cache;
  * a ``dropped without backup due to host memory pressure`` event (host pool
    still mis-sized for the graded chain).

Store policy: one unique namespace per run; never clear/flush any store; the
shared /data/l3/local-prod-v1.1 store is never touched.

Exit codes: 0 PASS | 1 FAIL | 2 INVALID | 3 PENDING | 4 ERROR | 5 BLOCKED.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_common as gc  # noqa: E402

MARK = "ALPHA-7Q3Z-42"
PAGE_BYTES = 16384  # 16 KiB per token-page (fp8_e4m3 KV)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=gc.DEFAULT_TREE)
    ap.add_argument("--model", default=gc.DEFAULT_MODEL)
    ap.add_argument("--port", type=int, default=gc.DEFAULT_PORT)
    ap.add_argument("--hc-size", type=int, default=8,
                    help="--hicache-size in SI GB; must stage the graded chain")
    ap.add_argument("--chain-tokens", type=int, default=62000)
    ap.add_argument("--host-pool-margin", type=int, default=4096)
    ap.add_argument("--max-new", type=int, default=32)
    ap.add_argument("--filler-tokens", type=int, default=16000,
                    help="unrelated filler tokens per write-back eviction round")
    ap.add_argument("--max-fillers", type=int, default=8)
    ap.add_argument("--extent-size", type=int, default=64 << 20)
    ap.add_argument("--file-size", type=int, default=0)
    ap.add_argument("--slots-margin", type=int, default=8)
    ap.add_argument("--reloc-reserve-slots", type=int, default=2,
                    help="bounded spare slots appended to FILE_SIZE so the "
                         "circular reclaim has a non-victim relocation "
                         "destination (owner closure 2); small on purpose so "
                         "the wrapped sweep is not dodged")
    ap.add_argument("--page-bytes", type=int, default=PAGE_BYTES)
    ap.add_argument("--sweep-tokens", type=int, default=2048)
    ap.add_argument("--sweep-requests", type=int, default=160)
    ap.add_argument("--max-consecutive-refusals", type=int, default=16,
                    help="a fail-closed refusal is not always permanent (the "
                         "campaign saw 9 refusals then progress); keep sweeping "
                         "until this many CONSECUTIVE refusal rounds occur with "
                         "no successful reclaim")
    ap.add_argument("--cold-fillers", type=int, default=1)
    ap.add_argument("--min-index-fraction", type=float, default=0.99)
    ap.add_argument("--min-restore-fraction", type=float, default=0.8)
    ap.add_argument("--wal-checkpoint-bytes", type=int, default=32 << 20)
    ap.add_argument("--expect", choices=["fixed", "unfixed"], default="fixed")
    ap.add_argument("--namespace", default=None)
    ap.add_argument("--reuse-namespace", action="store_true")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--lock-attempts", type=int, default=240)
    ap.add_argument("--lock-poll", type=int, default=15)
    ap.add_argument("--health-timeout", type=float, default=2400.0)
    return ap.parse_args()


def config_suffix(model: str) -> str:
    return f"_{'-'.join(model.split('/'))}_0_1"


def compute_geometry(args) -> dict:
    page_bytes = int(getattr(args, "page_bytes", PAGE_BYTES) or PAGE_BYTES)
    pages_per_slot = args.extent_size // page_bytes
    if pages_per_slot <= 0:
        raise gc.GateInvalid("extent_size smaller than one page")
    chain_slots = math.ceil(args.chain_tokens / pages_per_slot)
    filler_slots = math.ceil(args.filler_tokens / pages_per_slot)
    reloc_reserve_slots = max(0, int(getattr(args, "reloc_reserve_slots", 0) or 0))
    # room for the write-back fillers (L2 eviction) plus the measured sweep's
    # wrap region, so the wrap is reached by the sweep and not by accident, plus
    # a bounded relocation-destination reserve (owner closure 2).  The reserve
    # is deliberately a whole number of EMPTY slots: the circular cursor still
    # wraps into the oldest full slot (the wrap is not dodged), while the
    # allocator has a non-victim free tail to relocate the victim's live refs
    # into.  It is bounded so the store is never padded to avoid the wrap.
    file_size = args.file_size or (
        (chain_slots + 2 * filler_slots + args.slots_margin
         + reloc_reserve_slots) * args.extent_size)
    if file_size < args.extent_size or file_size % args.extent_size != 0:
        raise gc.GateInvalid(
            f"file_size {file_size} must be a positive multiple >= "
            f"extent_size {args.extent_size}")
    return {
        "extent_size": args.extent_size, "file_size": file_size,
        "num_slots": file_size // args.extent_size,
        "pages_per_slot": pages_per_slot,
        "chain_slots": chain_slots,
        "filler_slots": filler_slots,
        "reloc_reserve_slots": reloc_reserve_slots,
        "reloc_reserve_bytes": reloc_reserve_slots * args.extent_size,
        "sweep_bytes_per_request": args.sweep_tokens * page_bytes,
    }


def main() -> int:
    args = parse_args()
    tag = "gateA-F1"
    rid = args.run_id or gc.run_id(tag)
    run_dir = gc.RUN_DIR / tag
    gate = gc.Gate(tag, run_dir, extra={
        "tree": args.tree, "model": args.model, "port": args.port,
        "hc_size_gb": args.hc_size, "chain_tokens": args.chain_tokens,
        "host_pool_margin": args.host_pool_margin, "expect": args.expect,
        "run_id": rid,
        "wrap_trigger": {
            "note": "every sweep request uses a distinct per-request deterministic "
                    "prompt seed (random.Random(180000 + i) in _filler_ids) with no "
                    "shared prefix, so it allocates NEW storage keys/slots "
                    "(the predecessor's 'chain + unique suffix' reused the "
                    "chain's refs and never advanced the cursor)",
            "backend_env": ["SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE",
                            "SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE"],
            "gc": "off (MAX_SIZE=0, MIN_FREE_SPACE=0)",
        },
        "store_policy": {"shared_production_store": gc.PRODUCTION_STORE,
                         "clear_or_flush_called": False},
    })
    gate.report["host_pool_sizing"] = gc.sizing_arithmetic(
        args.hc_size, args.chain_tokens, args.host_pool_margin)
    lock_fd = None
    proc = console = None
    try:
        gate.report["gpu_compute_apps_before"] = gc.gpu_compute_apps()
        gate.check("tree_present",
                   os.path.exists(os.path.join(args.tree, "src", "python",
                                               "sglang", "__init__.py")),
                   detail=args.tree)
        pf = gc.preflight_import(args.tree)
        gate.report["preflight_import"] = pf
        gate.check("preflight_sglang_file_in_tree", pf.get("ok"), detail=pf)
        if not pf.get("ok"):
            gate.invalidate("tree binding not proven (stale editable install?)")
            return _finish(gate)
        geom = compute_geometry(args)
        gate.report["geometry"] = geom
        gate.log(f"pinned geometry: {geom}")
        suffix = config_suffix(args.model)

        prompt_json = run_dir / "prompt_A.json"
        info = gc.build_prompt(args.tree, args.model, MARK, args.chain_tokens,
                               prompt_json)
        ids_a = info["ids"]
        gate.report["prompt"] = {"marker": MARK, "n": len(ids_a),
                                 "query_window_len": len(ids_a) - 1}
        gate.check("chain_ok", len(ids_a) >= 32000, detail=len(ids_a))
        gate.check("chain_fits_context",
                   len(ids_a) + args.sweep_tokens + args.max_new <= 65536,
                   detail=f"{len(ids_a)}+{args.sweep_tokens}+{args.max_new}")
        if not gate.checks["chain_ok"]["ok"]:
            gate.invalidate("built F1 chain below the required length")
            return _finish(gate)
        if not gate.checks["chain_fits_context"]["ok"]:
            gate.invalidate("chain + sweep prompt exceeds the 65536 context")
            return _finish(gate)
        gate.report["sizing_check"] = gc.sizing_arithmetic(
            args.hc_size, len(ids_a), args.host_pool_margin)

        lock_fd = gc.acquire_lock(f"gate-a-f1-{rid}",
                                  max_attempts=args.lock_attempts,
                                  poll_s=args.lock_poll)
        if lock_fd is None:
            gate.pending("canonical GPU lock not acquired within bounded window")
            return _finish(gate)
        gate.check("port_free_before_launch", gc.port_free(args.port),
                   detail=args.port)
        if not gc.port_free(args.port):
            gate.invalidate(f"port {args.port} busy after lock acquisition")
            return _finish(gate)

        namespace = args.namespace or gc.resolve_namespace(
            gc.L3_ROOT, tag, rid, reuse=args.reuse_namespace)
        gate.report["namespace"] = namespace
        gate.report["namespace_before"] = gc.namespace_manifest(namespace, suffix)

        extra_env = {
            "SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE": str(geom["extent_size"]),
            "SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE": str(geom["file_size"]),
            # GC off: only the circular cursor reclaim may touch a slot.
            "SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE": "0",
            "SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE": "0",
            "SGLANG_HICACHE_EXTENT_BACKEND_WAL_CHECKPOINT_BYTES":
                str(args.wal_checkpoint_bytes),
        }
        metrics_dir = run_dir / "metrics_s1"
        console_path = run_dir / "server.console.s1.log"
        proc, console, _ = gc.launch_server(
            args.tree, args.model, args.port, namespace, console_path,
            metrics_dir, hc_size_gb=args.hc_size, extra_env=extra_env)
        gate.log(f"launched server pid={proc.pid} "
                 f"file_size={geom['file_size']} slots={geom['num_slots']}")
        health = gc.wait_health(args.port, proc, args.health_timeout)
        gate.check("server_healthy", health.get("ok"), detail=health)
        gate.check("server_not_inheriting_lock",
                   not gc.proc_holds_lock(proc.pid),
                   detail="lock fd absent from server /proc/<pid>/fd")
        if not health.get("ok"):
            gate.invalidate(f"server unhealthy: {health}")
            return _finish(gate)
        env = gc.proc_env(proc.pid)
        gate.check("server_pythonpath",
                   env.get("PYTHONPATH") == os.path.join(args.tree, "src", "python"),
                   detail=env.get("PYTHONPATH"))
        kg = gc.kv_dtype_gate(console_path)
        gate.check("kv_dtype_gate", kg.get("ok"), detail=kg)
        off_store = gc.console_size(console_path)  # before any store writes

        hp = gc.parse_host_pool(console_path, prompt_tokens=len(ids_a),
                                host_pool_margin=args.host_pool_margin)
        gate.report["host_pool_actual"] = hp
        gate.check("host_pool_stages_graded_chain", hp.get("ok"),
                   detail={k: hp.get(k) for k in
                           ("kv_tokens", "required_kv_host_tokens",
                            "kv_headroom_tokens")})
        if not hp.get("ok"):
            gate.invalidate(
                "kv host pool does not stage the graded chain "
                f"(kv_tokens={hp.get('kv_tokens')} < required="
                f"{hp.get('required_kv_host_tokens')}): write-back can only be "
                "dropped without backup -> storage tier unreachable")
            return _finish(gate)

        # ---- 1. prime + force write-back of the chain -------------------
        gc.generate(args.port, ids_a, 1)
        warm = gc.generate(args.port, ids_a, args.max_new)
        gate.report["warm_A"] = _resp_slim(warm)
        gate.check("warm_device_resident", warm["tier"]["device"] > 0,
                   detail=warm["tier"])
        persist = _persist_chain(gate, args, console_path, namespace, suffix,
                                 ids_a, str(prompt_json), run_dir, rid)
        if persist is None:
            return _finish(gate)
        gate.report["persist"] = persist
        if not persist["ok"]:
            gate.invalidate(persist["reason"])
            return _finish(gate)

        # Console node-id evidence for the graded chain (owner closure 1): the
        # match anchors of requests whose fill_len equals the chain length plus
        # the restore_backup durable nodes bound the chain's radix node ids.
        # Read from the whole post-launch window so it is available to the
        # target-scoped drop predicate at every later stage.
        target_evidence = gc.target_node_evidence(
            gc.parse_storage_events(gc.read_new_lines(console_path, off_store)),
            len(ids_a))
        gate.report["target_node_evidence"] = target_evidence

        # ---- 2. offline victim identification (pre-sweep) ----------------
        pre = _snapshot_membership(
            gate, args, namespace, suffix, run_dir, rid, "pre-sweep", ids_a,
            str(prompt_json))
        if pre is None:
            return _finish(gate)
        gate.report["pre_sweep_membership"] = _slim_membership(pre)
        pre_mem = pre.get("membership") or {}
        target_details = pre.get("target_slot_details") or {}
        head = pre.get("head") or {}
        target_slot_set = {int(s) for s in target_details}
        full_target_slots = sorted(
            int(s) for s, d in target_details.items()
            if int(d.get("free_tail_bytes") or 0) < args.page_bytes)
        gate.report["pre_sweep_target_slots"] = {
            "target_slots": sorted(target_slot_set),
            "full_target_slots": full_target_slots,
            "details": target_details,
            "allocator_state": pre.get("allocator_state"),
        }
        min_present = math.ceil(args.min_index_fraction * (len(ids_a) - 1))
        gate.check("pre_target_in_index",
                   (pre_mem.get("n_present") or 0) >= min_present,
                   detail={"n_present": pre_mem.get("n_present"),
                           "required": min_present})
        gate.check("pre_head_present",
                   bool(head.get("head_present_in_rebuilt_index")),
                   detail=head.get("head_present_in_rebuilt_index"))
        gate.check("pre_target_slots_known", bool(target_slot_set),
                   detail=sorted(target_slot_set))
        gate.check("pre_victim_candidates_known", bool(full_target_slots),
                   detail={"full_target_slots": full_target_slots,
                           "note": "target slots a circular wrap can reclaim; "
                                   "every one of them holds live target refs"})
        pre_scope = persist.get("dropped_scope")
        if not pre_scope:
            pre_scope = {"ok": persist.get("dropped_no_backup_n", 0) == 0,
                         "n_total": persist.get("dropped_no_backup_n", 0)}
        gate.check("pre_no_target_drop_without_backup",
                   pre_scope.get("ok") is True,
                   detail={"scope": pre_scope,
                           "events": persist.get("dropped_no_backup_n", 0)})
        if not (gate.checks["pre_target_in_index"]["ok"]
                and gate.checks["pre_head_present"]["ok"]
                and gate.checks["pre_target_slots_known"]["ok"]
                and gate.checks["pre_victim_candidates_known"]["ok"]):
            gate.invalidate(
                "pre-sweep preconditions failed: chain not fully in the extent "
                "index / no target-holding slot is wrap-reclaimable -> nothing "
                "to reclaim")
            return _finish(gate)

        # ---- 2b. relocation-destination reserve preflight (closure 2) -----
        # Before the (expensive, GPU) sweep: prove a bounded non-victim
        # destination capacity exists AND the expected relocation of the
        # largest target-holding candidate fits into it.  A 100%-live store
        # with no destination is the product's EXPECTED fail-closed
        # backpressure -> INVALID geometry, not a relocation-success oracle.
        reserve_candidates = [target_details[str(s)] for s in full_target_slots
                              if str(s) in target_details]
        reserve_candidate = (max(reserve_candidates,
                                 key=lambda d: int(d.get("live_bytes") or 0))
                             if reserve_candidates else {})
        pre_reserve = gc.relocation_reserve_check(reserve_candidate)
        pre_reserve["allocator_max_free_tail_bytes"] = int(
            (pre.get("allocator_state") or {}).get("max_free_tail_bytes") or 0)
        pre_reserve["geometry_reloc_reserve_slots"] = int(
            geom.get("reloc_reserve_slots") or 0)
        pre_reserve["geometry_reloc_reserve_bytes"] = int(
            geom.get("reloc_reserve_bytes") or 0)
        gate.report["pre_sweep_relocation_reserve"] = pre_reserve
        if args.expect == "fixed":
            if not gc.assert_preconditions(gate, "gate-a-f1-reserve-preflight", [
                ("pre_reloc_victim_holds_target_live_refs",
                 bool(pre_reserve["holds_target_live_refs"]), pre_reserve),
                ("pre_reloc_destination_capacity_exists",
                 bool(pre_reserve["destination_capacity_exists"]), pre_reserve),
                ("pre_reloc_expected_relocation_fits",
                 bool(pre_reserve["reclaim_relocatable"]), pre_reserve),
            ]):
                return _finish(gate)
        else:
            gate.record("pre_reloc_reserve_optional", pre_reserve)

        # ---- 3. deterministic unique-prefix sweep ------------------------
        sweep = _sweep_to_wrap(gate, args, console_path, target_slot_set,
                               target_evidence=target_evidence)
        gate.report["sweep"] = sweep
        if sweep.get("abort_reason"):
            gate.invalidate(sweep["abort_reason"])
            return _finish(gate)
        victim_slot = sweep.get("victim_slot")

        # ---- 4. post-sweep offline reclaim proof -------------------------
        _settle(console_path, off_store, timeout_s=60.0)
        post = _snapshot_membership(
            gate, args, namespace, suffix, run_dir, rid, "post-sweep", ids_a,
            str(prompt_json), victim_slot=victim_slot)
        if post is None:
            return _finish(gate)
        gate.report["post_sweep_membership"] = _slim_membership(post)
        post_mem = post.get("membership") or {}
        post_victim = post.get("victim") or {}
        post_head = post.get("head") or {}
        pre_victim = (target_details.get(str(victim_slot))
                      if victim_slot is not None else None) or {}
        post_reclaim = _reclaim_evidence(sweep, post, victim_slot,
                                         pre_victim.get("generation"),
                                         target_slot_set)
        gate.report["reclaim_evidence"] = post_reclaim
        gate.report["pre_sweep_victim"] = pre_victim
        gate.report["post_sweep_victim"] = {
            "slot": victim_slot, "generation": post_victim.get("generation"),
            "live_refs": post_victim.get("live_refs"),
            "target_live_refs": post_victim.get("target_live_refs"),
            "drop_frames": post_victim.get("drop_frames"),
            "head_current_slot": (post.get("target_slots") or {}).get(
                "head_current_slot"),
            "head_current_generation": (post.get("target_slots") or {}).get(
                "head_current_generation"),
        }
        gate.check("wrap_into_victim_observed",
                   post_reclaim["wrap_observed"],
                   detail={k: post_reclaim[k] for k in
                           ("recycle_count", "relocated_count", "refused_count",
                            "refusal_reason")})
        gate.check("victim_reclaim_executed",
                   post_reclaim["reclaim_executed"],
                   detail={"relocated_count": post_reclaim["relocated_count"],
                           "recycle_count": post_reclaim["recycle_count"],
                           "refused_count": post_reclaim["refused_count"]})
        if args.expect == "fixed":
            # Owner closure 3: the measured FIXED oracle requires a real
            # relocation of the victim's target live refs (>0), not merely a
            # destructive recycle with a generation bump.
            gate.check("victim_target_relocation_count_positive",
                       post_reclaim["relocated_count"] > 0,
                       detail={"relocated_count":
                                   post_reclaim["relocated_count"],
                               "wrap_kind": post_reclaim.get("wrap_kind")})
        gate.check("victim_generation_changed",
                   post_reclaim["generation_changed"],
                   detail={"pre_generation": pre_victim.get("generation"),
                           "post_generation": post_victim.get("generation"),
                           "drop_frames": post_victim.get("drop_frames")})
        gate.check("victim_held_live_target_refs",
                   (pre_victim.get("target_live_refs") or 0) > 0,
                   detail={"slot": victim_slot,
                           "target_live_refs": pre_victim.get("target_live_refs"),
                           "live_refs": pre_victim.get("live_refs"),
                           "live_bytes": pre_victim.get("live_bytes")})
        gate.check("head_resolved_after_reclaim",
                   post_reclaim["head_resolved"],
                   detail=post_reclaim["head_detail"])
        gate.check("post_target_in_index",
                   (post_mem.get("n_present") or 0) >= min_present,
                   detail={"n_present": post_mem.get("n_present"),
                           "required": min_present})
        gate.check("batch_exists_eq_expected",
                   post_reclaim["batch_exists_eq_expected"],
                   detail={"batch_exists": (post.get("predicate") or {}).get(
                       "window_from_page0_hits"),
                       "expected": post_reclaim["batch_exists_expected"]})
        gate.check("post_no_target_drop_without_backup",
                   post_reclaim["no_target_drop_without_backup"],
                   detail={"scope": post_reclaim.get("drop_scope"),
                           "events": post_reclaim["dropped_no_backup_n"]})
        # Pre-cold relocation reserve, measured on the victim AS IT WAS before
        # the reclaim (pre_victim): it must have held target live refs and the
        # relocation must have fit the non-victim destination capacity.
        post_reserve = gc.relocation_reserve_check(pre_victim)
        gate.report["post_sweep_relocation_reserve"] = post_reserve
        if args.expect == "fixed":
            gate.check("post_reloc_destination_capacity",
                       bool(post_reserve["ok"]), detail=post_reserve)

        if not (gate.checks["wrap_into_victim_observed"]["ok"]
                and gate.checks["victim_reclaim_executed"]["ok"]):
            gate.invalidate(
                "no circular-reclaim of a live target slot was executed; "
                "the head-slot recycle precondition is not established before "
                "the measured request"
                + (" :: " + post_reclaim["refusal_reason"]
                   if post_reclaim["refusal_reason"] else ""))
            return _finish(gate)
        # In `fixed` mode both extra checks are always registered above; the
        # mode test makes their absence fail closed instead of defaulting
        # permissive through a ``.get(..., True)``.
        fixed_extra_ok = (
            args.expect != "fixed"
            or (gate.checks["victim_target_relocation_count_positive"]["ok"]
                and gate.checks["post_reloc_destination_capacity"]["ok"]))
        if not (gate.checks["victim_held_live_target_refs"]["ok"]
                and gate.checks["victim_generation_changed"]["ok"]
                and gate.checks["head_resolved_after_reclaim"]["ok"]
                and gate.checks["post_target_in_index"]["ok"]
                and gate.checks["batch_exists_eq_expected"]["ok"]
                and gate.checks["post_no_target_drop_without_backup"]["ok"]
                and fixed_extra_ok):
            gate.invalidate(
                "reclaim executed but its post-state does not satisfy the "
                "preconditions (live victim refs/generation/head resolution/"
                "index membership/batch_exists/no-target-drop/relocation-"
                "reserve) -- measured request withheld")
            return _finish(gate)

        # ---- 5. force L1/L2 cold (STRICT flush) --------------------------
        flush = gc.flush_cache_strict(args.port, timeout_s=240.0, attempts=3)
        gate.report["flush_cache"] = flush
        gate.check("flush_cache_confirmed", flush.get("ok"), detail=flush)
        if not flush.get("ok"):
            gate.invalidate(
                "cold-L1 precondition not established: /flush_cache did not "
                f"return a confirmed success (status={flush.get('status')}, "
                f"body={flush.get('body')!r}); measured request withheld")
            return _finish(gate)
        off_cold = gc.console_size(console_path)  # flush + cold fillers window
        for j in range(max(0, args.cold_fillers)):
            fr = gc.generate(args.port, _filler_ids(1000 + j, args.sweep_tokens), 1)
            if not fr.get("ok"):
                gate.invalidate(f"cold-L2 filler {j} failed: {fr.get('error')}")
                return _finish(gate)
        _settle(console_path, off_store, timeout_s=30.0)
        cold_pre = _snapshot_membership(
            gate, args, namespace, suffix, run_dir, rid, "cold-pre", ids_a,
            str(prompt_json), victim_slot=victim_slot)
        if cold_pre is None:
            return _finish(gate)
        cold_pre_mem = cold_pre.get("membership") or {}
        gate.report["cold_pre_membership"] = _slim_membership(cold_pre)
        gate.check("cold_pre_target_still_indexed",
                   (cold_pre_mem.get("n_present") or 0) >= min_present,
                   detail={"n_present": cold_pre_mem.get("n_present"),
                           "required": min_present})
        if not gate.checks["cold_pre_target_still_indexed"]["ok"]:
            gate.invalidate(
                "after the cold-L1/L2 forcing the target is no longer fully in "
                "the extent index; the cold oracle is unestablishable")
            return _finish(gate)

        # ---- 6. measured cold request ------------------------------------
        cold = gc.generate(args.port, ids_a, args.max_new)
        cold_events = gc.parse_storage_events(
            gc.read_new_lines(console_path, off_cold))
        gate.report["cold_L1"] = _resp_slim(cold)
        gc.ensure_ok(gate, cold, "cold_L1")
        gate.report["cold_L1_console_evidence"] = gc.slim_storage_events(
            cold_events)
        gate.check("cold_request_executed",
                   cold["ok"] and bool(cold["output_ids"]),
                   detail=cold.get("error"))
        gate.check("cold_evidence_present", _evidence_ok(cold),
                   detail="response carried cached_tokens_details/telemetry")
        if not (gate.checks["cold_request_executed"]["ok"]
                and gate.checks["cold_evidence_present"]["ok"]):
            gate.invalidate("cold request did not execute / no tier evidence")
            return _finish(gate)
        # Post-cold membership (owner fix C3): classify a drop in the cold
        # window against a snapshot taken AFTER the measured request.  The
        # pre-request `cold_pre_target_still_indexed` verdict is STALE relative
        # to cold-window drops and must never be reused as `refs_intact`.
        cold_post = _snapshot_membership(
            gate, args, namespace, suffix, run_dir, rid, "cold-post", ids_a,
            str(prompt_json), victim_slot=victim_slot)
        if cold_post is None:
            return _finish(gate)
        cold_post_mem = cold_post.get("membership") or {}
        gate.report["cold_post_membership"] = _slim_membership(cold_post)
        cold_refs, cold_scope = _cold_window_drop_scope(
            cold_events, target_evidence, cold_pre_mem, cold_post_mem)
        gate.report["cold_window_drop_scope"] = {
            "scope": cold_scope, "refs_intact": cold_refs,
            "baseline": _delta_slim(cold_pre_mem),
            "now": _delta_slim(cold_post_mem)}
        gate.check("cold_window_no_target_drop_without_backup",
                   cold_scope["ok"],
                   detail={"scope": cold_scope,
                           "events": len(cold_events.get("dropped_no_backup",
                                                         []))})
        if not cold_scope["ok"]:
            gate.invalidate(
                "a graded-target (or unattributable) kv subtree was dropped "
                "without backup during the measured cold window "
                f"(target_roots={cold_scope['target_roots']}, "
                f"unknown_roots={cold_scope['unknown_roots']}, "
                f"refs_intact={cold_refs}); the cold oracle is unestablishable")
            return _finish(gate)
        cold_miss = gc.revoke_miss(cold_events)
        cold_hit = gc.revoke_storage_hit(cold_events)
        cold_restore = gc.max_restore_n_tokens(cold_events)
        gate.report["cold_L1_counters"] = {
            "storage_hit": cold_hit, "miss_marker": cold_miss,
            "restore_success_n_tokens": cold_restore,
            "tier": cold["tier"],
        }
        gate.check("cold_ids_eq_device",
                   cold["output_ids"] == warm["output_ids"],
                   detail=_ids_sig(cold["output_ids"], warm["output_ids"]))
        gate.check("cold_no_zero_hit_miss", not cold_miss,
                   detail={"miss_marker": cold_miss, "storage_hit": cold_hit})

        _classify(gate, args, cold_hit, cold_miss, cold_restore, cold,
                  post_mem, post_head, post_reclaim)
        return _finish(gate)
    except gc.GateBlocked as exc:
        gate.blocked(str(exc))
        return _finish(gate)
    except gc.GateInvalid as exc:
        gate.invalidate(str(exc))
        return _finish(gate)
    except Exception as exc:  # noqa: BLE001
        gate.error(exc, traceback.format_exc())
        return _finish(gate)
    finally:
        try:
            if proc is not None:
                gc.stop_server(proc, console)
        except Exception:  # noqa: BLE001
            pass
        gc.release_lock(lock_fd)


# ------------------------------------------------------------------ helpers
def _persist_chain(gate, args, console_path, namespace, suffix, ids_a,
                   ids_json, run_dir, rid):
    """Force the chain's write-back to L3 with UNRELATED fillers and prove it."""
    target_n = len(ids_a)
    min_present = math.ceil(args.min_index_fraction * (target_n - 1))
    kv_host_tokens = int(gc.parse_host_pool(console_path).get("kv_tokens") or 0)
    # the chain must leave L2: unrelated tokens written after its write-back
    # must exceed the free host capacity it occupied.
    host_evict_target = max(4096, kv_host_tokens - target_n + 4096)
    records = []
    filler_total = 0
    ev = {}
    last_mem = None
    # Pre-drop durable baseline for the chain: best membership seen while no
    # dropped-without-backup event was in the cumulative window.
    baseline = {}
    off = gc.console_size(console_path)
    for i in range(args.max_fillers):
        resp = gc.generate(args.port, _filler_ids(i, args.filler_tokens), 1)
        records.append({"i": i, "ok": resp["ok"], "seconds": resp["seconds"]})
        if not resp["ok"]:
            gate.invalidate(f"write-back filler {i} failed: {resp.get('error')}")
            return None
        filler_total += args.filler_tokens
        ev = gc.parse_storage_events(gc.read_new_lines(console_path, off))
        written = gc.extent_write_bytes(ev)
        pre = None
        if written > 0 or ev.get("dropped_no_backup"):
            pre = _snapshot_membership(gate, args, namespace, suffix, run_dir,
                                       rid, f"persist-{i}", ids_a, ids_json)
            if pre is None:
                return None
            last_mem = pre.get("membership") or {}
        drops_present = bool(ev.get("dropped_no_backup"))
        if pre is not None and not drops_present:
            if (_int_or_zero(last_mem.get("n_present"))
                    > _int_or_zero(baseline.get("n_present"))):
                baseline = last_mem
        # Target-scoped drop predicate (owner closure 1, tightened D1):
        # FOREIGN requires a no-decrease delta proof of the chain's durable refs
        # measured against a COMPLETE (full-window) drop-free baseline and
        # confirmed by a re-snapshot consumed immediately after the drop lines.
        # No complete baseline, a missing proxy, or any decrease =>
        # target/unknown => INVALID.  The node-id ordering bound is NOT used
        # (its invariant is false; see gate_common).
        refs_intact = None
        recheck_mem = None
        if pre is not None:
            post_snaps = [last_mem]
            if drops_present:
                # D1(ii): re-snapshot immediately around the drop window.  The
                # verdict must hold for BOTH post-drop snapshots, so a drop
                # landing between them cannot be hidden.
                recheck = _snapshot_membership(
                    gate, args, namespace, suffix, run_dir, rid,
                    f"persist-{i}-recheck", ids_a, ids_json)
                if recheck is None:
                    return None
                recheck_mem = recheck.get("membership") or {}
                post_snaps.append(recheck_mem)
            refs_intact = gc.combine_delta_status([
                gc.delta_status_with_rechecks(baseline, post_snaps)])
        drop_evidence = gc.target_node_evidence(ev, target_n)
        scoped = gc.scope_drop_events(ev, drop_evidence, refs_intact=refs_intact)
        scoped_ok = gc.drop_scope_ok(scoped)
        if ev.get("dropped_no_backup"):
            gate.report["persist_drop_scope"] = {
                "evidence": drop_evidence, "summary": scoped_ok,
                "refs_intact": refs_intact, "filler_tokens_total": filler_total,
                "baseline": _delta_slim(baseline),
                "now": _delta_slim(last_mem),
                "recheck": (_delta_slim(recheck_mem)
                            if recheck_mem is not None else None),
                "scoped_tail": scoped[-8:],
            }
        if not scoped_ok["ok"]:
            gate.report["persist_console_evidence"] = gc.slim_storage_events(ev)
            return {"ok": False, "dropped_no_backup_n": scoped_ok["n_total"],
                    "dropped_scope": scoped_ok,
                    "reason": "graded-target (or unattributable) kv subtree "
                              "dropped without backup due to host memory "
                              f"pressure during write-back (target_roots="
                              f"{scoped_ok['target_roots']}, unknown_roots="
                              f"{scoped_ok['unknown_roots']}, refs_intact="
                              f"{refs_intact}); only drops with a no-decrease "
                              "delta proof against a COMPLETE full-window "
                              "baseline, confirmed by the immediately-following "
                              "re-snapshot, are disposable"}
        if written <= 0:
            continue
        done = ((last_mem.get("n_present") or 0) >= min_present
                and filler_total >= host_evict_target)
        gate.log(f"write-back filler {i}: extent_write_bytes={written} "
                 f"n_present={last_mem.get('n_present')}/{target_n - 1} "
                 f"filler_total={filler_total} host_evict_target="
                 f"{host_evict_target}")
        if done:
            out = {
                "ok": True, "fillers": records, "filler_tokens_total": filler_total,
                "host_evict_target": host_evict_target,
                "kv_host_tokens": kv_host_tokens,
                "extent_write_bytes": written,
                "extent_write_n": len(ev.get("extent_write", [])),
                "reclaim_relocated_n": len(ev.get("reclaim_relocated", [])),
                "reclaim_refused_n": len(ev.get("reclaim_refused", [])),
                "extent_recycle_n": gc.extent_recycle_count(ev),
                "dropped_no_backup_n": scoped_ok["n_total"],
                "dropped_scope": scoped_ok,
                "drop_evidence": drop_evidence,
                "membership": {"n_present": last_mem.get("n_present"),
                               "query_window_len": target_n - 1,
                               "required": min_present,
                               "head_present_in_rebuilt_index":
                                   last_mem.get("head_present_in_rebuilt_index")},
                "console_evidence": gc.slim_storage_events(ev),
            }
            gate.check("persist_extent_write_seen", written > 0, detail=written)
            gate.check("persist_target_in_index",
                       (last_mem.get("n_present") or 0) >= min_present,
                       detail=out["membership"])
            gate.check("persist_host_eviction_proven",
                       filler_total >= host_evict_target,
                       detail={"filler_tokens_total": filler_total,
                               "host_evict_target": host_evict_target})
            gate.check("persist_no_target_drop_without_backup",
                       scoped_ok["ok"],
                       detail={"scope": scoped_ok,
                               "events": scoped_ok["n_total"],
                               "filler_tokens_total": filler_total})
            gate.report["persist_console_evidence"] = gc.slim_storage_events(ev)
            return out
    return {
        "ok": False, "fillers": records, "filler_tokens_total": filler_total,
        "dropped_no_backup_n": len(ev.get("dropped_no_backup", [])),
        "dropped_scope": gc.drop_scope_ok(ev.get("dropped_scopes") or []),
        "membership": last_mem,
        "reason": (
            f"chain not fully written back to L3 after {len(records)} unrelated "
            f"filler(s) ({filler_total} tokens, host_evict_target="
            f"{host_evict_target}); preconditions (b)/(c) not established"),
    }


def _snapshot_membership(gate, args, namespace, suffix, run_dir, rid, label,
                         ids_a, ids_json, victim_slot=None):
    snap = str(run_dir / f"store-snapshot-{label}-{rid}")
    try:
        mem, meta = gc.snapshot_and_membership(
            args.tree, namespace, suffix, snap,
            run_dir / f"wal-membership-{label}-{rid}.json", ids_json,
            query_window_len=len(ids_a) - 1, victim_slot=victim_slot)
    except gc.GateInvalid as exc:
        gate.invalidate(f"offline membership [{label}] failed: {exc}")
        return None
    mem = dict(mem)
    mem["_snapshot_meta"] = meta
    return mem


def _slim_membership(mem) -> dict:
    m = mem.get("membership") or {}
    v = mem.get("victim") or {}
    h = mem.get("head") or {}
    ts = mem.get("target_slots") or {}
    return {
        "membership": m,
        "predicate": mem.get("predicate"),
        "head_present": h.get("head_present_in_rebuilt_index"),
        "head_last_set_seq": h.get("head_last_set_seq"),
        "head_slot_last_drop_seq": h.get("head_slot_last_drop_seq"),
        "head_refreshed_after_drop": h.get("head_refreshed_after_drop"),
        "target_slots": ts,
        "victim": {k: v.get(k) for k in
                   ("slot", "generation", "live_refs", "live_bytes",
                    "target_live_refs", "target_live_bytes",
                    "target_live_head_present", "relocation_headroom_bytes",
                    "reclaim_relocatable", "fail_closed_reason")},
        "allocator_state": mem.get("allocator_state"),
        "drop_slot_frames": mem.get("drop_slot_frames"),
        "snapshot": mem.get("_snapshot_meta"),
    }


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _delta_slim(mem) -> dict:
    """Membership fields that carry the durable no-decrease proof."""
    mem = mem or {}
    return {k: mem.get(k) for k in
            ("n_present", "n_absent", "first_absent_index", "n_runs",
             "longest_run_len", "query_window_len")}


def _cold_window_drop_scope(cold_events, target_evidence, pre_mem, post_mem):
    """Classify cold-window drops against the POST-request membership (C3).

    ``pre_mem`` is the membership snapshot taken immediately before the measured
    cold request and ``post_mem`` the snapshot taken after it.  A no-decrease
    delta between them measured against a COMPLETE (full-window) ``pre_mem`` is
    the ONLY way a cold-window drop becomes ``foreign`` (D1); a partial
    ``pre_mem``, a missing proxy, a decrease, or any missing snapshot is
    target/unknown -> INVALID.  The pre-request verdict alone is never used as
    ``refs_intact``.
    """
    refs_intact = gc.combine_delta_status(
        [gc.durable_delta_status(pre_mem, post_mem)])
    return refs_intact, gc.drop_scope_ok(
        gc.scope_drop_events(cold_events, target_evidence,
                             refs_intact=refs_intact))


def _sweep_to_wrap(gate, args, console_path, target_slots,
                   target_evidence=None):
    """Send UNRELATED UNIQUE prefixes until the cursor reclaims a TARGET slot.

    The victim is whatever target-holding slot the circular cursor wraps into
    first (in a packed store that is the oldest full slot, not necessarily the
    chain-head slot), so the sweep watches for any reclaim/recycle naming a
    slot that the pre-sweep offline replay proved holds live target refs.
    """
    off_sweep = gc.console_size(console_path)
    out = {"requests_done": 0, "recycle_count": 0, "relocated_count": 0,
           "refused_count": 0, "dropped_no_backup_n": 0,
           "drop_scope": None,
           "first_wrap_request": None, "victim_slot": None,
           "abort_reason": None, "extent_recycle_total": 0,
           "consecutive_refusals": 0, "max_consecutive_refusals":
               args.max_consecutive_refusals,
           "records_tail": [], "sweep_written_bytes": 0}
    consecutive = 0
    for i in range(args.sweep_requests):
        resp = gc.generate(args.port, _filler_ids(500 + i, args.sweep_tokens), 1)
        out["requests_done"] += 1
        out["records_tail"] = (out["records_tail"] + [
            {"i": i, "ok": resp["ok"], "seconds": resp["seconds"]}])[-4:]
        if not resp["ok"]:
            out["abort_reason"] = f"sweep request {i} failed: {resp.get('error')}"
            return out
        ev = gc.parse_storage_events(gc.read_new_lines(console_path, off_sweep))
        out["sweep_written_bytes"] = gc.extent_write_bytes(ev)
        out["dropped_no_backup_n"] = len(ev.get("dropped_no_backup", []))
        # Target-scoped (owner closure 1).  A sweep round cannot cheaply re-run
        # the offline replay every request, so no positive delta proof exists
        # here and refs_intact is None: ANY drop in the sweep window is
        # therefore unknown -> INVALID (fail closed).  The node-id ordering
        # bound is NOT used (its invariant is false; see gate_common).
        scoped = gc.scope_drop_events(ev, target_evidence, refs_intact=None)
        scoped_ok = gc.drop_scope_ok(scoped)
        out["drop_scope"] = scoped_ok
        if out["dropped_no_backup_n"]:
            out["drop_scope_tail"] = scoped[-8:]
        if not scoped_ok["ok"]:
            out["abort_reason"] = (
                "graded-target (or unattributable) kv subtree dropped without "
                "backup due to host memory pressure during the sweep "
                f"(target_roots={scoped_ok['target_roots']}, unknown_roots="
                f"{scoped_ok['unknown_roots']}, total={scoped_ok['n_total']}); "
                "no positive no-decrease delta proof is available per sweep "
                "round, so this fails closed")
            return out
        out["extent_recycle_total"] = gc.extent_recycle_count(ev)
        hits = gc.reclaim_hits_for_slots(ev, target_slots)
        out["recycle_count"] = sum(1 for k, _, _ in hits if k == "recycle")
        out["relocated_count"] = sum(1 for k, _, _ in hits if k == "relocated")
        out["refused_count"] = sum(1 for k, _, _ in hits if k == "refused")
        out["hits_tail"] = [{"kind": k, "slot": s, "record": r}
                            for k, s, r in hits][-4:]
        success = [(k, s, r) for k, s, r in hits if k in ("relocated", "recycle")]
        if success:
            kind, slot, rec = success[0]
            out["first_wrap_request"] = i
            out["victim_slot"] = slot
            out["wrap_kind"] = kind
            out["wrap_event"] = rec
            return out
        refused = [h for h in hits if h[0] == "refused"]
        if refused:
            consecutive += 1
            out["consecutive_refusals"] = consecutive
            out["last_refusal"] = refused[-1][2]
            if consecutive >= args.max_consecutive_refusals:
                out["first_wrap_request"] = i
                out["victim_slot"] = refused[-1][1]
                out["wrap_kind"] = "refused"
                out["wrap_event"] = refused[-1][2]
                return out
        else:
            consecutive = 0
            out["consecutive_refusals"] = 0
    return out


def _reclaim_evidence(sweep, post, victim_slot, pre_generation,
                      target_slots=None) -> dict:
    ev = {
        "victim_slot": victim_slot,
        "victim_is_target_slot": (victim_slot in set(target_slots or [])
                                  if victim_slot is not None else False),
        "recycle_count": sweep.get("recycle_count", 0),
        "relocated_count": sweep.get("relocated_count", 0),
        "refused_count": sweep.get("refused_count", 0),
        "wrap_kind": sweep.get("wrap_kind"),
        "wrap_event": sweep.get("wrap_event"),
        "refusal_reason": None,
    }
    pv = post.get("victim") or {}
    drops = pv.get("drop_frames") or []
    post_gen = pv.get("generation")
    max_drop_gen = max((d.get("new_generation", 0) for d in drops), default=0)
    ev["drop_frames_for_victim"] = drops
    ev["generation_changed"] = bool(
        (post_gen is not None and pre_generation is not None
         and post_gen > pre_generation)
        or max_drop_gen > (pre_generation or 0))
    # did the cursor actually wrap into the victim? any of:
    #  * a relocation/refusal naming the victim (backend reached the victim),
    #  * an extent_recycle on the victim,
    #  * a DROP_SLOT frame for the victim.
    ev["wrap_observed"] = bool(ev["relocated_count"] or ev["recycle_count"]
                               or ev["refused_count"]
                               or ev["drop_frames_for_victim"])
    # a *successful, live* reclaim: relocation happened, or a recycle with the
    # victim's post-generation bumped and the head still resolvable.
    ev["reclaim_executed"] = bool(
        ev["relocated_count"]
        or (ev["recycle_count"] and ev["generation_changed"]))
    if ev["refused_count"] and not ev["reclaim_executed"]:
        ev["refusal_reason"] = (
            f"product refused circular reclaim of victim slot {victim_slot} "
            f"{ev['refused_count']}x: no destination capacity outside the "
            "victim (ExtentFileBackend fail-closed)")
    ts = post.get("target_slots") or {}
    head_slot = ts.get("head_current_slot")
    head = post.get("head") or {}
    head_present = bool(head.get("head_present_in_rebuilt_index"))
    # head survived if it is present and either moved out of the victim or the
    # victim was never dropped.
    moved = head_slot is not None and (
        victim_slot is None or int(head_slot) != int(victim_slot))
    ev["head_detail"] = {
        "head_current_slot": head_slot,
        "victim_slot": victim_slot,
        "head_present": head_present,
        "moved_out_of_victim": moved,
        "head_current_generation": ts.get("head_current_generation"),
        "head_refreshed_after_drop": head.get("head_refreshed_after_drop"),
    }
    ev["head_resolved"] = head_present and (
        moved or not ev["generation_changed"]
        or bool(head.get("head_refreshed_after_drop")))
    pred = post.get("predicate") or {}
    expected = ((post.get("prompt") or {}).get("query_window_len")
                or (post.get("membership") or {}).get("query_window_len"))
    ev["batch_exists_expected"] = expected
    ev["batch_exists"] = pred.get("window_from_page0_hits")
    ev["batch_exists_eq_expected"] = bool(
        expected is not None and ev["batch_exists"] == expected
        and expected > 0)
    ev["dropped_no_backup_n"] = sweep.get("dropped_no_backup_n", 0)
    scope = sweep.get("drop_scope")
    if scope is None:
        # Backward-compatible shape for synthetic callers/tests.
        scope = {"n_total": sweep.get("dropped_no_backup_n", 0),
                 "ok": sweep.get("dropped_no_backup_n", 0) == 0}
    ev["drop_scope"] = scope
    if ev["dropped_no_backup_n"]:
        # L5: a non-None scope without an explicit ``ok is True`` is
        # fail-closed (a row exists but the scope cannot vouch for it).
        ev["no_target_drop_without_backup"] = scope.get("ok") is True
    else:
        ev["no_target_drop_without_backup"] = True
    return ev


def _classify(gate, args, cold_hit, cold_miss, cold_restore, cold, mem, head,
              reclaim) -> None:
    chain_len = max(0, int(gate.report.get("prompt", {}).get("n", 0)) - 1)
    cold_storage = int(cold["tier"]["storage"])
    cold_device = int(cold["tier"]["device"])
    restore_frac = (cold_restore / chain_len) if chain_len else 0.0
    gate.report["classification"] = {
        "expect": args.expect,
        "cold_storage": cold_storage,
        "cold_device": cold_device,
        "cold_storage_hit": cold_hit,
        "cold_miss_marker": cold_miss,
        "cold_restore_n_tokens": cold_restore,
        "restore_fraction_of_chain": round(restore_frac, 4),
        "min_restore_fraction": args.min_restore_fraction,
        "victim_reclaim_kind": reclaim.get("wrap_kind"),
        "victim_relocated": reclaim.get("relocated_count", 0),
        "victim_recycle_events": reclaim.get("recycle_count", 0),
        "victim_refusals": reclaim.get("refused_count", 0),
        "head_post_slot": (reclaim.get("head_detail") or {}).get(
            "head_current_slot"),
        "head_moved_out_of_victim": (reclaim.get("head_detail") or {}).get(
            "moved_out_of_victim"),
        "offline_first_absent_index": mem.get("first_absent_index"),
        "offline_n_present": mem.get("n_present"),
        "offline_head_present": head.get("head_present_in_rebuilt_index"),
        "offline_head_refreshed_after_drop": head.get(
            "head_refreshed_after_drop"),
        "batch_exists": reclaim.get("batch_exists"),
        "batch_exists_expected": reclaim.get("batch_exists_expected"),
    }
    if args.expect == "fixed":
        fixed_ok = (
            cold_storage > 0
            and cold_device == 0
            and not cold_miss
            and (cold_hit is None or cold_hit > 0)
            and cold_restore > 0
            and restore_frac >= args.min_restore_fraction
            and bool(reclaim.get("batch_exists_eq_expected"))
            and gate.checks.get("cold_ids_eq_device", {}).get("ok") is True)
        if fixed_ok:
            gate.log("FIXED-mode expectation observed: the reclaim conserved/"
                     "relocated the live head and the cold request restored "
                     "from the storage tier with exact ids")
        else:
            gate.fail(
                "FIXED-mode expectation NOT observed: after a proven reclaim of "
                "the head slot the cold request must restore from the storage "
                "tier (storage>0, device==0, no zero-hit miss, "
                "batch_exists==expected) with exact ids")
    else:
        unfixed_ok = (
            reclaim.get("wrap_observed")
            and reclaim.get("generation_changed")
            and not reclaim.get("relocated_count")
            and cold_storage == 0
            and cold_miss
            and mem.get("first_absent_index") == 0
            and (mem.get("n_present") or 0) > 0)
        if unfixed_ok:
            gate.log("UNFIXED-mode expectation observed: the reclaim dropped "
                     "the head and the cold request took a zero-hit miss")
        else:
            gate.fail(
                "UNFIXED-mode expectation NOT observed: expected a destructive "
                "reclaim with a zero-hit cold miss and the offline head absent")


def _settle(console_path, offset, timeout_s=60.0):
    last = -1
    stable = 0.0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        ev = gc.parse_storage_events(gc.read_new_lines(console_path, offset))
        cur = gc.extent_write_bytes(ev)
        if cur == last:
            stable += 2.0
            if stable >= 6.0:
                return
        else:
            stable = 0.0
            last = cur
        time.sleep(2.0)


def _resp_slim(resp) -> dict:
    return {"ok": resp.get("ok"), "error": resp.get("error"),
            "seconds": resp.get("seconds"), "tier": resp.get("tier"),
            "n_ids": len(resp.get("output_ids") or []),
            "output_ids": resp.get("output_ids")}


def _evidence_ok(resp) -> bool:
    tier = resp.get("tier") or {}
    return bool(tier.get("has_cached_tokens_details")
                or tier.get("has_hicache_telemetry"))


def _ids_sig(got, want) -> dict:
    got, want = got or [], want or []
    return {"got_n": len(got), "want_n": len(want), "equal": got == want,
            "got_head": got[:8], "want_head": want[:8]}


def _filler_ids(i: int, n_tokens: int):
    rng = random.Random(180000 + i)
    # distinct per index and unrelated to the chat-rendered chain, so every
    # request allocates NEW storage keys (no prefix match on the chain).
    return [rng.randrange(1000, 60000) for _ in range(n_tokens)]


def _finish(gate: gc.Gate) -> int:
    gate.report["gpu_compute_apps_after"] = gc.gpu_compute_apps()
    verdict, rc = gate.finish()
    gate.save("gate-a-f1-result.json")
    gate.log(f"VERDICT={verdict} rc={rc}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
