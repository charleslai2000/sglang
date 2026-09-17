#!/usr/bin/env python3
"""Gate A -- L3 content integrity at >=64K (DEVICE == L3 == RECOVERED).

Two distinct >=65,000-token prompts, each carrying its own unique marker
(ALPHA-7Q3Z-42 / BRAVO-9X8Y-17) so cross-session bleed is observable.

Oracle (per prompt): the per-token output ids must be identical across the
DEVICE arm, the L3 arm, and the RECOVERED (post-restart) arm, and the L3 /
RECOVERED arms must restore from the STORAGE tier
(``cached_tokens_details.storage > 0`` with ``device == 0`` and ``host == 0``).

Staged preconditions (FIX 1 -- asserted BEFORE the measured request; any unmet
precondition is INVALID, never FAIL/PASS):
  a. target prefix created and device-resident;
  b. write-back to L3 observed (``evt=extent_write`` + store manifest growth);
  c. the target is present in the run's OWN Extent index (offline replay of
     this run's namespace; ``wal_forensics.py --mode membership``);
  d/e. unrelated filler prefixes (never sharing the target prefix) force the
     target out of L1 and L2; the filler token volume proves L1+L2 eviction;
  f. immediately before the measured request: storage index hit proven offline,
     device/host absence guaranteed by the filler volume;
  g. only then the measured request;
  h. require storage > 0 AND device == 0 AND host == 0 AND ids == DEVICE ids.

Host-pool sizing (the campaign root cause): HiCache write-back is
device -> host -> storage, so the graded prompt must FIT in the host pool to be
backed up at all.  A kv host pool below the prompt can only emit
``write_back: KV subtree dropped without backup due to host memory pressure``
and every arm sees ``storage == 0``.  ``--hicache-size`` is SI GB and is split
across the kv+mamba device pools; see ``gate_common`` sizing constants.  The
gate asserts the ACTUAL allocated pool (parsed from the server console) covers
prompt + ``--host-pool-margin`` before any measured request.

Store policy: one unique namespace per run.  No clear/flush of any store;
nothing under the shared /data/l3/local-prod-v1.1 store is touched.

Exit codes: 0 PASS | 1 FAIL | 2 INVALID | 3 PENDING | 4 ERROR | 5 BLOCKED.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_common as gc  # noqa: E402

MARK_A = "ALPHA-7Q3Z-42"
MARK_B = "BRAVO-9X8Y-17"
PAGE_BYTES = 16384  # 16 KiB per token-page (fp8_e4m3 KV)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=gc.DEFAULT_TREE)
    ap.add_argument("--model", default=gc.DEFAULT_MODEL)
    ap.add_argument("--port", type=int, default=gc.DEFAULT_PORT)
    ap.add_argument("--hc-size", type=int, default=8,
                    help="--hicache-size in SI GB; must stage the graded prompt")
    ap.add_argument("--prompt-tokens", type=int, default=65000)
    ap.add_argument("--host-pool-margin", type=int, default=4096,
                    help="required kv-host headroom above the graded prompt")
    ap.add_argument("--max-new", type=int, default=32)
    ap.add_argument("--filler-tokens", type=int, default=16000,
                    help="unrelated filler tokens per eviction round")
    ap.add_argument("--max-fillers", type=int, default=8,
                    help="bound on unrelated eviction fillers; must cover one "
                         "full host-pool cycle (host_cycle_target)")
    ap.add_argument("--extent-size", type=int, default=64 << 20)
    ap.add_argument("--file-size", type=int, default=0,
                    help="0 => computed from prompt + filler budget")
    ap.add_argument("--slots-margin", type=int, default=4)
    ap.add_argument("--min-index-fraction", type=float, default=0.99)
    ap.add_argument("--wal-checkpoint-bytes", type=int, default=32 << 20)
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
    """Small disposable extent store sized so no wrap interrupts Gate A."""
    pages_per_slot = args.extent_size // PAGE_BYTES
    if pages_per_slot <= 0:
        raise gc.GateInvalid("extent_size smaller than one 16 KiB page")
    target_slots = math.ceil(args.prompt_tokens / pages_per_slot)
    filler_slots = math.ceil(args.filler_tokens / pages_per_slot)
    file_size = args.file_size or (
        (target_slots + args.max_fillers * filler_slots + args.slots_margin)
        * args.extent_size)
    if file_size < args.extent_size or file_size % args.extent_size != 0:
        raise gc.GateInvalid(
            f"file_size {file_size} must be a positive multiple >= "
            f"extent_size {args.extent_size}")
    return {
        "extent_size": args.extent_size,
        "file_size": file_size,
        "num_slots": file_size // args.extent_size,
        "pages_per_slot": pages_per_slot,
        "target_slots": target_slots,
        "filler_slots": filler_slots,
        "reason": "sparse file; large enough that target+filler writes never "
                  "wrap (wraps are exercised by Gate A-F1, not here)",
    }


def parse_args_and_geometry(args):
    geom = compute_geometry(args)
    return geom


def main() -> int:
    args = parse_args()
    tag = "gateA"
    rid = args.run_id or gc.run_id(tag)
    run_dir = gc.RUN_DIR / tag
    gate = gc.Gate(tag, run_dir, extra={
        "tree": args.tree, "model": args.model, "port": args.port,
        "hc_size_gb": args.hc_size, "prompt_tokens": args.prompt_tokens,
        "host_pool_margin": args.host_pool_margin, "max_new": args.max_new,
        "filler_tokens": args.filler_tokens, "max_fillers": args.max_fillers,
        "run_id": rid,
        "contract": {
            "endpoint": "/generate",
            "input": "pre-rendered chat template (enable_thinking=false)",
            "temperature": 0, "top_p": 1.0, "top_k": 1,
            "sampling_seed": gc.SEED, "max_new_tokens": args.max_new,
            "ignore_eos": True,
        },
    })
    gate.report["store_policy"] = {
        "shared_production_store": gc.PRODUCTION_STORE,
        "clear_or_flush_called": False,
        "namespace": "one unique per-run namespace; no shared clear/reset",
    }
    gate.report["host_pool_sizing"] = gc.sizing_arithmetic(
        args.hc_size, args.prompt_tokens, args.host_pool_margin)
    lock_fd = None
    proc = console = None
    try:
        gate.report["gpu_compute_apps_before"] = gc.gpu_compute_apps()
        gate.check("tree_present",
                   os.path.exists(os.path.join(args.tree, "src", "python",
                                               "sglang", "__init__.py")),
                   detail=args.tree)
        gate.check("tree_python_present",
                   os.path.exists(gc.resolve_python(args.tree)),
                   detail=gc.resolve_python(args.tree))
        pf = gc.preflight_import(args.tree)
        gate.report["preflight_import"] = pf
        gate.check("preflight_sglang_file_in_tree", pf.get("ok"), detail=pf)
        if not pf.get("ok"):
            gate.invalidate("tree binding not proven (stale editable install?)")
            return _finish(gate)

        # --- prompts (CPU only, before the lock) -------------------------
        pa = run_dir / "prompt_A.json"
        pb = run_dir / "prompt_B.json"
        # Distinct BODY seeds, not just distinct trailing markers: prompt_builder
        # builds the body from its seed, so the same seed would give A and B a
        # long shared token prefix and B would prefix-match A's radix/storage
        # pages instead of exercising an independent target.
        info_a = gc.build_prompt(args.tree, args.model, MARK_A,
                                 args.prompt_tokens, pa, seed=gc.SEED)
        info_b = gc.build_prompt(args.tree, args.model, MARK_B,
                                 args.prompt_tokens, pb, seed=gc.SEED + 101)
        ids_a, ids_b = info_a["ids"], info_b["ids"]
        gate.report["prompts"] = {
            "A": {"marker": MARK_A, "n": len(ids_a), "seed": gc.SEED},
            "B": {"marker": MARK_B, "n": len(ids_b), "seed": gc.SEED + 101},
            "target_tokens": args.prompt_tokens,
        }
        gate.check("prompt_A_ge_64k", len(ids_a) >= 64000, detail=len(ids_a))
        gate.check("prompt_B_ge_64k", len(ids_b) >= 64000, detail=len(ids_b))
        gate.check("prompts_distinct", ids_a != ids_b)
        shared = 0
        for x, y in zip(ids_a, ids_b):
            if x != y:
                break
            shared += 1
        gate.report["prompts_shared_prefix_tokens"] = shared
        gate.check("prompts_independent_prefix",
                   shared < 1024,
                   detail={"shared_prefix_tokens": shared,
                           "note": "A and B must be independent targets, not "
                                   "one prefix-matching the other"})
        if not (gate.checks["prompt_A_ge_64k"]["ok"]
                and gate.checks["prompt_B_ge_64k"]["ok"]):
            gate.invalidate("built prompt(s) below the >=64K regime")
            return _finish(gate)
        if not gate.checks["prompts_distinct"]["ok"]:
            gate.invalidate("the two built prompts are identical")
            return _finish(gate)
        if not gate.checks["prompts_independent_prefix"]["ok"]:
            gate.invalidate(
                f"prompt B shares its first {shared} tokens with prompt A; the "
                "two targets are not independent")
            return _finish(gate)

        geom = parse_args_and_geometry(args)
        gate.report["geometry"] = geom
        suffix = config_suffix(args.model)
        max_prompt = max(len(ids_a), len(ids_b))
        gate.report["sizing_check"] = gc.sizing_arithmetic(
            args.hc_size, max_prompt, args.host_pool_margin)

        lock_fd = gc.acquire_lock(f"gate-a-{rid}",
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
        if args.namespace:
            os.makedirs(namespace, exist_ok=True)
        gate.report["namespace"] = namespace
        gate.report["namespace_before"] = gc.namespace_manifest(namespace, suffix)
        gate.log(f"namespace (unique, no clear/flush): {namespace}")

        extra_env = {
            "SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE": str(geom["extent_size"]),
            "SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE": str(geom["file_size"]),
            # GC off: this gate must not confuse watermark GC with the oracle.
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
        gate.log(f"launched server s1 pid={proc.pid} "
                 f"file_size={geom['file_size']} slots={geom['num_slots']}")
        health = gc.wait_health(args.port, proc, args.health_timeout)
        gate.check("server_s1_healthy", health.get("ok"), detail=health)
        gate.check("server_s1_not_inheriting_lock",
                   not gc.proc_holds_lock(proc.pid),
                   detail="lock fd absent from server /proc/<pid>/fd")
        if not health.get("ok"):
            gate.invalidate(f"server s1 unhealthy: {health}")
            return _finish(gate)
        env = gc.proc_env(proc.pid)
        gate.check("server_s1_pythonpath",
                   env.get("PYTHONPATH") == os.path.join(args.tree, "src", "python"),
                   detail=env.get("PYTHONPATH"))
        kg = gc.kv_dtype_gate(console_path)
        gate.check("kv_dtype_gate_s1", kg.get("ok"), detail=kg)
        gate.report["kv_gate_s1"] = kg

        # --- HOST POOL PRECONDITION (must precede any measured request) ---
        hp = gc.parse_host_pool(console_path, prompt_tokens=max_prompt,
                                host_pool_margin=args.host_pool_margin)
        gate.report["host_pool_actual_s1"] = hp
        gate.check("host_pool_stages_graded_prompt", hp.get("ok"),
                   detail={k: hp.get(k) for k in
                           ("kv_tokens", "required_kv_host_tokens",
                            "kv_headroom_tokens", "smaller_than_device_warnings")})
        if not hp.get("ok"):
            gate.invalidate(
                "kv host pool does not stage the graded prompt "
                f"(kv_tokens={hp.get('kv_tokens')} < required="
                f"{hp.get('required_kv_host_tokens')}): write-back can only be "
                "dropped without backup -> storage tier unreachable")
            return _finish(gate)

        # ---- (a) DEVICE arm --------------------------------------------
        off = gc.console_size(console_path)
        gc.generate(args.port, ids_a, 1)
        dev_a = gc.generate(args.port, ids_a, args.max_new)
        gc.generate(args.port, ids_b, 1)
        dev_b = gc.generate(args.port, ids_b, args.max_new)
        gate.report["DEVICE_A"] = dev_a
        gate.report["DEVICE_B"] = dev_b
        gc.ensure_ok(gate, dev_a, "DEVICE_A")
        gc.ensure_ok(gate, dev_b, "DEVICE_B")
        gate.check("device_A_ok", dev_a["ok"] and bool(dev_a["output_ids"]),
                   detail=dev_a.get("error"))
        gate.check("device_B_ok", dev_b["ok"] and bool(dev_b["output_ids"]),
                   detail=dev_b.get("error"))
        gate.check("device_A_device_resident",
                   dev_a["tier"]["device"] >= 0.8 * len(ids_a),
                   detail=dev_a["tier"])
        gate.check("device_B_device_resident",
                   dev_b["tier"]["device"] >= 0.8 * len(ids_b),
                   detail=dev_b["tier"])
        gate.check("device_A_storage_zero", dev_a["tier"]["storage"] == 0,
                   detail=dev_a["tier"]["storage"])
        gate.check("device_B_storage_zero", dev_b["tier"]["storage"] == 0,
                   detail=dev_b["tier"]["storage"])
        gate.check("device_outputs_distinct",
                   dev_a["output_ids"] != dev_b["output_ids"],
                   detail={"A": (dev_a["output_ids"] or [])[:8],
                           "B": (dev_b["output_ids"] or [])[:8]})
        if not (dev_a["ok"] and dev_b["ok"] and dev_a["output_ids"]
                and dev_b["output_ids"]):
            gate.invalidate("DEVICE reference arm did not execute cleanly")
            return _finish(gate)

        # ---- (b)(c)(d)(e) persist to L3 with UNRELATED fillers ---------
        persist = _persist_targets(
            gate, args, console_path, off, namespace, suffix,
            {"A": (ids_a, str(pa)), "B": (ids_b, str(pb))}, run_dir, rid)
        if persist is None:
            return _finish(gate)
        gate.report["persist"] = persist
        if not persist["ok"]:
            gate.invalidate(persist["reason"])
            return _finish(gate)

        # ---- (f) required pre-assertions before the measured request -----
        # Owner closure 3: prove the target is in the extent index, the device
        # and host tiers are cold by unrelated-filler volume, a storage
        # candidate hit exists, host-pool sizing covers the workload, and no
        # graded-target drop occurred.  Any missing precondition -> INVALID
        # (never FAIL) and the measured request is withheld.  These are proven
        # offline / by volume, NOT by a re-warming request.
        pre = persist.get("preconditions") or {}
        if not gc.assert_preconditions(gate, "gate-a-l3-arm", [
            ("pre_host_pool_stages_workload",
             gate.checks.get("host_pool_stages_graded_prompt",
                             {}).get("ok") is True,
             {k: hp.get(k) for k in ("kv_tokens", "required_kv_host_tokens")}),
            ("pre_target_in_extent_index",
             bool(pre.get("target_in_extent_index")), pre.get("membership")),
            ("pre_device_miss_guaranteed",
             bool(pre.get("device_eviction_proven")),
             (persist.get("device_eviction_proof") or {})),
            ("pre_host_miss_guaranteed",
             bool(pre.get("host_eviction_proven")),
             (persist.get("host_eviction_proof") or {})),
            ("pre_storage_candidate_hit",
             bool(pre.get("storage_candidate_hit")), pre.get("membership")),
            ("pre_no_target_drop_without_backup",
             bool(pre.get("no_target_drop_without_backup")),
             pre.get("drop_scope")),
        ]):
            return _finish(gate)

        # ---- (g) measured L3 arm (preconditions proven above) ----------
        l3_a = gc.generate(args.port, ids_a, args.max_new)
        l3_b = gc.generate(args.port, ids_b, args.max_new)
        gate.report["L3_A"] = l3_a
        gate.report["L3_B"] = l3_b
        gc.ensure_ok(gate, l3_a, "L3_A")
        gc.ensure_ok(gate, l3_b, "L3_B")
        l3_events = gc.parse_storage_events(gc.read_new_lines(console_path, off))
        gate.report["L3_console_evidence"] = gc.slim_storage_events(l3_events)
        gate.report["store_after_l3"] = gc.namespace_manifest(namespace, suffix)
        _assert_storage_arm(gate, "l3", l3_a, l3_b, dev_a, dev_b, ids_a, ids_b)

        # ---- graceful restart, same namespace, full process death ------
        ident_pre = gc.wal_forensics(args.tree, namespace, suffix, "identity",
                                     run_dir / "wal-identity-pre-restart.json")
        gate.report["wal_identity_pre_restart"] = ident_pre
        uuid_pre = (ident_pre.get("manifest_state") or {}).get("file_uuid")
        s1_pid = proc.pid
        stop1 = gc.stop_server(proc, console)
        proc = console = None
        gate.report["stop_s1"] = stop1
        gate.check("server_s1_exited", stop1.get("stopped") is True, detail=stop1)
        gone = gc.wait_proc_gone(s1_pid, 180)
        gate.check("server_s1_process_gone", gone, detail=s1_pid)
        gate.check("port_free_before_restart", gc.wait_port_free(args.port, 300),
                   detail=args.port)
        if not gone or not gc.port_free(args.port):
            gate.invalidate("s1 did not fully terminate before restart")
            return _finish(gate)
        metrics_dir2 = run_dir / "metrics_s2"
        console2 = run_dir / "server.console.s2.log"
        proc, console, _ = gc.launch_server(
            args.tree, args.model, args.port, namespace, console2,
            metrics_dir2, hc_size_gb=args.hc_size, extra_env=extra_env)
        gate.log(f"relaunched server s2 pid={proc.pid}")
        health2 = gc.wait_health(args.port, proc, args.health_timeout)
        gate.check("server_s2_healthy", health2.get("ok"), detail=health2)
        gate.check("server_s2_is_new_process", proc.pid != s1_pid,
                   detail={"s1": s1_pid, "s2": proc.pid})
        gate.check("server_s2_not_inheriting_lock",
                   not gc.proc_holds_lock(proc.pid))
        if not health2.get("ok"):
            gate.invalidate(f"server s2 unhealthy: {health2}")
            return _finish(gate)
        env2 = gc.proc_env(proc.pid)
        gate.check("server_s2_pythonpath",
                   env2.get("PYTHONPATH") == os.path.join(args.tree, "src", "python"),
                   detail=env2.get("PYTHONPATH"))
        kg2 = gc.kv_dtype_gate(console2)
        gate.check("kv_dtype_gate_s2", kg2.get("ok"), detail=kg2)
        gate.report["kv_gate_s2"] = kg2
        ident_post = gc.wal_forensics(args.tree, namespace, suffix, "identity",
                                      run_dir / "wal-identity-post-restart.json")
        gate.report["wal_identity_post_restart"] = ident_post
        uuid_post = (ident_post.get("manifest_state") or {}).get("file_uuid")
        gate.check("recovered_same_store", bool(uuid_pre) and uuid_pre == uuid_post,
                   detail={"pre": uuid_pre, "post": uuid_post})
        if not (uuid_pre and uuid_pre == uuid_post):
            gate.invalidate("s2 did not reopen the same dedicated store")
            return _finish(gate)
        hp2 = gc.parse_host_pool(console2, prompt_tokens=max_prompt,
                                 host_pool_margin=args.host_pool_margin)
        gate.report["host_pool_actual_s2"] = hp2
        gate.check("host_pool_stages_graded_prompt_s2", hp2.get("ok"),
                   detail=hp2.get("kv_tokens"))

        # ---- RECOVERED arm ---------------------------------------------
        off2 = gc.console_size(console2)
        rec_a = gc.generate(args.port, ids_a, args.max_new)
        rec_b = gc.generate(args.port, ids_b, args.max_new)
        gate.report["RECOVERED_A"] = rec_a
        gate.report["RECOVERED_B"] = rec_b
        gc.ensure_ok(gate, rec_a, "RECOVERED_A")
        gc.ensure_ok(gate, rec_b, "RECOVERED_B")
        rec_events = gc.parse_storage_events(gc.read_new_lines(console2, off2))
        gate.report["RECOVERED_console_evidence"] = gc.slim_storage_events(
            rec_events)
        gate.report["store_after_recovered"] = gc.namespace_manifest(
            namespace, suffix)
        _assert_storage_arm(gate, "rec", rec_a, rec_b, dev_a, dev_b,
                            ids_a, ids_b)
        gate.check("no_cross_session_bleed",
                   dev_a["output_ids"] != dev_b["output_ids"]
                   and l3_a["output_ids"] != l3_b["output_ids"]
                   and rec_a["output_ids"] != rec_b["output_ids"]
                   and rec_a["output_ids"] == dev_a["output_ids"]
                   and rec_b["output_ids"] == dev_b["output_ids"])

        # ---- verdict classification ------------------------------------
        storage_proven = _storage_proven(l3_a, l3_b) and _storage_proven(
            rec_a, rec_b)
        if not storage_proven:
            gate.invalidate(
                "storage-tier restore NOT confirmed on L3/RECOVERED arms "
                "(need storage>0 with device==0 and host==0); device/host-only "
                "content equality is INVALID, not PASS")
        required_ok = all(c.get("ok") for c in gate.checks.values()
                          if not c.get("optional"))
        if storage_proven and not required_ok:
            gate.fail("content mismatch / bleed under confirmed storage-tier "
                      "restore -> production blocker")
        if storage_proven and required_ok:
            gate.report["storage_tier_proof"] = {
                "fields": [
                    "cached_tokens_details.storage > 0 (primary)",
                    "cached_tokens_details.device == 0 and host == 0 (restore "
                    "origin, not just a positive counter)",
                    "cached_tokens_details.storage_backend == ExtentFileBackend",
                    "offline Extent-index membership of this run's namespace "
                    "(pre-measurement)",
                ],
                "L3_A": l3_a["tier"], "L3_B": l3_b["tier"],
                "REC_A": rec_a["tier"], "REC_B": rec_b["tier"],
            }
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


def _storage_proven(a: dict, b: dict) -> bool:
    ta, tb = a.get("tier") or {}, b.get("tier") or {}
    return (int(ta.get("storage") or 0) > 0
            and int(tb.get("storage") or 0) > 0
            and int(ta.get("device") or 0) == 0
            and int(tb.get("device") or 0) == 0)


def _as_positive(value) -> int:
    """Non-negative int for baseline comparison; None/garbage -> 0."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _targets_in_index_ok(membership, min_present_by_target, default_min) -> bool:
    """Every target present at its OWN threshold; empty membership is NOT ok.

    An empty membership dict means the offline verdict has no target rows to
    stand on -- it must never default to ``True`` (fail-open).
    """
    if not membership:
        return False
    return all(
        (m.get("n_present") or 0) >=
        min_present_by_target.get(
            name, m.get("min_present_required") or default_min)
        for name, m in membership.items())


