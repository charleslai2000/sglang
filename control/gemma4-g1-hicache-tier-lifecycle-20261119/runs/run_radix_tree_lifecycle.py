#!/usr/bin/env python3
"""Run a deterministic tree, Host-source probes, then cold L3 restores."""

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def http_json(url, path, timeout=30):
    with urllib.request.urlopen(url + path, timeout=timeout) as response:
        return json.loads(response.read())


def metrics(url):
    try:
        with urllib.request.urlopen(url + "/metrics", timeout=10) as response:
            return response.read().decode()
    except Exception as exc:
        return f"METRICS_ERROR {type(exc).__name__}: {exc}\n"


def extent_files(extent_dir):
    directory = Path(extent_dir)
    paths = sorted(directory.glob("hicache.data*")) + sorted(directory.glob("*.wal*"))
    return {
        str(path): {
            "size_bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in paths
        if path.is_file()
    }


def snapshot(url, out, label, extent_dir):
    result = {
        "label": label,
        "epoch_s": time.time(),
        "extent_files": extent_files(extent_dir),
        "tree_shape": {"root_tokens": 16384, "branch_tokens": 16384, "leaf_tokens": 32768},
    }
    for key, path in (
        ("server_info", "/server_info"),
        ("storage_backend", "/hicache/storage-backend"),
    ):
        try:
            result[key] = http_json(url, path)
        except Exception as exc:
            result[key + "_error"] = f"{type(exc).__name__}: {exc}"
    metrics_text = metrics(url)
    metrics_path = out / f"{label}.metrics.txt"
    metrics_path.write_text(metrics_text)
    result["pool_capacities"] = read_pool_capacities(metrics_text)
    result["tier_transfer_counters"] = read_tier_transfer_counters(metrics_text)
    result["metrics_path"] = metrics_path.name
    result["extent_directory"] = str(extent_dir)
    (out / f"{label}.snapshot.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def read_prometheus(metrics_text, name):
    matches = read_prometheus_series(metrics_text, name)
    return next(iter(matches.values()), None) if len(matches) == 1 else None


def read_pool_capacities(metrics_text):
    names = (
        "sglang:max_total_num_tokens",
        "sglang:max_total_num_tokens_swa",
        "sglang:hicache_host_total_tokens",
        "sglang:hicache_host_used_tokens",
        "sglang:hicache_kv_pool_tokens",
        "sglang:hicache_kv_host_usable_tokens",
        "sglang:hicache_usable_tokens",
    )
    return {name: read_prometheus(metrics_text, name) for name in names}


def read_tier_transfer_counters(metrics_text):
    names = (
        "sglang:prefetched_tokens_total",
        "sglang:backuped_tokens_total",
        "sglang:load_back_tokens_total",
        "sglang:hicache_backup_tokens_total",
        "sglang:load_back_bytes_total",
        "sglang:hicache_backup_bytes_total",
    )
    return {name: read_prometheus_series(metrics_text, name) for name in names}


def read_prometheus_series(metrics_text, name):
    values = {}
    for line in metrics_text.splitlines():
        if line.startswith(name + "{"):
            label_part, _, value_part = line.partition(" ")
            try:
                values[label_part] = float(value_part)
            except ValueError:
                continue
        elif line.startswith(name + " "):
            try:
                values["unlabeled"] = float(line.rsplit(None, 1)[-1])
            except ValueError:
                continue
    return values


def read_host_pool_allocations(server_log):
    try:
        text = Path(server_log).read_text(errors="replace")
    except OSError as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    pools = {}
    for match in re.finditer(
        r"Allocating (full|swa) hierarchical KV host pool: (\d+) tokens, ([0-9.]+) GB host memory",
        text,
        re.IGNORECASE,
    ):
        pools[match.group(1).lower()] = {
            "tokens": int(match.group(2)),
            "host_memory_gb": float(match.group(3)),
        }
    return {
        "available": set(pools) == {"full", "swa"},
        "pools": pools,
        "source": "runtime allocation log; distinct Full/SWA host pools",
    }


def post(url, path, payload, timeout):
    request = urllib.request.Request(
        url + path,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def flush_radix_cache(url, timeout):
    request = urllib.request.Request(
        url + "/flush_cache?timeout=120",
        data=b"",
        headers={"Content-Length": "0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 130) as response:
            body = response.read().decode(errors="replace")
            return {
                "status": response.status,
                "body": body,
                "success": "cache flushed." in body.lower(),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "body": exc.read().decode(errors="replace"),
            "success": False,
        }


def positive_counter(line, name):
    match = re.search(rf"(?:^|\s){name}=(\d+)(?:\s|$)", line)
    return int(match.group(1)) if match else 0


def field_value(line, name):
    match = re.search(rf"(?:^|\s){name}=([^\s]+)", line)
    return match.group(1) if match else None


def source_restore_qualified(record, source, output_tokens):
    if (
        not record.get("ok")
        or record.get("completion_tokens") != output_tokens
        or record.get("output_token_ids_count") != output_tokens
    ):
        return False
    details = record.get("cached_tokens_details") or {}
    d, h, s = (int(details.get(key, 0) or 0) for key in ("device", "host", "storage"))
    evidence = record.get("restore_evidence", {})
    ready_events = evidence.get("ready_events", [])
    accepted_ready = any(
        f"rid={record.get('rid')} " in line and "finalize_result=accepted" in line
        for line in ready_events
    )
    accepted_restore = (not ready_events or accepted_ready) and any(
        f"rid={record.get('rid')} " in line
        and "disposition=RESTORE" in line
        and positive_counter(line, "requested") > 0
        and positive_counter(line, "granted") == positive_counter(line, "requested")
        for line in evidence.get("restore_events", [])
    )
    extent_read = any(
        positive_counter(line, "physical_bytes") > 0
        and positive_counter(line, "succeeded_keys") > 0
        for line in evidence.get("extent_reads", [])
    )
    return {
        "l1": d > 0 and h == 0 and s == 0,
        # The prompt may retain a common ancestor in L1 while its target
        # branch-exclusive suffix is restored from a lower tier. Aggregate
        # cached_tokens_details is therefore a presence/source test, not a
        # requirement that unrelated ancestor tokens be absent from Device.
        "l2": h > 0 and s == 0 and accepted_ready,
        "l3": s > 0 and extent_read and accepted_restore,
        "mixed": h > 0 and s > 0 and extent_read and accepted_restore,
    }[source]


def frontier_recovery_qualified(record, output_tokens):
    evidence = record.get("restore_evidence", {})
    frontier_waits = evidence.get("frontier_wait_events", [])
    frontier_wakes = evidence.get("frontier_wake_events", [])
    frontier_retries = evidence.get("retry_events", [])
    ready_indices = evidence.get("ready_line_indices", [])
    if frontier_waits and frontier_wakes and frontier_retries and ready_indices:
        wait_index = frontier_waits[-1]["line_index"]
        wake_index = next(
            (event["line_index"] for event in frontier_wakes if event["line_index"] > wait_index),
            None,
        )
        retry_index = next(
            (event["line_index"] for event in frontier_retries if wake_index is not None and event["line_index"] > wake_index),
            None,
        )
        ready_index = next(
            (index for index in ready_indices if retry_index is not None and index > retry_index),
            None,
        )
        same_frontier_wait_wake = bool(
            set(evidence.get("frontier_wait_ids", []))
            & set(evidence.get("frontier_wake_ids", []))
        )
        if (
            ready_index is not None
            and same_frontier_wait_wake
            and record.get("ok")
            and record.get("completion_tokens") == output_tokens
            and record.get("output_token_ids_count") == output_tokens
            and record.get("cached_tokens_details")
        ):
            return True
    for wake in evidence.get("wake_events", []):
        if not (
            wake.get("retry_grant") is True
            and wake.get("decision") == "grant"
            and wake.get("event_id")
            and wake.get("wait_id")
        ):
            continue
        matched_wait = any(
            wait.get("wait_id") == wake.get("wait_id")
            and wait.get("state") == "WAIT_CAPACITY"
            for wait in evidence.get("wait_events", [])
        )
        matched_ready = any(
            f"rid={record.get('rid')} " in ready
            and f"wait_id={wake.get('wait_id')} " in ready
            and f"wake_event_id={wake.get('event_id')} " in ready
            and "finalize_result=accepted" in ready
            for ready in evidence.get("ready_events", [])
        )
        if (
            matched_wait
            and matched_ready
            and any(
                f"rid={record.get('rid')} " in retry
                and "cause=frontier" in retry
                and field_value(retry, "attempt_id") == wake.get("attempt_id")
                for retry in evidence.get("retry_events", [])
            )
            and record.get("ok")
            and record.get("completion_tokens") == output_tokens
            and record.get("output_token_ids_count") == output_tokens
        ):
            return True
    return False


def validate_radix_events(lifecycle_events):
    if not isinstance(lifecycle_events, list):
        raise ValueError("RADIX_TRACE_SCHEMA_INVALID")
    for event in lifecycle_events:
        if not isinstance(event, dict) or not isinstance(event.get("operation"), str):
            raise ValueError("RADIX_TRACE_EVENT_SCHEMA_INVALID")
    operations = {event["operation"] for event in lifecycle_events}
    required = {"split_new_prefix", "split_old_child", "backup_commit"}
    missing = sorted(required - operations)
    if missing:
        raise ValueError(f"RADIX_LIFECYCLE_COVERAGE_MISSING:{missing}")
    if not any(event.get("operation") == "backup_commit" and event.get("full_host_after") is True for event in lifecycle_events):
        raise ValueError("RADIX_BACKUP_COMMIT_NOT_ACCEPTED")


def parse_restore_log(server_log, request_ids):
    wanted = set(request_ids)
    events = {rid: [] for rid in wanted}
    try:
        with Path(server_log).open(errors="replace") as stream:
            for line in stream:
                if "[HAE] " in line:
                    try:
                        event = json.loads(line.split("[HAE] ", 1)[1])
                    except (ValueError, TypeError):
                        event = None
                    rid = str(event.get("rid")) if isinstance(event, dict) else None
                    if rid in wanted:
                        events[rid].append(("hae", event, line.rstrip()))
                    continue
                if "rid=" not in line:
                    continue
                rid = next((candidate for candidate in wanted if f"rid={candidate} " in line), None)
                if rid is not None:
                    events[rid].append(("line", None, line.rstrip()))
    except OSError as exc:
        return {rid: {"log_available": False, "error": str(exc), "events": []} for rid in wanted}
    result = {}
    for rid, records in events.items():
        lines = [line for _, _, line in records]
        indexed_lines = [(index, line) for index, line in enumerate(lines)]
        hae = [event for kind, event, _ in records if kind == "hae"]
        waits = [
            event for event in hae
            if event.get("evt") == "restore_host_alloc_wait"
            and event.get("state") == "WAIT_CAPACITY"
        ]
        wake_decisions = [
            event for event in hae
            if event.get("evt") == "restore_host_alloc_wake_decision"
            and event.get("decision") == "grant"
            and event.get("retry_grant") is True
        ]
        frontier_wait_ids = {
            field_value(line, "wait_id")
            for _, line in indexed_lines
            if "evt=frontier_wait" in line and f"rid={rid} " in line
        }
        frontier_wake_ids = {
            field_value(line, "wait_id")
            for _, line in indexed_lines
            if "evt=frontier_wake" in line and f"rid={rid} " in line
        }
        frontier_waits = [
            {"line_index": index, "line": line}
            for index, line in indexed_lines
            if "evt=frontier_wait" in line and f"rid={rid} " in line
        ]
        frontier_wakes = [
            {"line_index": index, "line": line}
            for index, line in indexed_lines
            if "evt=frontier_wake" in line and f"rid={rid} " in line
        ]
        retries = [
            line for line in lines
            if "evt=restore_retry" in line
            and ("cause=frontier" in line or "cause=capacity" in line)
        ]
        result[rid] = {
            "log_available": True,
            "extent_reads": [line for line in lines if "evt=extent_read" in line],
            "restore_events": [
                line for line in lines
                if ("evt=restore_disposition" in line and "disposition=RESTORE" in line)
                or ("evt=restore_hybrid_finalize" in line and "result=accepted" in line)
            ],
            "host_alloc_events": hae,
            "wait_events": waits,
            "wake_events": wake_decisions,
            "frontier_wait_events": frontier_waits,
            "frontier_wake_events": frontier_wakes,
            "frontier_wait_ids": sorted(value for value in frontier_wait_ids if value),
            "frontier_wake_ids": sorted(value for value in frontier_wake_ids if value),
            "retry_events": [
                {"line_index": index, "line": line}
                for index, line in indexed_lines
                if "evt=restore_retry" in line and ("cause=frontier" in line or "cause=capacity" in line)
            ],
            "ready_events": [line for line in lines if "evt=ready_host" in line and "finalize_result=accepted" in line],
            "ready_line_indices": [
                index for index, line in indexed_lines
                if "evt=ready_host" in line and "finalize_result=accepted" in line
            ],
        }
    return result


def run_one(url, row, rid, phase, new_tokens, timeout):
    payload = {
        "rid": rid,
        "input_ids": [row["input_ids"]],
        "sampling_params": {
            "temperature": 0,
            "top_p": 1,
            "max_new_tokens": new_tokens,
            "min_new_tokens": new_tokens,
            "ignore_eos": True,
        },
        "return_cached_tokens_details": True,
        "return_token_ids": True,
    }
    started = time.time()
    tick = time.perf_counter()
    try:
        result = post(url, "/generate", payload, timeout)
        if isinstance(result, list):
            result = result[0]
        meta = result.get("meta_info", {})
        output_ids = result.get("output_ids", [])
        completion = int(meta.get("completion_tokens", len(output_ids)))
        return {
            "rid": rid,
            "phase": phase,
            "source_fixture_rid": row["rid"],
            "branch_id": row["branch_id"],
            "prompt_sha256": row["sha256"],
            "prompt_tokens": meta.get("prompt_tokens", len(row["input_ids"])),
            "started_epoch_s": started,
            "elapsed_s": time.perf_counter() - tick,
            "completion_tokens": completion,
            "output_token_ids_count": len(output_ids),
            "output_ids": output_ids,
            "cached_tokens": meta.get("cached_tokens"),
            "cached_tokens_details": meta.get("cached_tokens_details"),
            "hicache_telemetry": meta.get("hicache_telemetry"),
            "finish_reason": meta.get("finish_reason"),
            "meta_info": meta,
            "ok": completion == new_tokens and len(output_ids) == new_tokens,
        }
    except Exception as exc:
        return {
            "rid": rid,
            "phase": phase,
            "source_fixture_rid": row["rid"],
            "branch_id": row["branch_id"],
            "prompt_sha256": row["sha256"],
            "started_epoch_s": started,
            "elapsed_s": time.perf_counter() - tick,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_parallel(url, rows, indices, phase, tokens, timeout, out, workers):
    records = []
    with ThreadPoolExecutor(max_workers=min(workers, len(indices))) as pool:
        futures = {
            pool.submit(
                run_one,
                url,
                rows[index],
                f"{rows[index]['rid']}-{phase}-{sequence:02d}",
                phase,
                tokens,
                timeout,
            ): sequence
            for sequence, index in enumerate(indices)
        }
        for future in as_completed(futures):
            records.append(future.result())
            (out / f"{phase}.partial.json").write_text(
                json.dumps({"completed": len(records), "requests": records}, indent=2)
                + "\n"
            )
    records.sort(key=lambda item: item["rid"])
    return records


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--extent-dir", required=True)
    parser.add_argument("--server-log", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--parallel", type=int, default=8)
    parser.add_argument("--warm-output-tokens", type=int, default=1)
    parser.add_argument("--decode-output-tokens", type=int, default=256)
    parser.add_argument("--min-requests", type=int, default=12)
    parser.add_argument("--require-source", choices=("none", "l1", "l2", "l3", "mixed"), default="none")
    parser.add_argument("--require-sources", default="")
    parser.add_argument("--minimum-source-requests", type=int, default=1)
    parser.add_argument("--require-branch-exclusive", default="")
    parser.add_argument("--branch-sequence", default="")
    parser.add_argument("--frontier-count", type=int, default=0)
    parser.add_argument("--require-radix-split", action="store_true")
    parser.add_argument("--require-capacity", action="store_true")
    parser.add_argument("--require-frontier-recovery", action="store_true")
    parser.add_argument("--capacity-json")
    parser.add_argument("--stages", default="tier_probe,cold_storage_restore")
    parser.add_argument("--pressure-fixture")
    parser.add_argument("--pressure-requests", type=int, default=0)
    parser.add_argument("--context", type=int, default=131072)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fixture_path = Path(args.fixture)
    fixture_bytes = fixture_path.read_bytes()
    fixture = json.loads(fixture_bytes)
    rows = fixture["requests"]
    stages = {item.strip() for item in args.stages.split(",") if item.strip()}
    branch_sequence = [int(item.strip()) for item in args.branch_sequence.split(",") if item.strip()]
    if len(set(branch_sequence)) != len(branch_sequence):
        raise SystemExit("DUPLICATE_BRANCH_SEQUENCE")
    if any(branch not in (0, 1) for branch in branch_sequence):
        raise SystemExit("INVALID_BRANCH_SEQUENCE")
    allowed_stages = {"tier_probe", "flush", "cold_storage_restore", "branch_exclusive_l3"}
    if not stages or not stages <= allowed_stages:
        raise SystemExit(f"INVALID_STAGES:{sorted(stages)}")
    # Radix cache flush is terminal: it resets the tree and removes key
    # metadata needed to address persisted Extent values.
    required_sources = {item.strip() for item in args.require_sources.split(",") if item.strip()}
    if args.require_source != "none":
        required_sources.add(args.require_source)
    if not required_sources <= {"l1", "l2", "l3", "mixed"}:
        raise SystemExit(f"INVALID_REQUIRED_SOURCES:{sorted(required_sources)}")
    if branch_sequence and "l3" not in required_sources:
        raise SystemExit("BRANCH_EXCLUSIVE_RESTORE_SEQUENCE_REQUIRES_L3_GATE")
    if "branch_exclusive_l3" in stages and not branch_sequence:
        raise SystemExit("BRANCH_EXCLUSIVE_L3_REQUIRES_BRANCH_SEQUENCE")
    if "branch_exclusive_l3" in stages and "l3" not in required_sources:
        raise SystemExit("BRANCH_EXCLUSIVE_L3_REQUIRES_L3_SOURCE_GATE")
    required_branches = {int(item.strip()) for item in args.require_branch_exclusive.split(",") if item.strip()}
    if not required_branches <= {0, 1}:
        raise SystemExit(f"INVALID_REQUIRED_BRANCHES:{sorted(required_branches)}")
    if args.require_frontier_recovery and args.frontier_count == 0:
        raise SystemExit("FRONTIER_REQUESTS_NOT_SCHEDULED")
    if args.require_frontier_recovery and args.frontier_count > len(rows):
        raise SystemExit("FRONTIER_RECOVERY_COUNT_EXCEEDS_FIXTURE")
    if args.require_frontier_recovery and stages != {"tier_probe", "cold_storage_restore"}:
        raise SystemExit("FRONTIER_RECOVERY_REQUIRES_TIER_PROBE_AND_COLD_RESTORE_STAGES")
    if len(rows) < args.min_requests:
        raise SystemExit(f"FIXTURE_TOO_SMALL expected_at_least={args.min_requests} actual={len(rows)}")
    if required_sources and not args.require_capacity:
        raise SystemExit("SOURCE_QUALIFICATION_REQUIRES_CAPACITY_GATE")
    if args.pressure_requests < 0:
        raise SystemExit("INVALID_PRESSURE_REQUEST_COUNT")
    if args.pressure_requests and not args.require_capacity:
        raise SystemExit("PRESSURE_REQUIRES_CAPACITY_GATE")
    if required_sources and "cold_storage_restore" in stages and "tier_probe" not in stages:
        raise SystemExit("POST_FLUSH_RESTORE_REQUIRES_PRE_FLUSH_SOURCE_PROBE")
    if required_branches and not required_sources:
        raise SystemExit("BRANCH_QUALIFICATION_REQUIRES_SOURCE_GATE")
    if required_branches and set(branch_sequence) != required_branches:
        raise SystemExit("BRANCH_SEQUENCE_AND_REQUIRED_BRANCHES_MISMATCH")
    if required_branches and set(required_sources) != {"l3"}:
        raise SystemExit("BRANCH_EXCLUSIVE_STAGE_MUST_GATE_ONLY_L3")
    if branch_sequence and set(branch_sequence) != {0, 1}:
        raise SystemExit("BRANCH_EXCLUSIVE_SEQUENCE_MUST_COVER_BOTH_BRANCHES")
    if args.require_capacity:
        if not args.capacity_json:
            raise SystemExit("CAPACITY_JSON_REQUIRED")
        capacity = json.loads(Path(args.capacity_json).read_text())
        full_gauges = capacity.get("gpu_pool_capacity_gauges", {}).get("sglang:max_total_num_tokens", {})
        swa_gauges = capacity.get("gpu_pool_capacity_gauges", {}).get("sglang:max_total_num_tokens_swa", {})
        if len(full_gauges) != 1 or len(swa_gauges) != 1:
            raise SystemExit("CAPACITY_DEVICE_GAUGES_NOT_UNIQUE")
        gpu_full = int(next(iter(full_gauges.values())))
        gpu_swa = int(next(iter(swa_gauges.values())))
        host_pools = capacity.get("distinct_host_pool_allocations", {})
        if capacity.get("request_count") != 0 or not capacity.get("host_pools_distinct_full_swa"):
            raise SystemExit("CAPACITY_ARTIFACT_INVALID")
        if gpu_full != 139_264 or gpu_swa <= 0:
            raise SystemExit("CAPACITY_DEVICE_CONFIGURATION_MISMATCH")
        if int(host_pools.get("full", {}).get("tokens", 0)) <= gpu_full:
            raise SystemExit("CAPACITY_FULL_HOST_NOT_ABOVE_DEVICE")
        if int(host_pools.get("swa", {}).get("tokens", 0)) <= gpu_swa:
            raise SystemExit("CAPACITY_SWA_HOST_NOT_ABOVE_DEVICE")
        if int(fixture.get("unique_prefix_workset_tokens", 0)) <= gpu_full:
            raise SystemExit("FIXTURE_WORKSET_NOT_ABOVE_GPU_CAPACITY")
        if capacity.get("hicache_warnings"):
            raise SystemExit("CAPACITY_HICACHE_WARNING_PRESENT")
    root_tokens = int(fixture["shape"]["root_tokens"])
    branch_tokens = int(fixture["shape"]["branch_tokens_each"])
    unique_roots = {tuple(row["input_ids"][:root_tokens]) for row in rows}
    unique_branches = {
        tuple(row["input_ids"][root_tokens : root_tokens + branch_tokens])
        for row in rows
    }
    unique_leaves = {
        tuple(row["input_ids"][root_tokens + branch_tokens :]) for row in rows
    }
    if len(unique_roots) != 1 or len(unique_branches) != 2 or len(unique_leaves) != len(rows):
        raise SystemExit("FIXTURE_RADIX_SHAPE_MISMATCH")
    fanout = {branch_id: sum(int(row["branch_id"]) == branch_id for row in rows) for branch_id in (0, 1)}
    if set(fanout.values()) != {6}:
        raise SystemExit(f"FIXTURE_BRANCH_FANOUT_MISMATCH:{fanout}")
    identity = {
        "path": str(fixture_path),
        "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "schema": fixture.get("schema"),
        "prompt_sha256": [row["sha256"] for row in rows],
        "request_count": len(rows),
        "unique_prefix_workset_tokens": fixture.get("unique_prefix_workset_tokens"),
        "root_count": len(unique_roots),
        "branch_count": len(unique_branches),
        "leaf_count": len(unique_leaves),
    }
    write_json(out / "fixture.identity.json", identity)
    if args.require_capacity:
        extent_path = Path(args.extent_dir)
        if not extent_path.is_dir() or not os.access(extent_path, os.W_OK):
            raise SystemExit("EXTENT_DIRECTORY_NOT_WRITABLE")
        if shutil.disk_usage(extent_path).free < 34 * (1 << 30):
            raise SystemExit("EXTENT_FREE_SPACE_BELOW_34_GIB")
    initial = snapshot(args.url, out, "before", args.extent_dir)
    initial["host_pool_allocations"] = read_host_pool_allocations(args.server_log)
    initial["capacity_artifact"] = args.capacity_json
    if args.require_capacity and not initial["host_pool_allocations"].get("available"):
        raise SystemExit("RUNTIME_HOST_POOL_LOG_ALLOCATIONS_MISSING")
    if args.require_capacity:
        for name, key in (("full", "sglang:max_total_num_tokens"), ("swa", "sglang:max_total_num_tokens_swa")):
            runtime_gpu = initial["pool_capacities"].get(key)
            gauges = capacity["gpu_pool_capacity_gauges"][key]
            if len(gauges) != 1:
                raise SystemExit(f"CAPACITY_DEVICE_GAUGES_NOT_UNIQUE:{name}")
            recorded_gpu = int(next(iter(gauges.values())))
            runtime_host = initial["host_pool_allocations"]["pools"].get(name, {}).get("tokens")
            if int(runtime_gpu or 0) != recorded_gpu:
                raise SystemExit(f"RUNTIME_DEVICE_CAPACITY_MISMATCH:{name}")
            if int(runtime_host or 0) <= int(runtime_gpu or 0):
                raise SystemExit(f"RUNTIME_HOST_CAPACITY_NOT_ABOVE_DEVICE:{name}")
    write_json(out / "before.snapshot.json", initial)

    seed = [
        run_one(
            args.url,
            row,
            f"{row['rid']}-seed",
            "tree_seed",
            args.warm_output_tokens,
            args.timeout,
        )
        for row in rows
    ]
    write_json(out / "tree_seed.json", {"requests": seed})
    snapshot(args.url, out, "after_seed", args.extent_dir)
    # Probe the populated cache before flushing. Pressure from the deduplicated
    # tree may produce L1, L2, or L3 sources; preserve each RID independently.
    order = list(reversed(range(len(rows))))
    frontier_records = []
    if args.frontier_count > 0:
        frontier_records = [
            run_one(
                args.url,
                rows[index],
                f"{rows[index]['rid']}-frontier-recovery-{index:02d}",
                "frontier_recovery",
                args.decode_output_tokens,
                args.timeout,
            )
            for index in range(min(args.frontier_count, len(rows)))
        ]
        frontier_log = parse_restore_log(args.server_log, [record["rid"] for record in frontier_records])
        for record in frontier_records:
            record["restore_evidence"] = frontier_log.get(record["rid"], {})
        write_json(out / "frontier_recovery.json", {"requests": frontier_records})
        write_json(out / "frontier_precondition.json", {
            "cache_usage_before_restore": initial["pool_capacities"],
            "source_fixture_rids": [rows[i]["rid"] for i in range(min(args.frontier_count, len(rows)))],
        })
        snapshot(args.url, out, "after_frontier_recovery", args.extent_dir)

    host_probe = []
    cold_l3 = []
    flush = {"status": None, "body": "not_run"}
    branch_probe_records = []
    source_gate_host_probe = None
    final = snapshot(args.url, out, "after_seed", args.extent_dir)
    pressure = None
    if args.pressure_requests:
        if not args.pressure_fixture:
            raise SystemExit("PRESSURE_FIXTURE_REQUIRED")
        pressure_path = Path(args.pressure_fixture)
        pressure_fixture = json.loads(pressure_path.read_text())
        pressure_rows = pressure_fixture if isinstance(pressure_fixture, list) else pressure_fixture.get("requests", [])
        if len(pressure_rows) < args.pressure_requests:
            raise SystemExit("PRESSURE_FIXTURE_TOO_SMALL")
        pressure_snapshot = final
        host_capacity = int(capacity["distinct_host_pool_allocations"]["full"]["tokens"])
        device_capacity = int(capacity["gpu_pool_capacity_gauges"]["sglang:max_total_num_tokens"].get("", 0))
        if not device_capacity:
            device_capacity = int(next(iter(capacity["gpu_pool_capacity_gauges"]["sglang:max_total_num_tokens"].values())))
        target_tokens = args.context
        requested_workset = args.pressure_requests * target_tokens
        tiered_capacity = device_capacity + host_capacity
        if requested_workset <= tiered_capacity:
            raise SystemExit(f"PRESSURE_WORKSET_NOT_ABOVE_DEVICE_PLUS_HOST:{requested_workset}:{tiered_capacity}")
        pressure_records = []
        for index, row in enumerate(pressure_rows[:args.pressure_requests]):
            ids = row.get("input_ids")
            if not isinstance(ids, list) or len(ids) != target_tokens:
                raise SystemExit(f"PRESSURE_ROW_LENGTH:{index}:{len(ids) if isinstance(ids, list) else 'invalid'}:{target_tokens}")
            pressure_records.append(run_one(args.url, row, f"{row['rid']}-pressure", "capacity_pressure", 1, args.timeout))
            write_json(out / "capacity_pressure.partial.json", {"completed": len(pressure_records), "requests": pressure_records})
        write_json(out / "capacity_pressure.json", {"target_tokens_each": target_tokens, "requested_workset_tokens": requested_workset, "device_tokens": device_capacity, "host_tokens": host_capacity, "tiered_capacity_tokens": tiered_capacity, "requests": pressure_records})
        pressure_after = snapshot(args.url, out, "after_capacity_pressure", args.extent_dir)
        host_used = pressure_after["pool_capacities"].get("sglang:hicache_host_used_tokens")
        capacity["runtime_pressure"] = {"target_tokens": target_tokens, "device_tokens": device_capacity, "host_tokens": host_capacity, "host_used_tokens": host_used, "before": pressure_snapshot.get("pool_capacities"), "after": pressure_after.get("pool_capacities")}
        write_json(out / "capacity.runtime.json", capacity)
        if int(host_used or 0) <= 0:
            raise SystemExit("PRESSURE_DID_NOT_OBSERVE_HOST_TIER_USE")
    if "tier_probe" in stages:
        host_probe = run_parallel(
            args.url,
            rows,
            order,
            "tier_probe",
            args.decode_output_tokens,
            args.timeout,
            out,
            args.parallel,
        )
        write_json(out / "tier_probe.json", {"requests": host_probe})
        source_gate_host_probe = list(host_probe)
        final = snapshot(args.url, out, "after_tier_probe", args.extent_dir)
    if "branch_exclusive_l3" in stages:
        for branch in branch_sequence:
            final = snapshot(args.url, out, f"before_branch_{branch}_exclusive_l3", args.extent_dir)
            if branch == 0:
                # Retain the first branch's records before requesting the
                # second branch; the request stream is branch-exclusive.
                indices = [index for index, row in enumerate(rows) if int(row["branch_id"]) == branch]
            else:
                indices = [index for index, row in enumerate(rows) if int(row["branch_id"]) == branch]
            branch_records = run_parallel(
                args.url, rows, indices, f"branch_{branch}_exclusive_l3",
                args.decode_output_tokens, args.timeout, out, args.parallel,
            )
            evidence = parse_restore_log(args.server_log, [record["rid"] for record in branch_records])
            for record in branch_records:
                record["restore_evidence"] = evidence.get(record["rid"], {})
            branch_probe_records.extend(branch_records)
            write_json(out / f"branch_{branch}_exclusive_l3.json", {"requests": branch_records})
            final = snapshot(args.url, out, f"after_branch_{branch}_exclusive_l3", args.extent_dir)
    if "cold_storage_restore" in stages:
        cold_l3 = run_parallel(
            args.url,
            rows,
            order,
            "cold_storage_restore",
            args.decode_output_tokens,
            args.timeout,
            out,
            args.parallel,
        )
        write_json(out / "cold_storage_restore.json", {"requests": cold_l3})
        final = snapshot(args.url, out, "after_cold_storage_restore", args.extent_dir)
    if "flush" in stages:
        flush = flush_radix_cache(args.url, args.timeout)
        if flush.get("status") != 200 or not flush.get("success"):
            raise SystemExit(f"RADIX_FLUSH_FAILED:{flush}")
        write_json(out / "flush.json", {"epoch_s": time.time(), **flush})
        final = snapshot(args.url, out, "after_flush", args.extent_dir)

    def phase_summary(records, expected_tokens):
        successful = [record for record in records if record.get("ok")]
        latencies = [record["elapsed_s"] for record in successful]
        source_counts = {"device": 0, "host": 0, "storage": 0, "unknown": 0}
        source_rids = {"device": [], "host": [], "storage": [], "host_only": [], "storage_only": [], "mixed_host_storage": [], "unknown": []}
        for record in records:
            details = record.get("cached_tokens_details") or {}
            if not isinstance(details, dict):
                details = {}
            counts = {key: int(details.get(key, 0) or 0) for key in ("device", "host", "storage")}
            observed = False
            for key, count in counts.items():
                if count > 0:
                    source_counts[key] += 1
                    source_rids[key].append(record["rid"])
                    observed = True
            if counts["host"] > 0 and counts["storage"] == 0:
                source_rids["host_only"].append(record["rid"])
            if counts["storage"] > 0 and counts["host"] == 0:
                source_rids["storage_only"].append(record["rid"])
            if counts["host"] > 0 and counts["storage"] > 0:
                source_rids["mixed_host_storage"].append(record["rid"])
            if not observed:
                source_counts["unknown"] += 1
                source_rids["unknown"].append(record["rid"])
        log_by_rid = parse_restore_log(args.server_log, [record["rid"] for record in records])
        for record in records:
            record["restore_evidence"] = log_by_rid.get(record["rid"], {})
        return {
            "count": len(records),
            "success": len(successful),
            "expected_output_tokens": expected_tokens,
            "exact_output_tokens": all(
                record.get("completion_tokens") == expected_tokens
                and record.get("output_token_ids_count") == expected_tokens
                for record in records
            ),
            "request_source_request_counts": source_counts,
            "request_source_rids": source_rids,
            "source_qualified_request_ids": {
                "l1": [r["rid"] for r in records if int((r.get("cached_tokens_details") or {}).get("device", 0) or 0) > 0],
                "l2": [r["rid"] for r in records if int((r.get("cached_tokens_details") or {}).get("host", 0) or 0) > 0 and int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) == 0],
                "l3": [r["rid"] for r in records if int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) > 0 and any(positive_counter(line, "physical_bytes") > 0 for line in r.get("restore_evidence", {}).get("extent_reads", []))],
                "mixed": [r["rid"] for r in records if int((r.get("cached_tokens_details") or {}).get("host", 0) or 0) > 0 and int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) > 0 and any(positive_counter(line, "physical_bytes") > 0 for line in r.get("restore_evidence", {}).get("extent_reads", []))],
            },
            "source_qualified_decode_requests": {
                "l1": [r["rid"] for r in records if r.get("ok") and int((r.get("cached_tokens_details") or {}).get("device", 0) or 0) > 0],
                "l2": [r["rid"] for r in records if r.get("ok") and int((r.get("cached_tokens_details") or {}).get("host", 0) or 0) > 0 and int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) == 0],
                "l3": [r["rid"] for r in records if r.get("ok") and int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) > 0],
                "mixed": [r["rid"] for r in records if r.get("ok") and int((r.get("cached_tokens_details") or {}).get("host", 0) or 0) > 0 and int((r.get("cached_tokens_details") or {}).get("storage", 0) or 0) > 0],
            },
            "rid_extent_read_evidence": {
                record["rid"]: record.get("restore_evidence", {}).get("extent_reads", [])
                for record in records
            },
            "rid_restore_lifecycle_evidence": {
                record["rid"]: record.get("restore_evidence", {}).get("restore_events", [])
                for record in records
            },
            "rid_ready_evidence": {
                record["rid"]: record.get("restore_evidence", {}).get("ready_events", [])
                for record in records
            },
            "rid_host_alloc_wait_evidence": {
                record["rid"]: record.get("restore_evidence", {}).get("wait_events", [])
                for record in records
            },
            "rid_host_alloc_wake_evidence": {
                record["rid"]: record.get("restore_evidence", {}).get("wake_events", [])
                for record in records
            },
            "latency_p50_s": statistics.median(latencies) if latencies else None,
            "request_ids": [record["rid"] for record in records],
        }

    summary = {
        "fixture": identity,
        "seed": phase_summary(seed, args.warm_output_tokens),
        "tier_probe": phase_summary(host_probe, args.decode_output_tokens) if host_probe else {"count": 0, "success": 0},
        "tier_probe_source_gates": {
            source: [record["rid"] for record in host_probe if source_restore_qualified(record, source, args.decode_output_tokens)]
            for source in ("l1", "l2", "l3", "mixed")
        },
        "branch_exclusive_l3": {
            str(branch): {
                "count": sum(record.get("branch_id") == branch for record in branch_probe_records),
                "success": sum(record.get("branch_id") == branch and record.get("ok") for record in branch_probe_records),
                "source_qualified": sum(source_restore_qualified(record, "l3", args.decode_output_tokens) for record in branch_probe_records if record.get("branch_id") == branch),
                "request_ids": [record["rid"] for record in branch_probe_records if record.get("branch_id") == branch],
            }
            for branch in branch_sequence
        },
        "cold_storage_restore": phase_summary(cold_l3, args.decode_output_tokens) if cold_l3 else {"count": 0, "success": 0},
        "frontier_recovery": phase_summary(frontier_records, args.decode_output_tokens) if frontier_records else {"count": 0, "success": 0},
        "flush": flush,
        "stages_requested": sorted(stages),
        "snapshots": ["before", "after_seed", "after_tier_probe", "after_flush", "after_cold_storage_restore"],
        "initial_extent_files": initial["extent_files"],
        "final_extent_files": final["extent_files"],
        "host_pool_allocations": initial.get("host_pool_allocations"),
        "finished_epoch_s": time.time(),
    }
    expected = len(rows)
    if summary["seed"]["success"] != expected:
        raise SystemExit("TREE_SEED_FAILURE")
    flush_body = flush.get("body", "").strip().lower()
    flush_ok = flush["status"] == 200 and flush.get("success") is True
    if "flush" in stages and not flush_ok:
        raise SystemExit("RADIX_FLUSH_BODY_FAILURE")
    if args.require_radix_split:
        event_path = out.parent / "tree-lifecycle-events.json"
        if not event_path.exists():
            raise SystemExit("RADIX_TRACE_ARTIFACT_MISSING")
        with event_path.open() as stream:
            lifecycle_events = json.load(stream)
        try:
            validate_radix_events(lifecycle_events)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        trace_artifact = out.parent / "hicache_quiescent.json"
        if not trace_artifact.exists():
            raise SystemExit("RADIX_QUIESCENT_ARTIFACT_MISSING")
        quiescent = json.loads(trace_artifact.read_text())
        trace_ops = quiescent.get("tree_trace_operations", {})
        if not quiescent.get("observed") or quiescent.get("tree_trace_violation"):
            raise SystemExit("RADIX_QUIESCENT_TRACE_INVALID")
        if trace_ops.get("split_new_prefix", 0) < 1 or trace_ops.get("split_old_child", 0) < 1:
            raise SystemExit("RADIX_QUIESCENT_SPLIT_NOT_CONFIRMED")
    source_records_by_source = {}
    for source in sorted(required_sources):
        stage_for_source = "cold_storage_restore" if source in ("l3", "mixed") else "tier_probe"
        if stage_for_source not in stages:
            raise SystemExit(f"SOURCE_STAGE_NOT_REQUESTED:{source}:{stage_for_source}")
        phase_records = (source_gate_host_probe or host_probe) if source in ("l1", "l2") else cold_l3
        if not phase_records:
            raise SystemExit(f"SOURCE_GATE_NO_REQUESTS:{source}")
        qualified = [
            record for record in phase_records
            if source_restore_qualified(record, source, args.decode_output_tokens)
        ]
        source_records_by_source[source] = qualified
        if len(qualified) < args.minimum_source_requests:
            raise SystemExit(f"SOURCE_GATE_{source.upper()}:{len(qualified)}/{args.minimum_source_requests}")
    if required_branches:
        if "branch_exclusive_l3" not in stages or branch_sequence != sorted(required_branches):
            raise SystemExit("BRANCH_EXCLUSIVE_SEQUENCE_MISMATCH")
        for branch in sorted(required_branches):
            records = [record for record in branch_probe_records if record.get("branch_id") == branch]
            if len(records) != 6 or any(
                not source_restore_qualified(record, "l3", args.decode_output_tokens)
                for record in records
            ):
                raise SystemExit(f"BRANCH_EXCLUSIVE_L3_DECODE_GATE:{branch}")

    if args.require_frontier_recovery:
        if not args.require_capacity:
            raise SystemExit("FRONTIER_CAPACITY_PRECONDITION_NOT_REQUIRED")
        if not args.frontier_count:
            raise SystemExit("FRONTIER_REQUESTS_NOT_SCHEDULED")
        recovered_records = [
            record for record in frontier_records
            if frontier_recovery_qualified(record, args.decode_output_tokens)
        ]
        if not recovered_records:
            raise SystemExit("FRONTIER_RECOVERY_GATE_MISSING")
        if not all(record.get("cached_tokens_details") for record in recovered_records):
            raise SystemExit("FRONTIER_RECOVERY_SOURCE_DETAILS_MISSING")
    if args.frontier_count > 0 and summary["frontier_recovery"]["success"] != len(frontier_records):
        raise SystemExit("FRONTIER_DECODE_FAILURE")
    if args.require_frontier_recovery and not recovered_records:
        raise SystemExit("FRONTIER_RECOVERY_QUALIFICATION_MISSING")
    if "tier_probe" in stages and summary["tier_probe"]["success"] != expected:
        raise SystemExit("TIER_PROBE_DECODE_FAILURE")
    if "tier_probe" in stages and not any(summary["tier_probe_source_gates"].values()):
        raise SystemExit("TIER_PROBE_HAS_NO_QUALIFIED_SOURCE")
    if "cold_storage_restore" in stages and summary["cold_storage_restore"]["success"] != expected:
        raise SystemExit("RESTORE_DECODE_FAILURE")
    if "branch_exclusive_l3" in stages:
        for branch in branch_sequence:
            result = summary["branch_exclusive_l3"][str(branch)]
            if result["count"] != 6 or result["success"] != 6 or result["source_qualified"] != 6:
                raise SystemExit(f"BRANCH_EXCLUSIVE_L3_GATE:{branch}:{result}")
    write_json(out / "lifecycle.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
