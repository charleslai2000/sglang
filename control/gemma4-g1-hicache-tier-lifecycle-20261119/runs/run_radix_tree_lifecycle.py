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
        "sglang:hicache_host_used_tokens",
        "sglang:hicache_host_total_tokens",
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


def admin_headers(admin_api_key):
    return {"Authorization": f"Bearer {admin_api_key}"} if admin_api_key else {}


def storage_backend_state(url, admin_api_key, timeout=30):
    request = urllib.request.Request(
        url + "/hicache/storage-backend",
        headers=admin_headers(admin_api_key),
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def set_storage_backend(
    url,
    admin_api_key,
    *,
    detach,
    backend=None,
    extra_config=None,
    prefetch_policy=None,
    write_policy=None,
    timeout=180,
):
    """Attach or detach the HiCache storage backend through the runtime control API."""
    headers = {"Content-Type": "application/json", **admin_headers(admin_api_key)}
    if detach:
        request = urllib.request.Request(
            url + "/hicache/storage-backend", headers=headers, method="DELETE"
        )
    else:
        payload = {
            "hicache_storage_backend": backend,
            "hicache_storage_backend_extra_config_json": extra_config,
        }
        if prefetch_policy:
            payload["hicache_storage_prefetch_policy"] = prefetch_policy
        if write_policy:
            payload["hicache_write_policy"] = write_policy
        request = urllib.request.Request(
            url + "/hicache/storage-backend",
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers=headers,
            method="PUT",
        )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": response.status,
                "body": response.read().decode(errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "body": exc.read().decode(errors="replace"),
        }


def wait_for_scheduler_idle(url, timeout=180, label="idle"):
    """Wait for full scheduler + HiCache quiescence.

    This is deliberately a poll rather than a fixed sleep: after a heavy restore
    phase the write-through queue can hold a backlog whose drain time is not
    bounded by request completion. `backup`/`ongoing_backup` are pending counts,
    so a service that keeps emitting backups never reads idle.
    """
    deadline = time.monotonic() + timeout
    last = None
    next_report = time.monotonic() + 30
    while time.monotonic() < deadline:
        if time.monotonic() >= next_report:
            print(f"[{label}] still waiting: {last}", flush=True)
            next_report = time.monotonic() + 30
        with urllib.request.urlopen(url + "/server_info", timeout=10) as response:
            info = json.loads(response.read())
        states = info.get("internal_states", [])
        last = [state.get("g1_p0_hicache_pending", {}) for state in states]
        if states and all(
            state.get("g1_p0_is_fully_idle") is True
            and all(
                pending.get(key, 0) == 0
                for key in (
                    "running",
                    "waiting",
                    "result_queue",
                    "write_through",
                    "load_back",
                    "prefetch",
                    "backup",
                    "ongoing_backup",
                )
            )
            and pending.get("buffer_pipeline_idle") is True
            for state, pending in zip(states, last)
        ):
            return True, last
        time.sleep(1)
    return False, last


def positive_counter(line, name):
    match = re.search(rf"(?:^|\s){name}=(\d+)(?:\s|$)", line)
    return int(match.group(1)) if match else 0


def field_value(line, name):
    match = re.search(rf"(?:^|\s){name}=([^\s]+)", line)
    return match.group(1) if match else None


def rid_matches_line(rid, line):
    """Match a client RID with the scheduler's optional batched-ID suffix."""
    return bool(re.search(rf"(?:^|\s)rid={re.escape(str(rid))}(?:_\d+)?(?:\s|$)", line))


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
        rid_matches_line(record.get("rid"), line) and "finalize_result=accepted" in line
        for line in ready_events
    )
    accepted_restore = any(
        rid_matches_line(record.get("rid"), line)
        and "disposition=RESTORE" in line
        and positive_counter(line, "requested") > 0
        and positive_counter(line, "granted") == positive_counter(line, "requested")
        for line in evidence.get("restore_events", [])
    )
    # A pure Host hit (device-miss, storage-miss/absent) never enters the P2A
    # storage-restore path, so it emits no `disposition=RESTORE`. It is
    # materialized by promoting the Host-resident prefix into Device instead.
    # Accept that mechanism only when the promotion is RID-correlated and
    # covers exactly the Host-resident token count, which ties the Device
    # placement to the Host copy rather than to a recompute.
    promoted_host = h > 0 and any(
        rid_matches_line(record.get("rid"), line)
        and positive_counter(line, "n") == h
        for line in evidence.get("promotion_reserves", [])
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
        "l2": h > 0 and s == 0 and ((accepted_ready and accepted_restore) or promoted_host),
        "l3": s > 0 and extent_read and accepted_ready and accepted_restore,
        "mixed": h > 0 and s > 0 and extent_read and accepted_ready and accepted_restore,
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
        # Runtime frontier_wait/frontier_wake currently identify the same RID
        # and node but do not expose a wait_id. RID-scoped order plus a
        # successful post-retry ready event is the available causal join.
        if (
            ready_index is not None
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
            rid_matches_line(record.get("rid"), ready)
            and f"wait_id={wake.get('wait_id')} " in ready
            and f"wake_event_id={wake.get('event_id')} " in ready
            and "finalize_result=accepted" in ready
            for ready in evidence.get("ready_events", [])
        )
        if (
            matched_wait
            and matched_ready
            and any(
                rid_matches_line(record.get("rid"), retry)
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
                    base_rid = next((candidate for candidate in wanted if rid == candidate or (rid and re.fullmatch(re.escape(candidate) + r"_\d+", rid))), None)
                    if base_rid is not None:
                        events[base_rid].append(("hae", event, line.rstrip()))
                    continue
                if "rid=" not in line:
                    continue
                # Scheduler normalizes batched generate IDs with a trailing
                # _<index> (currently _0). Join that exact suffix while
                # keeping r1 distinct from r10 and any other RID prefix.
                rid = next(
                    (
                        candidate
                        for candidate in wanted
                        if re.search(rf"(?:^|\s)rid={re.escape(candidate)}(?:_\d+)?(?:\s|$)", line)
                    ),
                    None,
                )
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
                if "evt=restore_disposition" in line and "disposition=RESTORE" in line
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
            "ready_events": [line for line in lines if "evt=ready_host" in line],
            "promotion_reserves": [line for line in lines if "evt=promotion_reserve" in line],
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
    parser.add_argument(
        "--admin-api-key", default=os.environ.get("G1_PROD_ADMIN_API_KEY", "")
    )
    parser.add_argument("--l2-only-storage-backend", default="")
    parser.add_argument("--l2-only-idle-timeout", type=int, default=600)
    # A branch-exclusive restore that arrives while the write-through backlog is
    # still draining cannot get a Host allocation (miss_reason=alloc_failed), is
    # parked in WAIT_CAPACITY and then falls back to recompute -- which hides the
    # Extent read the branch gate is looking for. Wait for quiescence first.
    parser.add_argument("--branch-idle-timeout", type=int, default=0)
    # The rows touched last by the seed phase are still Device-resident when the
    # branch phase starts, so their restores are Device hits and produce no
    # Extent read (r18: 9/12 qualified, the misses were each branch's first
    # request). A churn pass re-reads every row once at one output token in
    # fixture order, which pushes them out of the Device pool again while
    # leaving the two hottest rows -- which the measured pass reaches last --
    # to be evicted by the restores that precede them.
    parser.add_argument("--branch-churn-passes", type=int, default=0)
    parser.add_argument("--l2-only-churn-passes", type=int, default=1)
    parser.add_argument("--l2-only-storage-extra-config", default="")
    parser.add_argument("--l2-only-storage-prefetch-policy", default="")
    parser.add_argument("--l2-only-storage-write-policy", default="")
    parser.add_argument("--require-capacity", action="store_true")
    parser.add_argument("--require-frontier-recovery", action="store_true")
    parser.add_argument("--capacity-json")
    parser.add_argument("--stages", default="tier_probe,cold_storage_restore")
    parser.add_argument("--pressure-fixture")
    parser.add_argument("--pressure-requests", type=int, default=0)
    parser.add_argument("--pressure-prompt-tokens", type=int, default=130000)
    parser.add_argument("--context", type=int, default=131072)
    parser.add_argument("--pressure-preserve-prefix", action="store_true")
    parser.add_argument("--pressure-min-device-evictions", type=int, default=1)
    parser.add_argument("--pressure-min-storage-bytes", type=int, default=1)
    parser.add_argument("--pressure-watermark-timeout", type=int, default=90)
    parser.add_argument("--pressure-max-prompt-tokens", type=int, default=130000)
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
    allowed_stages = {
        "tier_probe",
        "flush",
        "cold_storage_restore",
        "branch_exclusive_l3",
        "l2_only_probe",
    }
    if not stages or not stages <= allowed_stages:
        raise SystemExit(f"INVALID_STAGES:{sorted(stages)}")
    # Radix cache flush is terminal: it resets the tree and removes key
    # metadata needed to address persisted Extent values.
    required_sources = {item.strip() for item in args.require_sources.split(",") if item.strip()}
    if args.require_source != "none":
        required_sources.add(args.require_source)
    if not required_sources <= {"l1", "l2", "l3", "mixed"}:
        raise SystemExit(f"INVALID_REQUIRED_SOURCES:{sorted(required_sources)}")
    # The per-branch gate below already requires all six requests of each branch
    # to satisfy source_restore_qualified(record, "l3"), which is strictly
    # stronger than a single l3 sample. When that gate is armed, an explicit
    # l3 source request is redundant.
    branch_gate_covers_l3 = "branch_exclusive_l3" in stages and bool(
        args.require_branch_exclusive
    )
    if branch_sequence and "l3" not in required_sources and not branch_gate_covers_l3:
        raise SystemExit("BRANCH_EXCLUSIVE_RESTORE_SEQUENCE_REQUIRES_L3_GATE")
    if "branch_exclusive_l3" in stages and not branch_sequence:
        raise SystemExit("BRANCH_EXCLUSIVE_L3_REQUIRES_BRANCH_SEQUENCE")
    if "branch_exclusive_l3" in stages and "l3" not in required_sources and not branch_gate_covers_l3:
        raise SystemExit("BRANCH_EXCLUSIVE_L3_REQUIRES_L3_SOURCE_GATE")
    required_branches = {int(item.strip()) for item in args.require_branch_exclusive.split(",") if item.strip()}
    if not required_branches <= {0, 1}:
        raise SystemExit(f"INVALID_REQUIRED_BRANCHES:{sorted(required_branches)}")
    if args.require_frontier_recovery and args.frontier_count == 0:
        raise SystemExit("FRONTIER_REQUESTS_NOT_SCHEDULED")
    if args.require_frontier_recovery and args.frontier_count < 2:
        raise SystemExit("FRONTIER_RECOVERY_REQUIRES_MULTIPLE_REQUESTS")
    if args.require_frontier_recovery and args.frontier_count > len(rows):
        raise SystemExit("FRONTIER_RECOVERY_COUNT_EXCEEDS_FIXTURE")
    if args.require_frontier_recovery and not args.pressure_requests:
        raise SystemExit("FRONTIER_RECOVERY_REQUIRES_CAPACITY_PRESSURE")
    if args.require_frontier_recovery and args.pressure_requests < args.frontier_count + 1:
        raise SystemExit("FRONTIER_RECOVERY_REQUIRES_PRESSURE_HEADROOM")
    if args.require_frontier_recovery and ("tier_probe" not in stages or "cold_storage_restore" not in stages):
        raise SystemExit("FRONTIER_RECOVERY_REQUIRES_TIER_PROBE_AND_COLD_RESTORE_STAGES")
    if len(rows) < args.min_requests:
        raise SystemExit(f"FIXTURE_TOO_SMALL expected_at_least={args.min_requests} actual={len(rows)}")
    if "l2_only_probe" in stages:
        # The Host tier is isolated by detaching the durable backend at runtime,
        # because write_through makes every Host-resident prefix also
        # storage-resident once its backup is acknowledged.
        if not args.admin_api_key:
            raise SystemExit("L2_ONLY_PROBE_REQUIRES_ADMIN_API_KEY")
        if not args.pressure_requests:
            raise SystemExit("L2_ONLY_PROBE_REQUIRES_CAPACITY_PRESSURE")
        if "tier_probe" not in stages:
            raise SystemExit("L2_ONLY_PROBE_REQUIRES_TIER_PROBE")
    if required_sources and not args.require_capacity:
        raise SystemExit("SOURCE_QUALIFICATION_REQUIRES_CAPACITY_GATE")
    # Capacity pressure is what normally evicts the fixture from Device, but it
    # also saturates the Host pool with in-flight backups, which makes the
    # branch restores fail their Host allocation (miss_reason=alloc_failed) even
    # though the Extent copy exists. A branch-exclusive run can get the same
    # eviction from the seed phase plus its own churn pass, so the pressure
    # requirement is waived when the per-branch l3 gate is armed.
    if required_sources and not args.pressure_requests and not branch_gate_covers_l3:
        raise SystemExit("SOURCE_QUALIFICATION_REQUIRES_CAPACITY_PRESSURE")
    if args.pressure_requests < 0:
        raise SystemExit("INVALID_PRESSURE_REQUEST_COUNT")
    if args.pressure_requests and not args.require_capacity:
        raise SystemExit("PRESSURE_REQUIRES_CAPACITY_GATE")
    # Pressure normally exists to give tier_probe a Host/Extent-populated tree.
    # A branch-exclusive run needs it for the opposite reason: the branch
    # suffixes must be pushed OUT of Device so their restores come from the
    # Extent instead of a Device hit, and pressure runs before every stage.
    if args.pressure_requests and "tier_probe" not in stages and "branch_exclusive_l3" not in stages:
        raise SystemExit("CAPACITY_PRESSURE_REQUIRES_TIER_PROBE")
    if args.pressure_requests and args.pressure_prompt_tokens <= 0:
        raise SystemExit("INVALID_PRESSURE_PROMPT_LENGTH")
    if args.pressure_requests and args.pressure_max_prompt_tokens < args.pressure_prompt_tokens:
        raise SystemExit("PRESSURE_MAX_PROMPT_TOKENS_BELOW_INITIAL")
    if required_sources and "cold_storage_restore" in stages and "tier_probe" not in stages:
        raise SystemExit("LOWER_TIER_SOURCE_GATE_REQUIRES_TIER_PROBE")
    # required_branches is itself the l3 gate for a branch run: see
    # branch_gate_covers_l3 above. Its per-record check is stronger than an
    # aggregate l3 source sample, so this guard no longer needs an explicit
    # l3 request.
    if required_branches and set(branch_sequence) != required_branches:
        raise SystemExit("BRANCH_SEQUENCE_AND_REQUIRED_BRANCHES_MISMATCH")
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
        capacity["runtime_before"] = {
            "gpu_pool_capacities": initial["pool_capacities"],
            "host_pool_allocations": initial["host_pool_allocations"],
        }
        write_json(out / "capacity.runtime.json", capacity)
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

    l1_probe = []
    host_probe = []
    cold_l3 = []
    flush = {"status": None, "body": "not_run"}
    branch_probe_records = []
    source_gate_host_probe = None
    final = snapshot(args.url, out, "after_seed", args.extent_dir)
    pressure = {}
    if args.pressure_requests:
        if not args.pressure_fixture:
            raise SystemExit("PRESSURE_FIXTURE_REQUIRED")
        pressure_path = Path(args.pressure_fixture)
        pressure_fixture = json.loads(pressure_path.read_text())
        pressure_rows = pressure_fixture if isinstance(pressure_fixture, list) else pressure_fixture.get("requests", [])
        if len(pressure_rows) < args.pressure_requests:
            raise SystemExit("PRESSURE_FIXTURE_TOO_SMALL")
        pressure_snapshot = final
        pressure["before"] = pressure_snapshot.get("pool_capacities")
        host_capacity = int(capacity["distinct_host_pool_allocations"]["full"]["tokens"])
        device_capacity = int(next(iter(capacity["gpu_pool_capacity_gauges"]["sglang:max_total_num_tokens"].values())))
        target_tokens = args.pressure_prompt_tokens
        maximum_pressure_tokens = args.pressure_max_prompt_tokens
        if target_tokens <= 0 or target_tokens + 1 > args.context:
            raise SystemExit(f"INVALID_PRESSURE_PROMPT_LENGTH:{target_tokens}:{args.context}")
        pressure_prefix_tokens = 0
        pressure_rows = pressure_rows[:args.pressure_requests]
        if args.pressure_preserve_prefix:
            bases = [row.get("input_ids", [])[:16384] for row in pressure_rows]
            if not bases or any(base != bases[0] for base in bases):
                raise SystemExit("PRESSURE_SHARED_ROOT_MISMATCH")
            pressure_prefix_tokens = len(bases[0])
            if pressure_prefix_tokens >= target_tokens:
                raise SystemExit("PRESSURE_PREFIX_NOT_SHORTER_THAN_PROMPT")
        requested_workset = pressure_prefix_tokens + args.pressure_requests * (target_tokens - pressure_prefix_tokens)
        tiered_capacity = device_capacity + host_capacity
        if requested_workset <= tiered_capacity:
            if args.pressure_min_device_evictions <= 0:
                raise SystemExit(f"PRESSURE_WORKSET_NOT_ABOVE_DEVICE_PLUS_HOST:{requested_workset}:{tiered_capacity}")
            candidate_tokens = target_tokens
            max_tokens = min(maximum_pressure_tokens, args.context - 1)
            while (
                pressure_prefix_tokens + args.pressure_requests * (candidate_tokens - pressure_prefix_tokens)
                <= tiered_capacity
                and candidate_tokens < max_tokens
            ):
                candidate_tokens = min(max_tokens, candidate_tokens + 4096)
            target_tokens = candidate_tokens
            requested_workset = pressure_prefix_tokens + args.pressure_requests * (target_tokens - pressure_prefix_tokens)
        if requested_workset <= tiered_capacity:
            raise SystemExit(f"PRESSURE_WORKSET_NOT_ABOVE_DEVICE_PLUS_HOST:{requested_workset}:{tiered_capacity}")
        pressure_records = []
        for index, row in enumerate(pressure_rows[:args.pressure_requests]):
            ids = row.get("input_ids")
            if not isinstance(ids, list) or len(ids) < target_tokens:
                raise SystemExit(f"PRESSURE_ROW_TOO_SHORT:{index}:{len(ids) if isinstance(ids, list) else 'invalid'}:{target_tokens}")
            if args.pressure_preserve_prefix and ids[:pressure_prefix_tokens] != pressure_rows[0]["input_ids"][:pressure_prefix_tokens]:
                raise SystemExit(f"PRESSURE_REQUEST_ROOT_MISMATCH:{index}")
            pressure_row = dict(row)
            pressure_row["input_ids"] = ids[:target_tokens]
            pressure_row["sha256"] = hashlib.sha256(json.dumps(pressure_row["input_ids"], separators=(",", ":")).encode()).hexdigest()
            result = run_one(args.url, pressure_row, f"{row['rid']}-pressure", "capacity_pressure", 1, args.timeout)
            pressure_records.append(result)
            write_json(out / "capacity_pressure.partial.json", {"completed": len(pressure_records), "requests": pressure_records})
            if not result.get("ok") or result.get("completion_tokens") != 1:
                raise SystemExit(f"PRESSURE_REQUEST_FAILED:{index}:{result.get('rid')}:{result.get('error', 'incomplete_output')}")
        write_json(out / "capacity_pressure.json", {"target_tokens_each": target_tokens, "requested_workset_tokens": requested_workset, "device_tokens": device_capacity, "host_tokens": host_capacity, "tiered_capacity_tokens": tiered_capacity, "shared_root_tokens": pressure_prefix_tokens, "requests": pressure_records})
        pressure_after = snapshot(args.url, out, "after_capacity_pressure", args.extent_dir)
        if pressure_after["pool_capacities"].get("sglang:hicache_host_used_tokens") is None:
            raise SystemExit("PRESSURE_HOST_USAGE_METRIC_MISSING")
        pressure["watermark"] = {
            "host_used_tokens": pressure_after["pool_capacities"].get("sglang:hicache_host_used_tokens"),
            "backup_counters": pressure_after.get("tier_transfer_counters", {}),
            "extent_bytes": sum(int(item.get("size_bytes", 0)) for item in pressure_after.get("extent_files", {}).values()),
        }
        extent_before = pressure_snapshot.get("extent_files", {})
        extent_bytes_before = sum(int(item.get("size_bytes", 0)) for item in extent_before.values())
        backups_before = pressure_snapshot.get("tier_transfer_counters", {}).get("sglang:backuped_tokens_total", {})
        watermark_deadline = time.monotonic() + args.pressure_watermark_timeout
        while time.monotonic() < watermark_deadline:
            host_now = pressure_after["pool_capacities"].get("sglang:hicache_host_used_tokens")
            ext_now = pressure_after.get("extent_files", {})
            ext_now_bytes = sum(int(item.get("size_bytes", 0)) for item in ext_now.values())
            backup_now = pressure_after.get("tier_transfer_counters", {}).get("sglang:backuped_tokens_total", {})
            evictions_now = sum(max(0, int(float(backup_now.get(key, 0)) - float(backups_before.get(key, 0)))) for key in set(backups_before) | set(backup_now))
            if int(host_now or 0) > 0 and evictions_now >= args.pressure_min_device_evictions and ext_now_bytes - extent_bytes_before >= args.pressure_min_storage_bytes:
                break
            time.sleep(1)
            pressure_after = snapshot(args.url, out, "after_capacity_pressure_watermark", args.extent_dir)
        pressure["records"] = pressure_records
        pressure["after"] = pressure_after.get("pool_capacities")
        host_used = pressure_after["pool_capacities"].get("sglang:hicache_host_used_tokens")
        extent_after = pressure_after.get("extent_files", {})
        extent_bytes_after = sum(int(item.get("size_bytes", 0)) for item in extent_after.values())
        backups_after = pressure_after.get("tier_transfer_counters", {}).get("sglang:backuped_tokens_total", {})
        evictions = sum(max(0, int(float(backups_after.get(key, 0)) - float(backups_before.get(key, 0)))) for key in set(backups_before) | set(backups_after))
        capacity["runtime_pressure"] = {"target_tokens_each": target_tokens, "device_tokens": device_capacity, "host_tokens": host_capacity, "host_used_tokens": host_used, "device_evicted_tokens_delta": evictions, "extent_bytes_before": extent_bytes_before, "extent_bytes_after": extent_bytes_after, "extent_bytes_written_delta": extent_bytes_after - extent_bytes_before, "before": pressure_snapshot.get("pool_capacities"), "after": pressure_after.get("pool_capacities")}
        write_json(out / "capacity.runtime.json", capacity)
        if int(host_used or 0) <= 0:
            raise SystemExit("PRESSURE_DID_NOT_OBSERVE_HOST_TIER_USE")
        if evictions < args.pressure_min_device_evictions:
            raise SystemExit(f"PRESSURE_DEVICE_EVICTION_BELOW_THRESHOLD:{evictions}:{args.pressure_min_device_evictions}")
        if extent_bytes_after - extent_bytes_before < args.pressure_min_storage_bytes:
            raise SystemExit(f"PRESSURE_EXTENT_WRITE_BELOW_THRESHOLD:{extent_bytes_after - extent_bytes_before}:{args.pressure_min_storage_bytes}")
    if args.frontier_count > 0:
        frontier_indices = list(range(min(args.frontier_count, len(rows))))
        frontier_pre_snapshot = snapshot(args.url, out, "before_frontier_recovery", args.extent_dir)
        frontier_records = run_parallel(
            args.url, rows, frontier_indices, "frontier_recovery",
            args.decode_output_tokens, args.timeout, out, args.parallel,
        )
        frontier_log = parse_restore_log(args.server_log, [record["rid"] for record in frontier_records])
        for record in frontier_records:
            record["restore_evidence"] = frontier_log.get(record["rid"], {})
        write_json(out / "frontier_recovery.json", {"requests": frontier_records})
        write_json(out / "frontier_precondition.json", {
            "cache_usage_before_restore": frontier_pre_snapshot["pool_capacities"],
            "tier_transfer_counters_before": frontier_pre_snapshot["tier_transfer_counters"],
            "source_fixture_rids": [rows[i]["rid"] for i in frontier_indices],
            "preceding_capacity_pressure": bool(pressure),
        })
        snapshot(args.url, out, "after_frontier_recovery", args.extent_dir)
    if "tier_probe" in stages:
        l1_probe = [
            run_one(args.url, rows[0], f"{rows[0]['rid']}-l1_probe", "l1_probe", args.decode_output_tokens, args.timeout)
        ]
        l1_evidence = parse_restore_log(args.server_log, [record["rid"] for record in l1_probe])
        for record in l1_probe:
            record["restore_evidence"] = l1_evidence.get(record["rid"], {})
        write_json(out / "l1_probe.json", {"requests": l1_probe})
        final = snapshot(args.url, out, "after_l1_probe", args.extent_dir)
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
        if args.branch_idle_timeout:
            # Best effort, unlike the l2-only stage: the write-through backlog
            # left by capacity pressure drains at roughly 1-1.5k tokens per
            # ack, tens of seconds apart, so a full drain can take hours. A few
            # minutes is enough for the first wave of acks to release the Host
            # pages the restores need, and the per-request evidence decides
            # whether the phase actually qualified.
            idle_reports = {}
            for branch in branch_sequence:
                idle_ok, idle_state = wait_for_scheduler_idle(
                    args.url, args.branch_idle_timeout, f"branch_{branch}_exclusive_l3"
                )
                idle_reports[str(branch)] = {"observed": idle_ok, "state": idle_state}
            write_json(
                out / "branch_idle.json",
                {"observed": all(item["observed"] for item in idle_reports.values()),
                 "best_effort": True, "per_branch": idle_reports},
            )
        churn_records = []
        for pass_index in range(args.branch_churn_passes):
            churn_records.extend(
                run_parallel(
                    args.url,
                    rows,
                    list(range(len(rows))),
                    f"branch_churn_{pass_index}",
                    1,
                    args.timeout,
                    out,
                    args.parallel,
                )
            )
            write_json(
                out / f"branch_churn_{pass_index}.json",
                {"requests": churn_records[-(len(rows)):]},
            )
        if churn_records:
            churn_evidence = parse_restore_log(
                args.server_log, [record["rid"] for record in churn_records]
            )
            for record in churn_records:
                record["restore_evidence"] = churn_evidence.get(record["rid"], {})
        for branch in branch_sequence:
            final = snapshot(args.url, out, f"before_branch_{branch}_exclusive_l3", args.extent_dir)
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
            args.url, rows, order, "cold_storage_restore",
            args.decode_output_tokens, args.timeout, out, args.parallel,
        )
        write_json(out / "cold_storage_restore.json", {"requests": cold_l3})
        final = snapshot(args.url, out, "after_cold_storage_restore", args.extent_dir)
    l2_only = []
    storage_control = {}
    if "l2_only_probe" in stages:
        idle_ok, idle_state = wait_for_scheduler_idle(
            args.url, args.l2_only_idle_timeout, "l2_only_probe"
        )
        if not idle_ok:
            raise SystemExit(f"L2_ONLY_PROBE_NOT_IDLE:{idle_state}")
        control_before = storage_backend_state(args.url, args.admin_api_key)
        detach = set_storage_backend(args.url, args.admin_api_key, detach=True)
        if detach.get("status") != 200 or "detached" not in detach.get("body", "").lower():
            raise SystemExit(f"L2_ONLY_PROBE_DETACH_FAILED:{detach}")
        control_detached = storage_backend_state(args.url, args.admin_api_key)
        if control_detached.get("hicache_storage_backend") not in (None, "", "none"):
            raise SystemExit(f"L2_ONLY_PROBE_DETACH_NOT_EFFECTIVE:{control_detached}")
        reattach_extra = (
            args.l2_only_storage_extra_config
            or control_before.get("hicache_storage_backend_extra_config")
        )
        if isinstance(reattach_extra, (dict, list)):
            reattach_extra = json.dumps(reattach_extra, separators=(",", ":"))
        # Churn the Device pool across the whole fixture first (1 token each,
        # reverse order) so that by the time the measured pass runs, the tail
        # prefixes are Device-evicted while their Host copies remain. Without
        # this the probe can land entirely on Device, as happened in r8, and
        # then no Host-only evidence exists regardless of the mechanism.
        l2_churn = []
        for churn_pass in range(args.l2_only_churn_passes):
            l2_churn.extend(
                run_parallel(
                    args.url,
                    rows,
                    list(reversed(order)),
                    f"l2_only_churn{churn_pass}",
                    args.warm_output_tokens,
                    args.timeout,
                    out,
                    1,
                )
            )
        if l2_churn:
            write_json(out / "l2_only_churn.json", {"requests": l2_churn})
        l2_only = run_parallel(
            args.url,
            rows,
            order,
            "l2_only_probe",
            args.decode_output_tokens,
            args.timeout,
            out,
            1,
        )
        l2_evidence = parse_restore_log(args.server_log, [record["rid"] for record in l2_only])
        for record in l2_only:
            record["restore_evidence"] = l2_evidence.get(record["rid"], {})
        write_json(out / "l2_only_probe.json", {"requests": l2_only})
        attached = set_storage_backend(
            args.url,
            args.admin_api_key,
            detach=False,
            backend=args.l2_only_storage_backend
            or control_before.get("hicache_storage_backend"),
            extra_config=reattach_extra,
            # Restore whatever the service was running with unless overridden;
            # re-attaching with a different policy would silently change the
            # configuration the earlier phases were measured under.
            prefetch_policy=args.l2_only_storage_prefetch_policy
            or control_before.get("hicache_storage_prefetch_policy"),
            write_policy=args.l2_only_storage_write_policy
            or control_before.get("hicache_storage_write_policy"),
        )
        control_after = (
            storage_backend_state(args.url, args.admin_api_key)
            if attached.get("status") == 200
            else {}
        )
        storage_control = {
            "idle_confirmed": True,
            "before": control_before,
            "detach_response": detach,
            "detached": control_detached,
            "reattach_response": attached,
            "after": control_after,
        }
        write_json(out / "l2_only_storage_control.json", storage_control)
        if attached.get("status") != 200 or control_after.get(
            "hicache_storage_backend"
        ) != args.l2_only_storage_backend:
            raise SystemExit(f"L2_ONLY_PROBE_REATTACH_FAILED:{attached}:{control_after}")
        final = snapshot(args.url, out, "after_l2_only_probe", args.extent_dir)
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
        "capacity_pressure": {"count": len(pressure.get("records", [])), "success": sum(bool(item.get("ok")) for item in pressure.get("records", [])), **{key: value for key, value in pressure.items() if key != "records"}},
        "capacity_pressure_parameters": {"requested_count": args.pressure_requests, "initial_prompt_tokens": args.pressure_prompt_tokens, "maximum_prompt_tokens": args.pressure_max_prompt_tokens, "minimum_device_eviction_tokens": args.pressure_min_device_evictions, "minimum_extent_write_bytes": args.pressure_min_storage_bytes},
        "seed": phase_summary(seed, args.warm_output_tokens),
        "l1_probe": phase_summary(l1_probe, args.decode_output_tokens) if l1_probe else {"count": 0, "success": 0},
        "tier_probe": phase_summary(host_probe, args.decode_output_tokens) if host_probe else {"count": 0, "success": 0},
        "tier_probe_source_gates": {
            source: [record["rid"] for record in (l1_probe if source == "l1" and l1_probe else host_probe) if source_restore_qualified(record, source, args.decode_output_tokens)]
            for source in ("l1", "l2", "l3", "mixed")
        },
        "cold_restore_source_gates": {
            source: [record["rid"] for record in cold_l3 if source_restore_qualified(record, source, args.decode_output_tokens)]
            for source in ("l3", "mixed")
        },
        "all_stage_source_gates": {
            source: sorted({
                record["rid"]
                for record in [*host_probe, *cold_l3, *branch_probe_records, *l2_only]
                if source_restore_qualified(record, source, args.decode_output_tokens)
            })
            for source in ("l1", "l2", "l3", "mixed")
        },
        "branch_churn": phase_summary(churn_records, 1) if churn_records else {"count": 0, "success": 0},
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
        "l2_only_probe": phase_summary(l2_only, args.decode_output_tokens) if l2_only else {"count": 0, "success": 0},
        "l2_only_probe_source_gates": {
            "l2": [record["rid"] for record in l2_only if source_restore_qualified(record, "l2", args.decode_output_tokens)],
            "l3": [record["rid"] for record in l2_only if source_restore_qualified(record, "l3", args.decode_output_tokens)],
            "mixed": [record["rid"] for record in l2_only if source_restore_qualified(record, "mixed", args.decode_output_tokens)],
        },
        "l2_only_storage_control": storage_control,
        "frontier_recovery": phase_summary(frontier_records, args.decode_output_tokens) if frontier_records else {"count": 0, "success": 0},
        "frontier_recovery_qualified_rids": [record["rid"] for record in frontier_records if frontier_recovery_qualified(record, args.decode_output_tokens)],
        "flush": flush,
        "stages_requested": sorted(stages),
        "snapshots": ["before", "after_seed", "after_l1_probe", "after_capacity_pressure", "after_tier_probe", "before_frontier_recovery", "after_frontier_recovery", "after_branch_exclusive_l3", "after_cold_storage_restore", "after_l2_only_probe", "after_flush"],
        "initial_extent_files": initial["extent_files"],
        "final_extent_files": final["extent_files"],
        "completion_token_target_per_request": args.decode_output_tokens,
        "frontier_requests_configured": args.frontier_count,
        "capacity_pressure_required_device_eviction_tokens": args.pressure_min_device_evictions,
        "capacity_pressure_required_extent_bytes": args.pressure_min_storage_bytes,
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
        if source == "l1" and l1_probe:
            stage_for_source = "tier_probe"
        if source == "l2" and l2_only:
            stage_for_source = "l2_only_probe"
        # A branch-exclusive run may qualify l3 from its own records: each of
        # them must independently show an Extent read, and the per-branch gate
        # below requires all six. Keeping the cold stage in the request is not
        # required when the branch stage is the qualified evidence source.
        if (
            source in ("l3", "mixed")
            and "cold_storage_restore" not in stages
            and "branch_exclusive_l3" in stages
        ):
            stage_for_source = "branch_exclusive_l3"
        if stage_for_source not in stages:
            raise SystemExit(f"SOURCE_STAGE_NOT_REQUESTED:{source}:{stage_for_source}")
        phase_records = (
            l1_probe if source == "l1" and l1_probe
            else l2_only if source == "l2" and l2_only
            else (source_gate_host_probe or host_probe) if source in ("l1", "l2")
            else branch_probe_records if stage_for_source == "branch_exclusive_l3"
            else (cold_l3 if source in ("l3", "mixed") else host_probe)
        )
        if (
            source in ("l3", "mixed")
            and stage_for_source != "branch_exclusive_l3"
            and not any(
                source_restore_qualified(record, source, args.decode_output_tokens)
                for record in host_probe
            )
        ):
            phase_records = cold_l3
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
        if not pressure.get("records"):
            raise SystemExit("FRONTIER_RECOVERY_PRESSURE_EVIDENCE_MISSING")
        frontier_precondition = json.loads((out / "frontier_precondition.json").read_text())
        if not frontier_precondition.get("preceding_capacity_pressure"):
            raise SystemExit("FRONTIER_RECOVERY_PRECONDITION_MISSING")
        before_counters = frontier_precondition.get("tier_transfer_counters_before", {})
        after_frontier = json.loads((out / "after_frontier_recovery.snapshot.json").read_text())
        after_counters = after_frontier.get("tier_transfer_counters", {})
        if before_counters != after_counters:
            raise SystemExit("FRONTIER_STAGE_CHANGED_TRANSFER_COUNTERS_UNEXPECTEDLY")
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
        if len(recovered_records) != len(frontier_records):
            raise SystemExit("FRONTIER_RECOVERY_QUALIFICATION_INCOMPLETE")
        if not all(record.get("cached_tokens_details") for record in recovered_records):
            raise SystemExit("FRONTIER_RECOVERY_SOURCE_DETAILS_MISSING")
        if not all(
            frontier_recovery_qualified(record, args.decode_output_tokens)
            for record in recovered_records
        ):
            raise SystemExit("FRONTIER_RECOVERY_CAUSAL_GATE_FAILURE")
        if not any(record.get("restore_evidence", {}).get("frontier_wait_events") for record in recovered_records):
            raise SystemExit("FRONTIER_WAIT_NOT_OBSERVED")
        if not any(record.get("restore_evidence", {}).get("frontier_wake_events") for record in recovered_records):
            raise SystemExit("FRONTIER_WAKE_NOT_OBSERVED")
        if not any(record.get("restore_evidence", {}).get("retry_events") for record in recovered_records):
            raise SystemExit("FRONTIER_RETRY_NOT_OBSERVED")
    if args.pressure_requests and summary["capacity_pressure"]["success"] != args.pressure_requests:
        raise SystemExit("CAPACITY_PRESSURE_REQUEST_FAILURE")
    if required_sources and (required_sources & {"l1", "l2"}):
        # L1 evidence comes from tier_probe. L2 evidence may also come from the
        # dedicated l2_only_probe stage, which exists precisely because a Host
        # hit cannot show storage==0 while write-through storage is attached;
        # requiring it from tier_probe alone makes that stage useless.
        upper_tier_evidence = {
            "l1": summary["tier_probe_source_gates"].get("l1") or [],
            "l2": (
                summary["l2_only_probe_source_gates"].get("l2")
                or summary["tier_probe_source_gates"].get("l2")
                or []
            ),
        }
        if not any(upper_tier_evidence[source] for source in required_sources & {"l1", "l2"}):
            raise SystemExit("TIER_SOURCE_GATE_HAS_NO_QUALIFIED_REQUEST")
    if required_sources and any(source in required_sources for source in ("l3", "mixed")) and not any(
        summary["tier_probe_source_gates"].get(source) or summary["cold_restore_source_gates"].get(source)
        for source in required_sources & {"l3", "mixed"}
    ):
        raise SystemExit("STORAGE_SOURCE_GATE_HAS_NO_QUALIFIED_REQUEST")
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