def _assert_storage_arm(gate, prefix, ra, rb, dev_a, dev_b, ids_a, ids_b):
    """The measured-arm oracle: storage-sourced restore with exact ids.

    ``device == 0`` is required (the content did not come from L1).  ``host`` is
    recorded, not gated: with ``write_back`` a restore may stage through host
    while the storage counter is positive; the tier rule rejects only a
    host/device-ONLY restore, i.e. ``storage == 0``.
    """
    gate.check(f"{prefix}_A_ok", ra["ok"] and bool(ra["output_ids"]),
               detail=ra.get("error"))
    gate.check(f"{prefix}_B_ok", rb["ok"] and bool(rb["output_ids"]),
               detail=rb.get("error"))
    gate.check(f"{prefix}_A_storage_positive", ra["tier"]["storage"] > 0,
               detail=ra["tier"])
    gate.check(f"{prefix}_B_storage_positive", rb["tier"]["storage"] > 0,
               detail=rb["tier"])
    gate.check(f"{prefix}_A_device_miss", int(ra["tier"]["device"]) == 0,
               detail=ra["tier"]["device"])
    gate.check(f"{prefix}_B_device_miss", int(rb["tier"]["device"]) == 0,
               detail=rb["tier"]["device"])
    gate.record(f"{prefix}_host_tokens", {"A": ra["tier"]["host"],
                                          "B": rb["tier"]["host"]})
    gate.check(f"{prefix}_backend_extent",
               ra["tier"]["storage_backend"] == "ExtentFileBackend"
               and rb["tier"]["storage_backend"] == "ExtentFileBackend",
               detail=[ra["tier"]["storage_backend"],
                       rb["tier"]["storage_backend"]])
    gate.check(f"{prefix}_A_ids_eq_device",
               ra["output_ids"] == dev_a["output_ids"],
               detail=_ids_sig(ra["output_ids"], dev_a["output_ids"]))
    gate.check(f"{prefix}_B_ids_eq_device",
               rb["output_ids"] == dev_b["output_ids"],
               detail=_ids_sig(rb["output_ids"], dev_b["output_ids"]))


