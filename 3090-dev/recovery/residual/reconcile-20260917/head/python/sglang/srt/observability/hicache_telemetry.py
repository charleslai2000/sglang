"""Pure HiCache request telemetry derivation.

The values collected here are observational facts owned by the scheduler/cache
path.  This module deliberately has no serving, storage, or Prometheus
dependencies so the accounting contract can be tested on CPU.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


HICACHE_TELEMETRY_SCHEMA = "hicache_request.v1"
HICACHE_PROMPT_SOURCES = (
    "l1",
    "l2",
    "l3",
    "newly_prefilled",
)
HICACHE_PARTIAL_REASONS = (
    "lifecycle_inapplicable",
    "lifecycle_missing",
    "durable_unknown",
)
HICACHE_INVALID_REASONS = (
    "attempt_mismatch",
    "generation_mismatch",
    "clock_order",
    "tier_nonconservation",
    "durable_contradiction",
)
HICACHE_STAGE_NAMES = (
    "storage_query",
    "prefetch_to_ready",
    "ready_to_admission",
    "admission_to_prefill_finish",
)
HICACHE_OUTCOMES = ("complete", "partial", "invalid")
HICACHE_LATENCY_BUCKETS = (
    0.0005,
    0.001,
    0.0025,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    20,
    40,
    80,
)


def _duration_seconds(start: Optional[int], end: Optional[int]) -> Optional[float]:
    if start is None or end is None or start > end:
        return None
    return (end - start) / 1e9


def derive_hicache_accounting(
    *,
    prompt_tokens: int,
    l1_tokens: int,
    l2_tokens: int,
    l3_tokens: int,
    durable_reusable_prefix_tokens: Optional[int],
) -> dict[str, Any]:
    """Derive the token conservation and durable-overlap formulas exactly."""
    raw_values = (prompt_tokens, l1_tokens, l2_tokens, l3_tokens)
    non_negative = all(isinstance(value, int) and value >= 0 for value in raw_values)
    cached_coverage = l1_tokens + l2_tokens + l3_tokens
    newly_prefilled_tokens = (
        prompt_tokens - cached_coverage if non_negative else None
    )
    conservation_valid = (
        non_negative
        and newly_prefilled_tokens >= 0
        and cached_coverage + newly_prefilled_tokens == prompt_tokens
    )
    if not conservation_valid:
        newly_prefilled_tokens = None
    if durable_reusable_prefix_tokens is None or not conservation_valid:
        avoidable_recompute_tokens = None
    elif not isinstance(durable_reusable_prefix_tokens, int) or durable_reusable_prefix_tokens < 0:
        avoidable_recompute_tokens = None
    else:
        avoidable_recompute_tokens = max(
            0, min(prompt_tokens, durable_reusable_prefix_tokens) - cached_coverage
        )
    return {
        "newly_prefilled_tokens": newly_prefilled_tokens,
        "avoidable_recompute_tokens": avoidable_recompute_tokens,
        "tier_conservation_valid": conservation_valid,
        "avoidable_upper_bound_valid": (
            avoidable_recompute_tokens is None
            or 0 <= avoidable_recompute_tokens <= (newly_prefilled_tokens or 0)
        ),
    }


def classify_matched_prefix_l3(proof: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify an operation-local matched-prefix proof without inferring durability."""
    if not proof:
        return {
            "matched_prefix_authority": "unknown",
            "matched_prefix_l3_tokens": None,
        }
    matched = proof.get("matched_token_boundary")
    required = (
        "request_lineage",
        "prefetch_attempt_id",
        "session_generation",
        "prompt_hash_lineage",
        "selected_anchor",
        "matched_token_boundary",
        "required_component_set",
        "per_component_durable_boundary",
        "proof_kind",
        "proof_observation_point",
    )
    if any(key not in proof or proof[key] is None for key in required):
        return {
            "matched_prefix_authority": "unknown",
            "matched_prefix_l3_tokens": None,
        }
    if not isinstance(matched, int) or matched < 0:
        return {
            "matched_prefix_authority": "unknown",
            "matched_prefix_l3_tokens": None,
        }
    kind = proof.get("proof_kind")
    boundaries = proof.get("per_component_durable_boundary")
    if kind == "root_zero" and proof.get("selected_anchor") == "root" and matched == 0:
        return {"matched_prefix_authority": "none", "matched_prefix_l3_tokens": 0}
    if kind not in {"persisted_contiguous", "joined_restore"}:
        return {"matched_prefix_authority": "unknown", "matched_prefix_l3_tokens": None}
    if not isinstance(boundaries, Mapping) or not boundaries:
        return {"matched_prefix_authority": "unknown", "matched_prefix_l3_tokens": None}
    try:
        common_boundary = min(int(value) for value in boundaries.values())
    except (TypeError, ValueError):
        return {"matched_prefix_authority": "unknown", "matched_prefix_l3_tokens": None}
    if common_boundary < matched:
        return {"matched_prefix_authority": "unknown", "matched_prefix_l3_tokens": None}
    return {
        "matched_prefix_authority": "l3_durable",
        "matched_prefix_l3_tokens": matched,
    }


