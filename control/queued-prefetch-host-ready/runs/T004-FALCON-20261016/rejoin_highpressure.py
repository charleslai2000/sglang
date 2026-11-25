#!/usr/bin/env python3
"""Rejoin only exact-run T004 high-pressure artifacts into a stage ledger."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
ARMS = [
    ("OFF", "falcon-t004-highpressure-off-20261017T235337Z"),
    ("ON", "falcon-t004-highpressure-on-20261018T005414Z"),
]

def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def main():
    result = {"schema": "t004_highpressure_stage_ledger.v1", "runs": []}
    for mode, run_id in ARMS:
        manifest = json.loads((ROOT / f"ab-{run_id}.json").read_text())
        probe = read_jsonl(ROOT / f"t38c-probe-{run_id}.jsonl")
        server_lines = (ROOT / f"server-{run_id}.log").read_text(errors="replace").splitlines()
        arm = {
            "mode": mode,
            "run_id": run_id,
            "source_head": "NOT_RECORDED_IN_RUN_MANIFEST_OR_DRIVER_LOG",
            "model_revision": manifest.get("revision"),
            "binary_sha256": "NOT_RECORDED",
            "requests": [],
        }
        for label in "ABCD":
            row = manifest["measured"][label]
            rid = row["rid"]
            events = manifest.get("per_rid_events", {}).get(rid, [])
            rid_lines = [line for line in server_lines if f"rid={rid}" in line]
            pref = [e for e in events if e.get("evt") == "pc_prefetch_enter" and e.get("origin")]
            query = next((e for e in events if e.get("evt") == "pc_storage_query"), None)
            l3_done = next((e for e in events if e.get("evt") == "pc_l3_host"), None)
            gets = [e for e in events if e.get("evt") == "pc_get_v2"]
            ready_line = next((x for x in rid_lines if "evt=ready_host " in x), None)
            admission_line = next((x for x in rid_lines if "evt=admission.v2 " in x), None)
            ready_ns = int(ready_line.split("ready_monotonic_ns=",1)[1].split()[0]) if ready_line else None
            admission_ns = int(admission_line.split("admission_monotonic_ns=",1)[1].split()[0]) if admission_line else None
            registration = next((e for e in events if e.get("evt") == "load_back_registered"), None)
            node_id = str(registration["node_id"]) if registration else None
            matching_acks = [e for e in probe if e.get("evt") == "load_back_ack_batch" and node_id and any(str(pair[0]) == node_id for pair in e.get("node_operation_ids", []))]
            meta = row["meta"]
            arrival = meta.get("request_received_ts")
            admit = meta.get("forward_entry_time")
            prefill_done = meta.get("prefill_finished_time")
            finish = meta.get("request_finished_ts")
            request = {
                "label": label, "rid": rid, "prompt_tokens": row.get("prompt_tokens"),
                "prompt_sha256": row.get("prefix_sha256"), "output_tokens": meta.get("completion_tokens"),
                "output_ids_sha256": __import__("hashlib").sha256(json.dumps(row.get("output_ids", []), separators=(",", ":")).encode()).hexdigest(),
                "cached_tokens": meta.get("cached_tokens", 0),
                "new_suffix_tokens_not_covered_by_cache": max(0, row.get("prompt_tokens", 0) - meta.get("cached_tokens", 0)),
                "arrival_epoch_s": arrival, "admission_epoch_s": admit,
                "arrival_to_admission_s": admit-arrival if arrival is not None and admit is not None else None,
                "queue_time_reported_s": meta.get("queue_time"),
                "prefetch_origin": pref[0].get("origin") if pref else None,
                "storage_query_epoch_s": query.get("ts") if query else None,
                "storage_query_hit_pages": query.get("kv_hit_pages") if query else None,
                "storage_query_sidecar_hits": query.get("sidecar_hits") if query else None,
                "pc_get_call_count": len(gets),
                "pc_get_event_span_s": max((e["ts"] for e in gets), default=None)-min((e["ts"] for e in gets), default=0) if gets else None,
                "l3_to_host_complete_epoch_s": l3_done.get("ts") if l3_done else None,
                "query_to_host_complete_event_span_s": l3_done["ts"]-query["ts"] if l3_done and query else None,
                "ready_monotonic_ns": ready_ns,
                "admission_monotonic_ns": admission_ns,
                "host_ready_to_admission_s": (admission_ns-ready_ns)/1e9 if ready_ns is not None and admission_ns is not None else None,
                "ready_observed_flag": "ready_host_observed=true" in admission_line if admission_line else None,
                "load_back_node_id": node_id,
                "h2d_ack_events_matching_node": [{"event_id": a.get("event_id"), "operation_id": next((int(p[1]) for p in a.get("node_operation_ids", []) if str(p[0]) == node_id), None), "node_operation_ids": a.get("node_operation_ids"), "ack_monotonic_ns": a.get("ts_mono_ns"), "ack_service_ms": a.get("gpu_elapsed_ms"), "bytes": a.get("num_bytes"), "bytes_by_pool": a.get("num_tokens_by_pool")} for a in matching_acks],
                "admission_to_prefill_finished_s": prefill_done-admit if prefill_done is not None and admit is not None else None,
                "prefill_finished_epoch_s": prefill_done, "request_finished_epoch_s": finish,
                "prefill_finish_to_request_finish_s": finish-prefill_done if finish is not None and prefill_done is not None else None,
                "e2e_s": meta.get("e2e_latency"),
                "first_gpu_execution": "NOT_VERIFIED: no RID-linked first GPU-step marker",
                "prefill_actual_gpu_execution_time": "NOT_VERIFIED: no per-step kernel/batch attribution",
                "decode_actual_gpu_execution_time": "NOT_VERIFIED: no per-step kernel/batch attribution",
                "gpu_disk_stall": "NOT_VERIFIED: no causal GPU-blocked-on-I/O intervals",
            }
            arm["requests"].append(request)
        # Same-run process identity in producer envelopes; avoids any cross-run joins.
        arm["producer_identity"] = manifest["per_rid_events"][manifest["measured"]["B"]["rid"]][0].get("producer") if manifest["per_rid_events"][manifest["measured"]["B"]["rid"]] else None
        result["runs"].append(arm)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
