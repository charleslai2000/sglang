#!/usr/bin/env python3
"""F2 -- REAL restart recovery (genuine new process + new lock generation).

Structure (``--phase all`` runs both, each in its OWN process):
  primer  : acquire the canonical lock in THIS driver process, launch server
            #1 in a unique store namespace, write the chain, force WAL
            checkpoint rotations, prove a storage-tier restore, then SIGTERM
            server #1 *while still holding the lock* and prove (fresh-process
            lock probe) the lock survived the SIGTERM.  Releases the lock.
  recover : a NEW process re-acquires the lock (generation must advance, so it
            is a fresh lock lifecycle -- never an fd inherited from server #1),
            launches server #2 against the SAME namespace, and proves the post-
            restart store still restores from the storage tier with content
            equality.

The predecessor's defect (GATE4-CLOSURE H5) was a lock held only through the
launched server's inherited fd: SIGTERM released it and the relaunch ran
outside the lock into a VRAM collision.  Here the lock fd is owned by the
driver (O_CLOEXEC + close_fds on every child) and the restart is a new
process/lock generation; any deviation is reported INVALID.

Store policy: one unique namespace for the whole F2 run; never clear/flush any
store; the shared /data/l3/local-prod-v1.1 store is never touched.

Host-pool sizing: as in Gate A, the kv host pool is asserted (from the server's
own allocation line) to stage the graded chain + ``--host-pool-margin`` before
the primer's write-back, so the pre-restart storage restore is reachable; the
post-restart server asserts the same.  The extent store is a small pinned
disposable file (GC off), not the production 64 GiB default.

Exit codes: 0 PASS | 1 FAIL | 2 INVALID | 3 PENDING | 4 ERROR | 5 BLOCKED.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_common as gc  # noqa: E402

MARK = "GOLF-3R8T-55"
STATE = gc.RUN_DIR / "f2" / "f2-state.json"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all", "primer", "recover"],
                    default="all")
    ap.add_argument("--tree", default=gc.DEFAULT_TREE)
    ap.add_argument("--model", default=gc.DEFAULT_MODEL)
    ap.add_argument("--port", type=int, default=gc.DEFAULT_PORT)
    ap.add_argument("--hc-size", type=int, default=8)
    ap.add_argument("--chain-tokens", type=int, default=62000)
    ap.add_argument("--host-pool-margin", type=int, default=4096)
    ap.add_argument("--max-new", type=int, default=32)
    ap.add_argument("--filler-tokens", type=int, default=16000)
    ap.add_argument("--max-fillers", type=int, default=8)
    ap.add_argument("--extent-size", type=int, default=64 << 20)
    ap.add_argument("--file-size", type=int, default=0)
    ap.add_argument("--slots-margin", type=int, default=8)
    ap.add_argument("--min-index-fraction", type=float, default=0.99)
    ap.add_argument("--wal-checkpoint-bytes", type=int, default=16 << 20)
    ap.add_argument("--namespace", default=None)
    ap.add_argument("--reuse-namespace", action="store_true")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--lock-attempts", type=int, default=240)
    ap.add_argument("--lock-poll", type=int, default=15)
    ap.add_argument("--health-timeout", type=float, default=2400.0)
    return ap.parse_args()


def config_suffix(model: str) -> str:
    return f"_{'-'.join(model.split('/'))}_0_1"


PAGE_BYTES = 16384


def compute_geometry(args) -> dict:
    """Small disposable extent store for the F2 store (no wrap during F2)."""
    pages_per_slot = args.extent_size // PAGE_BYTES
    if pages_per_slot <= 0:
        raise gc.GateInvalid("extent_size smaller than one 16 KiB page")
    chain_slots = math.ceil(args.chain_tokens / pages_per_slot)
    filler_slots = math.ceil(args.filler_tokens / pages_per_slot)
    file_size = args.file_size or (
        (chain_slots + args.max_fillers * filler_slots + args.slots_margin)
        * args.extent_size)
    if file_size < args.extent_size or file_size % args.extent_size != 0:
        raise gc.GateInvalid(
            f"file_size {file_size} must be a positive multiple >= "
            f"extent_size {args.extent_size}")
    return {"extent_size": args.extent_size, "file_size": file_size,
            "num_slots": file_size // args.extent_size,
            "pages_per_slot": pages_per_slot, "chain_slots": chain_slots,
            "filler_slots": filler_slots}


def storage_env(args) -> tuple:
    geom = compute_geometry(args)
    return geom, {
        "SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE": str(geom["extent_size"]),
        "SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE": str(geom["file_size"]),
        "SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE": "0",
        "SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE": "0",
        "SGLANG_HICACHE_EXTENT_BACKEND_WAL_CHECKPOINT_BYTES":
            str(args.wal_checkpoint_bytes),
    }


# ------------------------------------------------------------------- controller
def run_all(args) -> int:
    base = _strip_phase(sys.argv[1:])
    run_dir = gc.RUN_DIR / "f2"
    run_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    rcs = {}
    for phase in ("primer", "recover"):
        cmd = [sys.executable, os.path.abspath(__file__)] + base + [
            "--phase", phase]
        gc.log(f"f2 controller: launching phase={phase}")
        proc = subprocess.run(cmd, cwd="/tmp")
        rcs[phase] = proc.returncode
        try:
            results[phase] = gc.read_json(
                run_dir / f"f2-{phase}-result.json")
        except Exception:  # noqa: BLE001
            results[phase] = None
        if phase == "primer" and proc.returncode != 0:
            gc.log(f"f2 controller: primer rc={proc.returncode}; not running recover")
            break
    if "recover" in rcs and rcs["primer"] == 0:
        combined_rc = rcs["recover"]
    else:
        combined_rc = rcs.get("primer", 4)
    verdict = {0: "PASS", 1: "FAIL", 2: "INVALID",
               3: "PENDING", 4: "ERROR", 5: "BLOCKED"}.get(combined_rc, "ERROR")
    combined = {"gate": "f2-combined", "verdict": verdict,
                "exit_code": combined_rc, "phase_exit_codes": rcs,
                "finished": time.time(),
                "phase_verdicts": {
                    k: (v or {}).get("verdict") for k, v in results.items()}}
    gc.write_json(run_dir / "f2-combined-result.json", combined)
    gc.log(f"f2 combined VERDICT={verdict} rc={combined_rc}")
    return combined_rc


def _strip_phase(argv):
    out = []
    skip = False
    for tok in argv:
        if skip:
            skip = False
            continue
        if tok == "--phase":
            skip = True
            continue
        if tok.startswith("--phase="):
            continue
        out.append(tok)
    return out


# ------------------------------------------------------------------- primer
def phase_primer(args) -> int:
    tag = "f2-primer"
    rid = args.run_id or gc.run_id(tag)
    run_dir = gc.RUN_DIR / "f2"
    gate = gc.Gate(tag, run_dir, extra={
        "tree": args.tree, "model": args.model, "port": args.port,
        "chain_tokens": args.chain_tokens,
        "wal_checkpoint_bytes": args.wal_checkpoint_bytes, "run_id": rid,
        "store_policy": {"shared_production_store": gc.PRODUCTION_STORE,
                         "clear_or_flush_called": False},
    })
    lock_fd = None
    proc = console = None
    state = {}
    try:
        gate.report["gpu_compute_apps_before"] = gc.gpu_compute_apps()
        gate.check("tree_present",
                   os.path.exists(os.path.join(args.tree, "src", "python",
                                               "sglang", "__init__.py")),
                   detail=args.tree)
        pf = gc.preflight_import(args.tree)
        gate.report["preflight_import"] = pf
        gate.check("preflight_sglang_file_in_tree", pf.get("ok"), detail=pf)
        suffix = config_suffix(args.model)
        prompt_json = run_dir / "prompt_A.json"
        info = gc.build_prompt(args.tree, args.model, MARK, args.chain_tokens,
                               prompt_json)
        ids_a = info["ids"]
        gate.report["prompt"] = {"marker": MARK, "n": len(ids_a)}
        gate.check("chain_ok", len(ids_a) >= 32000, detail=len(ids_a))
        geom, extra_env = storage_env(args)
        gate.report["geometry"] = geom
        gate.report["host_pool_sizing"] = gc.sizing_arithmetic(
            args.hc_size, len(ids_a), args.host_pool_margin)

        lock_fd = gc.acquire_lock(f"f2-primer-{rid}",
                                  max_attempts=args.lock_attempts,
                                  poll_s=args.lock_poll)
        if lock_fd is None:
            gate.pending("canonical GPU lock not acquired within bounded window")
            return _finish(gate, tag)
        lock_rec = gc.read_json(gc.LOCK_PATH) if os.path.exists(gc.LOCK_PATH) else {}
        state["lock_generation_primer"] = lock_rec.get("generation")
        state["primer_pid"] = os.getpid()
        gate.check("lock_generation_recorded",
                   isinstance(state["lock_generation_primer"], int),
                   detail=state["lock_generation_primer"])
        gate.check("port_free_before_launch", gc.port_free(args.port),
                   detail=args.port)
        if not gc.port_free(args.port):
            gate.invalidate(f"port {args.port} busy after lock acquisition")
            return _finish(gate, tag)

        namespace = args.namespace or gc.resolve_namespace(
            gc.L3_ROOT, "f2", rid, reuse=args.reuse_namespace)
        state["namespace"] = namespace
        state["suffix"] = suffix
        state["run_dir"] = str(run_dir)
        state["prompt_json"] = str(prompt_json)

        metrics_dir = run_dir / "metrics_s1"
        console_path = run_dir / "server.console.s1.log"
        proc, console, _ = gc.launch_server(
            args.tree, args.model, args.port, namespace, console_path,
            metrics_dir, hc_size_gb=args.hc_size, extra_env=extra_env)
        state["server1_pid"] = proc.pid
        state["server1_starttime"] = gc.proc_starttime(proc.pid)
        gate.log(f"launched server s1 pid={proc.pid}")
        health = gc.wait_health(args.port, proc, args.health_timeout)
        gate.check("server_s1_healthy", health.get("ok"), detail=health)
        gate.check("server_s1_not_inheriting_lock",
                   not gc.proc_holds_lock(proc.pid))
        if not health.get("ok"):
            gate.invalidate(f"server s1 unhealthy: {health}")
            return _finish(gate, tag)
        lp = gc.lock_probe()
        gate.check("lock_held_while_s1_runs", lp.get("locked") is True,
                   detail=lp)
        env = gc.proc_env(proc.pid)
        gate.check("server_s1_pythonpath",
                   env.get("PYTHONPATH") == os.path.join(args.tree, "src", "python"),
                   detail=env.get("PYTHONPATH"))
        hp = gc.parse_host_pool(console_path, prompt_tokens=len(ids_a),
                                host_pool_margin=args.host_pool_margin)
        gate.report["host_pool_actual_s1"] = hp
        gate.check("host_pool_stages_graded_chain_s1", hp.get("ok"),
                   detail={"kv_tokens": hp.get("kv_tokens"),
                           "required_kv_host_tokens":
                               hp.get("required_kv_host_tokens")})
        if not hp.get("ok"):
            gate.invalidate(
                "kv host pool does not stage the graded chain "
                f"(kv_tokens={hp.get('kv_tokens')} < required="
                f"{hp.get('required_kv_host_tokens')}): write-back can only be "
                "dropped without backup -> storage tier unreachable")
            return _finish(gate, tag)

        ident0 = _identity_retry(gate, args, namespace, suffix,
                                 run_dir / "wal-identity-initial.json")
        state["wal_identity_initial"] = ident0
        gate.report["wal_identity_initial"] = ident0
        gate.check("initial_manifest_present",
                   ident0.get("manifest_state") is not None)

        # ---- device reference -------------------------------------------
        off = gc.console_size(console_path)
        gc.generate(args.port, ids_a, 1)
        dev_a = gc.generate(args.port, ids_a, args.max_new)
        gate.report["DEVICE_A"] = _resp_slim(dev_a)
        gc.ensure_ok(gate, dev_a, "DEVICE_A")
        gate.check("device_A_ok", dev_a["ok"] and bool(dev_a["output_ids"]),
                   detail=dev_a.get("error"))
        state["device_ids"] = dev_a["output_ids"]

        # ---- write-back + checkpoint rotations --------------------------
        initial_current = int(ident0.get("wal_current") or 0)
        initial_manifest_bytes = int(ident0.get("manifest_bytes") or 0)
        pre_restart_probe = None
        rotations = 0
        for i in range(args.max_fillers):
            gc.generate(args.port, _filler_ids(i, args.filler_tokens), 1)
            probe = gc.generate(args.port, ids_a, args.max_new)
            man = gc.namespace_manifest(namespace, suffix)
            rotations = (int(man.get("wal_current") or 0) - initial_current)
            if probe["tier"]["storage"] > 0 and rotations > 1:
                pre_restart_probe = probe
                break
        if pre_restart_probe is None:
            pre_restart_probe = gc.generate(args.port, ids_a, args.max_new)
        man = gc.namespace_manifest(namespace, suffix)
        rotations = max(rotations,
                        int(man.get("wal_current") or 0) - initial_current)
        gate.report["pre_restart_probe"] = _resp_slim(pre_restart_probe)
        gc.ensure_ok(gate, pre_restart_probe, "pre_restart_probe")
        gate.check("pre_restart_storage_positive",
                   pre_restart_probe["tier"]["storage"] > 0,
                   detail=pre_restart_probe["tier"])
        gate.check("rotation_count_gt_1", rotations > 1, detail=rotations)
        state["pre_restart_ids"] = pre_restart_probe["output_ids"]

        # ---- L3 persistence + index proof (preconditions for F2) --------
        ev = gc.parse_storage_events(gc.read_new_lines(console_path, off))
        gate.report["primer_console_evidence"] = gc.slim_storage_events(ev)
        gate.check("primer_no_drop_without_backup",
                   not ev.get("dropped_no_backup"),
                   detail={"events": len(ev.get("dropped_no_backup", []))})
        if ev.get("dropped_no_backup"):
            gate.invalidate(
                "kv subtree dropped without backup due to host memory pressure "
                "during the F2 primer; host pool mis-sized for the chain")
            return _finish(gate, tag)
        snap = str(run_dir / f"store-snapshot-primer-{rid}")
        min_present = math.ceil(args.min_index_fraction * (len(ids_a) - 1))
        try:
            mem, snap_meta = gc.snapshot_and_membership(
                args.tree, namespace, suffix, snap,
                run_dir / f"wal-membership-primer-{rid}.json", str(prompt_json),
                query_window_len=len(ids_a) - 1)
        except gc.GateInvalid as exc:
            gate.invalidate(f"offline membership [f2-primer] failed: {exc}")
            return _finish(gate, tag)
        pm = mem.get("membership") or {}
        gate.report["primer_membership"] = {
            "n_present": pm.get("n_present"), "required": min_present,
            "first_absent_index": pm.get("first_absent_index"),
            "predicate": mem.get("predicate"),
            "snapshot": snap_meta,
        }
        gate.check("primer_target_in_extent_index",
                   (pm.get("n_present") or 0) >= min_present,
                   detail={"n_present": pm.get("n_present"),
                           "required": min_present})
        if not gate.checks["primer_target_in_extent_index"]["ok"]:
            gate.invalidate(
                "chain not fully written back to the extent index before the "
                "restart; the post-restart storage restore cannot be attributed")
            return _finish(gate, tag)

        if not gate.checks["rotation_count_gt_1"]["ok"]:
            gate.invalidate(
                f"WAL checkpoint rotation not observed (rotation_count={rotations}"
                f"<=1); restart-recovery precondition not established")

        ident1 = _identity_retry(gate, args, namespace, suffix,
                                 run_dir / "wal-identity-pre-restart.json")
        state["wal_identity_pre_restart"] = ident1
        gate.report["wal_identity_pre_restart"] = ident1
        st1 = ident1.get("manifest_state") or {}
        gate.check("wal_floor_advanced_pre",
                   int(st1.get("wal_floor") or 0) > 0
                   or int(ident1.get("wal_current") or 0) > initial_current,
                   detail={"wal_floor": st1.get("wal_floor"),
                           "wal_current": ident1.get("wal_current"),
                           "initial_current": initial_current})
        gate.check("manifest_grew_pre",
                   int(ident1.get("manifest_bytes") or 0) > initial_manifest_bytes,
                   detail={"before": initial_manifest_bytes,
                           "after": ident1.get("manifest_bytes")})
        if not gate.checks["wal_floor_advanced_pre"]["ok"]:
            gate.invalidate("wal_floor did not advance before restart")
        if not gate.checks["manifest_grew_pre"]["ok"]:
            gate.invalidate("manifest did not grow before restart")
        state["initial_current"] = initial_current
        state["rotation_count"] = rotations

        # ---- hold the lock across SIGTERM, then release -----------------
        s1_pid = proc.pid
        stop1 = gc.stop_server(proc, console)
        proc = console = None
        gate.report["stop_s1"] = stop1
        gate.check("server_s1_exited", stop1.get("stopped") is True, detail=stop1)
        gate.check("server_s1_process_gone", gc.wait_proc_gone(s1_pid, 180),
                   detail=s1_pid)
        lp2 = gc.lock_probe()
        gate.check("lock_held_after_sigterm", lp2.get("locked") is True,
                   detail=lp2)
        gate.check("port_free_after_stop", gc.wait_port_free(args.port, 300),
                   detail=args.port)
        state["lock_held_after_sigterm"] = lp2.get("locked")
        gc.write_json(STATE, state)
        gate.report["state_file"] = str(STATE)
        gate.log(f"primer complete; state written to {STATE}")
        return _finish(gate, tag)
    except gc.GateBlocked as exc:
        gate.blocked(str(exc))
        return _finish(gate, tag)
    except gc.GateInvalid as exc:
        gate.invalidate(str(exc))
        return _finish(gate, tag)
    except Exception as exc:  # noqa: BLE001
        gate.error(exc, traceback.format_exc())
        return _finish(gate, tag)
    finally:
        try:
            if proc is not None:
                gc.stop_server(proc, console)
        except Exception:  # noqa: BLE001
            pass
        gc.release_lock(lock_fd)


# ------------------------------------------------------------------- recover
def phase_recover(args) -> int:
    tag = "f2-recover"
    run_dir = gc.RUN_DIR / "f2"
    gate = gc.Gate(tag, run_dir, extra={
        "tree": args.tree, "model": args.model, "port": args.port,
        "wal_checkpoint_bytes": args.wal_checkpoint_bytes,
        "store_policy": {"shared_production_store": gc.PRODUCTION_STORE,
                         "clear_or_flush_called": False},
    })
    lock_fd = None
    proc = console = None
    try:
        gate.report["gpu_compute_apps_before"] = gc.gpu_compute_apps()
        if not STATE.exists():
            gate.blocked(f"primer state missing: {STATE}")
            return _finish(gate, tag)
        state = gc.read_json(STATE)
        gate.report["primer_state"] = {
            k: v for k, v in state.items()
            if k not in ("device_ids", "pre_restart_ids")}
        namespace = state["namespace"]
        suffix = state["suffix"]
        prompt_json = state["prompt_json"]
        ids_a = gc.read_json(prompt_json)["ids"]
        gate.check("tree_present",
                   os.path.exists(os.path.join(args.tree, "src", "python",
                                               "sglang", "__init__.py")),
                   detail=args.tree)
        pf = gc.preflight_import(args.tree)
        gate.report["preflight_import"] = pf
        gate.check("preflight_sglang_file_in_tree", pf.get("ok"), detail=pf)
        gate.check("primer_server1_gone",
                   not os.path.exists(f"/proc/{state['server1_pid']}"),
                   detail=state["server1_pid"])

        lock_fd = gc.acquire_lock(f"f2-recover-{os.getpid()}",
                                  max_attempts=args.lock_attempts,
                                  poll_s=args.lock_poll)
        if lock_fd is None:
            gate.pending("canonical GPU lock not acquired within bounded window")
            return _finish(gate, tag)
        lock_rec = gc.read_json(gc.LOCK_PATH) if os.path.exists(gc.LOCK_PATH) else {}
        lock_gen = lock_rec.get("generation")
        gate.report["lock_generation_recover"] = lock_gen
        gate.check("new_lock_generation",
                   isinstance(lock_gen, int)
                   and int(lock_gen) > int(state.get("lock_generation_primer") or 0),
                   detail={"primer": state.get("lock_generation_primer"),
                           "recover": lock_gen})
        gate.check("new_recover_process",
                   os.getpid() != int(state.get("primer_pid") or -1),
                   detail=os.getpid())
        gate.check("port_free_before_relaunch", gc.port_free(args.port),
                   detail=args.port)
        if not gc.port_free(args.port):
            gate.invalidate(f"port {args.port} busy before relaunch")
            return _finish(gate, tag)

        metrics_dir = run_dir / "metrics_s2"
        console_path = run_dir / "server.console.s2.log"
        geom, extra_env = storage_env(args)
        gate.report["geometry"] = geom
        gate.report["host_pool_sizing"] = gc.sizing_arithmetic(
            args.hc_size, len(ids_a), args.host_pool_margin)
        proc, console, _ = gc.launch_server(
            args.tree, args.model, args.port, namespace, console_path,
            metrics_dir, hc_size_gb=args.hc_size, extra_env=extra_env)
        gate.log(f"relaunched server s2 pid={proc.pid}")
        health = gc.wait_health(args.port, proc, args.health_timeout)
        gate.check("server_s2_healthy", health.get("ok"), detail=health)
        gate.check("server_s2_new_process",
                   proc.pid != int(state.get("server1_pid") or -1)
                   and gc.proc_starttime(proc.pid)
                   != state.get("server1_starttime"),
                   detail={"s1": state.get("server1_pid"),
                           "s2": proc.pid})
        gate.check("server_s2_not_inheriting_lock",
                   not gc.proc_holds_lock(proc.pid))
        if not health.get("ok"):
            gate.invalidate(f"server s2 unhealthy: {health}")
            return _finish(gate, tag)
        lp = gc.lock_probe()
        gate.check("lock_held_while_s2_runs", lp.get("locked") is True,
                   detail=lp)
        env = gc.proc_env(proc.pid)
        gate.check("server_s2_pythonpath",
                   env.get("PYTHONPATH") == os.path.join(args.tree, "src", "python"),
                   detail=env.get("PYTHONPATH"))
        kg = gc.kv_dtype_gate(console_path)
        gate.check("kv_dtype_gate_s2", kg.get("ok"), detail=kg)
        hp = gc.parse_host_pool(console_path, prompt_tokens=len(ids_a),
                                host_pool_margin=args.host_pool_margin)
        gate.report["host_pool_actual_s2"] = hp
        gate.check("host_pool_stages_graded_chain_s2", hp.get("ok"),
                   detail={"kv_tokens": hp.get("kv_tokens"),
                           "required_kv_host_tokens":
                               hp.get("required_kv_host_tokens")})
        if not hp.get("ok"):
            gate.invalidate(
                "restarted server's kv host pool does not stage the graded "
                f"chain (kv_tokens={hp.get('kv_tokens')}); post-restart restore "
                "cannot be attributed")
            return _finish(gate, tag)

        # ---- post-restart restore + content equality --------------------
        post = gc.generate(args.port, ids_a, args.max_new)
        gate.report["POST_RESTART_A"] = _resp_slim(post)
        gc.ensure_ok(gate, post, "POST_RESTART_A")
        gate.check("post_restart_ok", post["ok"] and bool(post["output_ids"]),
                   detail=post.get("error"))
        gate.check("post_restart_storage_positive",
                   post["tier"]["storage"] > 0, detail=post["tier"])
        gate.check("post_restart_device_miss",
                   int(post["tier"]["device"] or 0) == 0, detail=post["tier"])
        gate.check("post_restart_content_equal",
                   post["output_ids"] == state.get("device_ids"),
                   detail=_ids_sig(post["output_ids"], state.get("device_ids")))

        ident2 = _identity_retry(gate, args, namespace, suffix,
                                 run_dir / "wal-identity-post-restart.json")
        gate.report["wal_identity_post_restart"] = ident2
        st2 = ident2.get("manifest_state") or {}
        gate.check("rotation_count_gt_1_final",
                   int(state.get("rotation_count") or 0) > 1,
                   detail=state.get("rotation_count"))
        gate.check("wal_floor_advanced_final",
                   int(st2.get("wal_floor") or 0) > 0,
                   detail=st2.get("wal_floor"))
        gate.check("manifest_grew_final",
                   int(ident2.get("manifest_bytes") or 0)
                   > int((state.get("wal_identity_initial") or {}).get(
                       "manifest_bytes") or 0),
                   detail={"initial": (state.get("wal_identity_initial") or {}
                                       ).get("manifest_bytes"),
                           "final": ident2.get("manifest_bytes")})
        uuid1 = (state.get("wal_identity_pre_restart") or {}).get(
            "manifest_state", {}).get("file_uuid")
        uuid2 = st2.get("file_uuid")
        gate.check("post_restart_same_store",
                   bool(uuid1) and uuid1 == uuid2,
                   detail={"pre": uuid1, "post": uuid2})
        if not gate.checks["post_restart_same_store"]["ok"]:
            gate.invalidate(
                "post-restart manifest file_uuid differs from pre-restart; "
                "server #2 did not recover the same store")

        storage_proven = (post["tier"]["storage"] > 0
                          and int(post["tier"]["device"] or 0) == 0)
        content_equal = post["output_ids"] == state.get("device_ids")
        gate.report["storage_tier_proof_fields"] = [
            "cached_tokens_details.storage > 0 (primary)",
            "cached_tokens_details.device == 0 (restore origin)",
            "pre-restart offline Extent-index membership of the same namespace",
            "post-restart identity: wal_current/wal_floor/manifest_bytes/"
            "file_uuid",
        ]
        gate.check("lock_survived_sigterm_primer",
                   bool(state.get("lock_held_after_sigterm")) is True,
                   detail=state.get("lock_held_after_sigterm"))
        restart_genuine = all(
            gate.checks.get(n, {}).get("ok") for n in
            ("new_lock_generation", "new_recover_process", "server_s2_new_process",
             "server_s2_not_inheriting_lock", "lock_held_while_s2_runs",
             "lock_survived_sigterm_primer"))
        gate.report["storage_tier_proof"] = {
            "fields": [
                "cached_tokens_details.storage > 0 (primary)",
                "hicache_telemetry.l3_tokens (corroborating)",
                "post-restart identity: wal_current/wal_floor/manifest_bytes",
            ],
            "POST_RESTART_A": post["tier"],
        }
        if not restart_genuine:
            gate.invalidate(
                "restart was not a genuine new process + new lock generation "
                "(lock fd inheritance / same process) -> result INVALID")
        elif not storage_proven:
            gate.invalidate(
                "post-restart store did not restore from the storage tier -> "
                "INVALID, not PASS")
        elif not content_equal:
            gate.fail("post-restart content mismatch under a confirmed "
                      "storage-tier restore -> production blocker")
        else:
            gate.log("F2 observed: genuine restart, rotations advanced, "
                     "post-restart storage-tier restore with content equality")
        return _finish(gate, tag)
    except gc.GateBlocked as exc:
        gate.blocked(str(exc))
        return _finish(gate, tag)
    except gc.GateInvalid as exc:
        gate.invalidate(str(exc))
        return _finish(gate, tag)
    except Exception as exc:  # noqa: BLE001
        gate.error(exc, traceback.format_exc())
        return _finish(gate, tag)
    finally:
        try:
            if proc is not None:
                gc.stop_server(proc, console)
        except Exception:  # noqa: BLE001
            pass
        gc.release_lock(lock_fd)


# ------------------------------------------------------------------- helpers
def _identity_retry(gate, args, namespace, suffix, out_path, attempts=6):
    last = None
    for _ in range(attempts):
        try:
            return gc.wal_forensics(args.tree, namespace, suffix, "identity",
                                    out_path)
        except gc.GateInvalid as exc:
            last = exc
            time.sleep(3)
    gate.invalidate(f"wal_forensics identity failed: {last}")
    return {"manifest_state": None}


def _resp_slim(resp) -> dict:
    return {"ok": resp.get("ok"), "error": resp.get("error"),
            "seconds": resp.get("seconds"), "tier": resp.get("tier"),
            "n_ids": len(resp.get("output_ids") or [])}


def _ids_sig(got, want) -> dict:
    got, want = got or [], want or []
    return {"got_n": len(got), "want_n": len(want), "equal": got == want,
            "got_head": got[:8], "want_head": want[:8]}


def _filler_ids(i: int, n_tokens: int):
    rng = random.Random(70000 + i)
    return [rng.randrange(1000, 60000) for _ in range(n_tokens)]


def _finish(gate: gc.Gate, tag: str) -> int:
    gate.report["gpu_compute_apps_after"] = gc.gpu_compute_apps()
    verdict, rc = gate.finish()
    gate.save(f"{tag}-result.json")
    gate.log(f"VERDICT={verdict} rc={rc}")
    return rc


def main() -> int:
    args = parse_args()
    if args.phase == "all":
        return run_all(args)
    if args.phase == "primer":
        return phase_primer(args)
    return phase_recover(args)


if __name__ == "__main__":
    raise SystemExit(main())