def build_hicache_telemetry(req: Any) -> dict[str, Any]:
    """Build the versioned per-request object from scheduler-owned facts."""
    prompt_tokens = int(len(req.origin_input_ids))
    l1_tokens = int(getattr(req, "cached_tokens_device", 0))
    l2_tokens = int(getattr(req, "cached_tokens_host", 0))
    l3_tokens = int(getattr(req, "cached_tokens_storage", 0))
    durable = getattr(req, "hicache_durable_reusable_prefix_tokens", None)
    accounting = derive_hicache_accounting(
        prompt_tokens=prompt_tokens,
        l1_tokens=l1_tokens,
        l2_tokens=l2_tokens,
        l3_tokens=l3_tokens,
        durable_reusable_prefix_tokens=durable,
    )

    enqueue = getattr(req, "hicache_enqueue_mono_ns", None)
    issue = getattr(req, "hicache_prefetch_issue_mono_ns", None)
    query_start = getattr(req, "hicache_storage_query_start_mono_ns", None)
    query_end = getattr(req, "hicache_storage_query_end_mono_ns", None)
    ready = getattr(req, "hicache_ready_mono_ns", None)
    admission = getattr(req, "hicache_admission_mono_ns", None)
    prefill_finish = getattr(req, "hicache_prefill_finish_mono_ns", None)

    invalid_reason = getattr(req, "hicache_invalid_reason", None)
    if invalid_reason is None:
        expected_attempt = getattr(req, "hicache_prefetch_attempt_id", None)
        observed_attempt = getattr(req, "hicache_prefetch_last_attempt_id", None)
        if expected_attempt is not None and observed_attempt != expected_attempt:
            invalid_reason = "attempt_mismatch"
    if invalid_reason is None:
        operation_generation = getattr(req, "hicache_telemetry_session_generation", None)
        request_generation = getattr(req, "session_generation", None)
        if operation_generation != request_generation and operation_generation is not None:
            invalid_reason = "generation_mismatch"
    if invalid_reason is None and not accounting["tier_conservation_valid"]:
        invalid_reason = "tier_nonconservation"
    if invalid_reason is None:
        for start, end in (
            (issue, query_start),
            (query_start, query_end),
            (issue, ready),
            (ready, admission),
            (admission, prefill_finish),
        ):
            if start is not None and end is not None and start > end:
                invalid_reason = "clock_order"
                break
    matched = classify_matched_prefix_l3(
        getattr(req, "hicache_matched_prefix_l3_proof", None)
    )
    proof = getattr(req, "hicache_matched_prefix_l3_proof", None)
    if proof:
        proof_matches_request = all(
            proof.get(key) == expected
            for key, expected in (
                ("request_lineage", getattr(req, "rid", None)),
                ("prefetch_attempt_id", getattr(req, "hicache_prefetch_last_attempt_id", None)),
                ("session_generation", getattr(req, "session_generation", None)),
            )
            if expected is not None
        )
        if not proof_matches_request:
            matched = {
                "matched_prefix_authority": "unknown",
                "matched_prefix_l3_tokens": None,
            }
    matched_authority = matched["matched_prefix_authority"]
    matched_l3 = matched["matched_prefix_l3_tokens"]
    if invalid_reason is None and durable is None:
        partial_reason = "durable_unknown"
    else:
        partial_reason = None

    stage_latency_seconds = {}
    for name, start, end in (
        ("storage_query", query_start, query_end),
        ("prefetch_to_ready", issue, ready),
        ("ready_to_admission", ready, admission),
        ("admission_to_prefill_finish", admission, prefill_finish),
    ):
        duration = _duration_seconds(start, end)
        if duration is not None:
            stage_latency_seconds[name] = duration

    rh_lead = _duration_seconds(issue, admission)
    rh_slack = _duration_seconds(ready, admission)
    if invalid_reason == "clock_order":
        rh_lead = None
        rh_slack = None

    lifecycle_complete = all(
        value is not None
        for value in (enqueue, issue, ready, admission, prefill_finish)
    )
    if invalid_reason in HICACHE_INVALID_REASONS:
        outcome = "invalid"
    elif (
        lifecycle_complete
        and accounting["tier_conservation_valid"]
        and durable is not None
    ):
        outcome = "complete"
    else:
        outcome = "partial"

    if outcome == "partial" and partial_reason is None:
        partial_reason = (
            "lifecycle_inapplicable"
            if not getattr(req, "hicache_rh_eligible", False)
            else "lifecycle_missing"
        )
    if outcome == "complete":
        partial_reason = None
    if outcome == "invalid":
        partial_reason = None
    if outcome == "partial":
        invalid_reason = None

    origin = getattr(req, "hicache_prefetch_last_origin", None)
    if origin is not None:
        origin = getattr(origin, "name", str(origin))

    return {
        "schema": HICACHE_TELEMETRY_SCHEMA,
        "rh_eligible": bool(getattr(req, "hicache_rh_eligible", False)),
        "prefetch_origin": origin,
        "prefetch_attempt_id": getattr(req, "hicache_prefetch_last_attempt_id", None),
        "enqueue_mono_ns": enqueue,
        "prefetch_issue_mono_ns": issue,
        "storage_query_start_mono_ns": query_start,
        "storage_query_end_mono_ns": query_end,
        "ready_mono_ns": ready,
        "admission_mono_ns": admission,
        "prefill_finish_mono_ns": prefill_finish,
        "prompt_tokens": prompt_tokens,
        "l1_tokens": l1_tokens,
        "l2_tokens": l2_tokens,
        "l3_tokens": l3_tokens,
        "newly_prefilled_tokens": accounting["newly_prefilled_tokens"],
        "matched_prefix_tokens": getattr(req, "hicache_matched_prefix_tokens", None),
        "matched_prefix_authority": matched_authority,
        "matched_prefix_l3_tokens": matched_l3,
        "durable_reusable_prefix_tokens": durable,
        "avoidable_recompute_tokens": accounting["avoidable_recompute_tokens"],
        "completed_kv_tokens": getattr(req, "hicache_completed_kv_tokens", None),
        "required_aux_pools": list(
            getattr(req, "hicache_required_aux_pools", None) or []
        ),
        "completed_aux_units": getattr(req, "hicache_completed_aux_units", None),
        "hybrid_restore_complete": getattr(
            req, "hicache_hybrid_restore_complete", None
        ),
        "rh_prefetch_lead_seconds": rh_lead,
        "rh_ready_slack_seconds": rh_slack,
        "stage_latency_seconds": stage_latency_seconds,
        "outcome": outcome,
        "partial_reason": partial_reason,
        "invalid_reason": invalid_reason,
        "_outcome": outcome,
    }


def build_and_observe_hicache_telemetry(
    req: Any, collector: Any = None
) -> Optional[dict[str, Any]]:
    """Best-effort telemetry boundary used by the serving output path."""
    try:
        telemetry = build_hicache_telemetry(req)
    except Exception:
        return None
    if (
        getattr(req, "finished", lambda: False)()
        and not getattr(req, "hicache_prometheus_observed", False)
        and collector is not None
    ):
        try:
            collector.observe_hicache_telemetry(telemetry)
        except Exception:
            pass
        else:
            telemetry["_prometheus_observed"] = True
            req.hicache_prometheus_observed = True
    return telemetry


def public_hicache_telemetry(telemetry: Mapping[str, Any]) -> dict[str, Any]:
    """Remove the internal aggregation discriminator from JSONL output."""
    result = dict(telemetry)
    result.pop("_outcome", None)
    result.pop("_prometheus_observed", None)
    return result