def _persist_targets(gate, args, console_path, off, namespace, suffix,
                     targets, run_dir, rid):
    """(b)(c)(d)(e): unrelated fillers force L1/L2 eviction into L3, then prove
    the target is in this run's OWN Extent index offline.

    Returns None when it has already invalidated the gate.
    """
    records = []
    filler_tokens_total = 0
    target_n = max(len(ids) for ids, _ in targets.values())
    min_present = math.ceil(args.min_index_fraction * (target_n - 1))
    # Per-target acceptance thresholds: A and B need not be equal length, so
    # each target is compared against its OWN window (a global max would be a
    # false-INVALID for the shorter prompt).
    min_present_by_target = {
        name: math.ceil(args.min_index_fraction * (len(ids) - 1))
        for name, (ids, _) in targets.items()}
    kv_host_tokens = int(gc.parse_host_pool(console_path).get("kv_tokens") or 0)
    host_cycle_target = kv_host_tokens or (target_n + args.host_pool_margin)
    last_membership = None
    # Pre-drop durable baseline per target: the best membership seen while NO
    # dropped-without-backup event was in the cumulative console window.
    baseline_by_target = {}
    last_man = {}
    ev = {}
    for i in range(args.max_fillers):
        resp = gc.generate(args.port, _filler_ids(i, args.filler_tokens), 1)
        records.append({"i": i, "ok": resp["ok"], "seconds": resp["seconds"],
                        "error": resp.get("error")})
        if not resp["ok"]:
            gate.invalidate(f"eviction filler {i} failed: {resp.get('error')}")
            return None
        filler_tokens_total += args.filler_tokens
        ev = gc.parse_storage_events(gc.read_new_lines(console_path, off))
        written = gc.extent_write_bytes(ev)
        man = gc.namespace_manifest(namespace, suffix)
        last_man = man
        membership = None
        if written > 0 or ev.get("dropped_no_backup"):
            membership = _membership_both(
                gate, args, namespace, suffix, targets, run_dir, rid, i)
            if membership is None:
                return None
            if not membership:
                gate.invalidate(
                    f"offline membership [{i}] returned no target rows; the "
                    "target-scoped drop verdict is unestablishable")
                return None
            last_membership = membership
        drops_present = bool(ev.get("dropped_no_backup"))
        if membership is not None and not drops_present:
            for name, m in membership.items():
                if (_as_positive(m.get("n_present"))
                        > _as_positive((baseline_by_target.get(name) or {})
                                       .get("n_present"))):
                    baseline_by_target[name] = m
        # Target-scoped drop predicate (owner closure 1, tightened D1).
        # FOREIGN requires a positive DELTA proof per target measured against a
        # COMPLETE (full-window) drop-free baseline, and confirmed by a
        # re-snapshot consumed immediately after the drop lines: a target page
        # that became durable only after the baseline, or a drop masked by
        # concurrent growth/backfill, can no longer read "intact".  No complete
        # baseline, an empty membership, a missing proxy, or any decrease =>
        # target/unknown => INVALID.  The node-id ordering bound is deliberately
        # NOT used (its invariant is false; see gate_common).
        refs_intact = None
        recheck = None
        if membership is not None:
            post_snaps = [membership]
            if drops_present:
                # D1(ii): re-snapshot immediately around the drop window.  The
                # verdict must hold for BOTH post-drop snapshots, so a drop
                # landing between them cannot be hidden.
                recheck = _membership_both(
                    gate, args, namespace, suffix, targets, run_dir, rid, i)
                if recheck is None:
                    return None
                post_snaps.append(recheck)
            refs_intact = gc.combine_delta_status([
                gc.delta_status_with_rechecks(
                    baseline_by_target.get(name),
                    [s.get(name) for s in post_snaps])
                for name in membership])
        drop_evidence = gc.target_node_evidence(ev, target_n)
        scoped = gc.scope_drop_events(ev, drop_evidence, refs_intact=refs_intact)
        scoped_ok = gc.drop_scope_ok(scoped)
        if ev.get("dropped_no_backup"):
            gate.report["persist_drop_scope"] = {
                "evidence": drop_evidence, "summary": scoped_ok,
                "refs_intact": refs_intact,
                "baseline": {k: {"n_present": v.get("n_present"),
                                 "n_absent": v.get("n_absent"),
                                 "first_absent_index":
                                     v.get("first_absent_index"),
                                 "n_runs": v.get("n_runs"),
                                 "longest_run_len": v.get("longest_run_len")}
                             for k, v in baseline_by_target.items()},
                "now": {k: {"n_present": v.get("n_present"),
                            "n_absent": v.get("n_absent"),
                            "first_absent_index": v.get("first_absent_index"),
                            "n_runs": v.get("n_runs"),
                            "longest_run_len": v.get("longest_run_len")}
                        for k, v in (membership or {}).items()},
                "recheck": ({k: {"n_present": v.get("n_present"),
                                 "n_absent": v.get("n_absent"),
                                 "first_absent_index":
                                     v.get("first_absent_index"),
                                 "n_runs": v.get("n_runs"),
                                 "longest_run_len": v.get("longest_run_len")}
                             for k, v in recheck.items()}
                            if recheck else None),
                "filler_tokens_total": filler_tokens_total,
                "scoped_tail": scoped[-8:],
            }
        if not scoped_ok["ok"]:
            gate.report["persist_console_evidence"] = gc.slim_storage_events(ev)
            gate.invalidate(
                "graded-target (or unattributable) kv subtree dropped without "
                "backup due to host memory pressure "
                f"({scoped_ok['n_total']} event(s)) after "
                f"{filler_tokens_total} filler tokens: "
                f"target_roots={scoped_ok['target_roots']} "
                f"unknown_roots={scoped_ok['unknown_roots']} "
                f"(refs_intact={refs_intact}); only drops with a no-decrease "
                "delta proof against a COMPLETE full-window baseline, confirmed "
                "by the immediately-following re-snapshot, are disposable "
                "(the node-id ordering bound is not used)")
            return None
        gate.log(f"filler {i}: extent_write_bytes={written} "
                 f"wal_current={man.get('wal_current')} "
                 f"filler_tokens_total={filler_tokens_total} "
                 f"host_cycle_target={host_cycle_target}")
        if written <= 0:
            continue
        ok = _targets_in_index_ok(membership, min_present_by_target,
                                  min_present)
        # The target can only be in the extent index after it left L2, but a
        # page may briefly exist in both tiers.  Require one full host-pool of
        # UNRELATED filler traffic after the last target access so L2 eviction is
        # proven by volume, not inferred.
        host_cycle_done = filler_tokens_total >= host_cycle_target
        device_cycle_done = (filler_tokens_total
                             >= gc.HICACHE_DEVICE_POOL_TOKENS)
        if ok and host_cycle_done and device_cycle_done:
            evidence = {
                "ok": True,
                "fillers": records,
                "filler_tokens_total": filler_tokens_total,
                "extent_write_bytes": written,
                "extent_write_n": len(ev.get("extent_write", [])),
                "extent_recycle_n": gc.extent_recycle_count(ev),
                "reclaim_relocated_n": len(ev.get("reclaim_relocated", [])),
                "reclaim_refused_n": len(ev.get("reclaim_refused", [])),
                "dropped_no_backup_n": len(ev.get("dropped_no_backup", [])),
                "dropped_scope": scoped_ok,
                "drop_evidence": drop_evidence,
                "namespace_after": man,
                "membership": {k: {kk: v[kk] for kk in
                                   ("n_present", "n_absent",
                                    "first_absent_index", "query_window_len",
                                    "min_present_required")}
                               for k, v in membership.items()},
                "device_eviction_proof": {
                    "unrelated_tokens_written": filler_tokens_total,
                    "device_pool_tokens": gc.HICACHE_DEVICE_POOL_TOKENS,
                    "device_pool_overwritten":
                        filler_tokens_total >= gc.HICACHE_DEVICE_POOL_TOKENS,
                },
                "host_eviction_proof": {
                    "unrelated_tokens_written": filler_tokens_total,
                    "kv_host_tokens": kv_host_tokens,
                    "host_cycle_target": host_cycle_target,
                    "target_tokens": target_n,
                    "note": "unrelated filler tokens cycled through the host "
                            "pool after the target's write-back, evicting it "
                            "from L2 to the storage tier",
                },
                "console_evidence": gc.slim_storage_events(ev),
                "preconditions": {
                    "target_in_extent_index": ok,
                    "device_eviction_proven": device_cycle_done,
                    "host_eviction_proven": host_cycle_done,
                    "storage_candidate_hit": ok,
                    "no_target_drop_without_backup": scoped_ok["ok"],
                    "membership": {k: v["n_present"]
                                   for k, v in membership.items()},
                    "drop_scope": scoped_ok,
                },
            }
            gate.check("persist_extent_write_seen",
                       evidence["extent_write_n"] > 0, detail=written)
            gate.check("persist_namespace_grew",
                       bool(man.get("wal_current") is not None
                            or man.get("files")), detail=man.get("files"))
            gate.check("persist_target_in_extent_index",
                       ok, detail=evidence["membership"])
            gate.check("persist_device_eviction_proven", device_cycle_done,
                       detail=evidence["device_eviction_proof"])
            gate.check("persist_host_eviction_proven", host_cycle_done,
                       detail=evidence["host_eviction_proof"])
            # Computed, target-scoped verdict -- never the old decorative True.
            gate.check("persist_no_target_drop_without_backup",
                       scoped_ok["ok"],
                       detail={"scope": scoped_ok,
                               "events": evidence["dropped_no_backup_n"],
                               "filler_tokens_total": filler_tokens_total,
                               "max_target_node_id":
                                   drop_evidence.get("max_node_id")})
            gate.report["persist_console_evidence"] = gc.slim_storage_events(ev)
            return evidence
        gate.log(f"filler {i}: not yet complete: "
                 + ", ".join(f"{k}={m['n_present']}/{m['query_window_len']}"
                             for k, m in membership.items())
                 + f"; host_cycle_done={host_cycle_done} "
                   f"device_cycle_done={device_cycle_done}")
    membership = last_membership or {}
    return {
        "ok": False,
        "fillers": records, "filler_tokens_total": filler_tokens_total,
        "extent_write_bytes": gc.extent_write_bytes(ev),
        "dropped_no_backup_n": len(ev.get("dropped_no_backup", [])),
        "dropped_scope": gc.drop_scope_ok(ev.get("dropped_scopes") or []),
        "namespace_after": last_man,
        "membership": {k: {"n_present": v.get("n_present"),
                           "query_window_len": v.get("query_window_len")}
                       for k, v in membership.items()},
        "reason": (
            f"target not fully persisted to L3 / L2 eviction not proven after "
            f"{len(records)} unrelated filler(s) ({filler_tokens_total} tokens, "
            f"host_cycle_target={host_cycle_target}); preconditions (b)/(c)/"
            "(d)/(e) not established before the measured request"),
    }


def _membership_both(gate, args, namespace, suffix, targets, run_dir, rid, i):
    out = {}
    for name, (ids, ids_json) in targets.items():
        snap = str(run_dir / f"store-snapshot-persist-{name}-{rid}-{i}")
        try:
            mem, meta = gc.snapshot_and_membership(
                args.tree, namespace, suffix, snap,
                run_dir / f"wal-membership-persist-{name}-{rid}-{i}.json",
                ids_json, query_window_len=len(ids) - 1)
        except gc.GateInvalid as exc:
            gate.invalidate(f"offline membership [{name}] failed: {exc}")
            return None
        m = mem.get("membership") or {}
        head = mem.get("head") or {}
        m = dict(m)
        m["query_window_len"] = len(ids) - 1
        m["min_present_required"] = math.ceil(
            args.min_index_fraction * (len(ids) - 1))
        m["head_present_in_rebuilt_index"] = head.get(
            "head_present_in_rebuilt_index")
        m["snapshot"] = meta
        out[name] = m
    return out


def _finish(gate: gc.Gate) -> int:
    gate.report["gpu_compute_apps_after"] = gc.gpu_compute_apps()
    verdict, rc = gate.finish()
    gate.save("gate-a-result.json")
    gate.log(f"VERDICT={verdict} rc={rc}")
    return rc


def _ids_sig(got, want) -> dict:
    got = got or []
    want = want or []
    return {"got_n": len(got), "want_n": len(want),
            "got_head": got[:8], "want_head": want[:8],
            "equal": got == want}


def _filler_ids(i: int, n_tokens: int):
    import random
    rng = random.Random(90000 + i)
    # 16-bit-range token ids guaranteed inside any modern BPE vocab and
    # distinct per filler index; unrelated to the chat-rendered target prompts
    # so they allocate new pages instead of prefix-matching.
    return [rng.randrange(1000, 60000) for _ in range(n_tokens)]


if __name__ == "__main__":
    raise SystemExit(main())
