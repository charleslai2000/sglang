#!/usr/bin/env python3
"""R115 fail-closed companion acceptance gate: durable frontier/lineage coverage.

This checker is ADDITIVE to the canonical R111 eleven-predicate oracle
(``work/R111-reducer/p0b_reducer.py``).  The R111 oracle's predicate 4 only
checks that a complete ``durability_barrier`` exists at the target's
``session_generation``.  It does NOT check that the barrier's durable lineage
actually covers the frontier the target restore requires.  This gate does.

The gate consumes only the frozen bundle's own text:

  * raw server-log lines carrying ``[HAE] {json}`` records; and
  * ``p0_durable`` JSONL records (``"trace": "p0_durable"``, written by the
    marker-gated durability producer).

Pure Python standard library.  No product imports, no monkeypatching, no
synthesis of product events, no runtime instrumentation.  Every failure mode
is fail-closed and yields a precise reason; the gate never defaults to PASS and
never trusts a bundle's own verdict/status/summary claims.

Rule (``durable_frontier_coverage``)
------------------------------------
Target identity ``T = (T_sid, T_gen, T_build)``:
  * ``T_gen`` = suffix after the last ``:`` of ``manifest["target"]
    ["lifecycle_key"]``;
  * ``T_sid``/``T_build`` = ``trace_context.session_id`` /
    ``trace_context.build_rid`` of the target's accepted
    ``restore_hybrid_finalize`` record; cross-check
    ``trace_context.session_generation == T_gen``.

Required frontier ``R``:
  * ``park`` = target ``restore_host_alloc_wait`` with ``state ==
    "WAIT_CAPACITY"`` and ``reason == "HOST_ALLOC"``;
  * ``R = park.requested_primary_tokens`` with
    ``park.positive_hit_tokens >= R > 0``;
  * cross-check the accepted finalize ``kv_expected == kv_fetched == R``.

``N_target``/``H_target``: probe ``p0_durable`` records matching ``T`` with
``evt in {residency_detach, residency_barrier_outcome}`` and non-null
``node_id``; node ids as strings, ``H_target`` their non-empty
``final_kv_hash`` values.

Barrier candidates ``B``: probe records ``evt == "durability_barrier"``
matching ``T`` with ``kv_durable is True``, ``mamba_durable is True``,
``kv_completed_tokens == kv_requested_tokens > 0``,
``mamba_expected_pages == mamba_succeeded_pages > 0``, non-empty ``node_id``
and non-empty ``final_kv_hash``.

Linked barrier: some ``b in B`` with ``b.node_id in N_target`` OR
``b.final_kv_hash in H_target``.

Covered frontier: the maximum integer ``frontier_end`` over
``storage_persisted`` probe records matching ``T`` with
``node_id in N_target``.

PASS iff a linked barrier exists AND ``covered_frontier >= R``.

Fail-closed: missing manifest target/lifecycle_key, missing accepted finalize,
missing/contradictory ``trace_context``, missing park, non-positive ``R``,
empty ``N_target``, no barrier candidate, no linked barrier, or no
``storage_persisted``-derived frontier on the target chain all yield FAIL with
a precise reason.  ``INVALID_INPUT`` (exit 2) is reserved for a structurally
unusable invocation: an unreadable/invalid manifest, a missing/unsupported
manifest ``format``, or a missing event file.

Run:

    python coverage_gate.py --events <raw.log> <probe.log> \
        --manifest <manifest.json> [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Frozen contract
# ---------------------------------------------------------------------------

RULE = "durable_frontier_coverage"
MANIFEST_FORMAT = "p0b.raw-bundle.v3"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INVALID = "INVALID_INPUT"

REASON_INSUFFICIENT_IDENTITY = "insufficient_target_identity"
REASON_INSUFFICIENT_LINEAGE = "insufficient_target_lineage"
REASON_NO_DURABLE_BARRIER = "no_durable_barrier"
REASON_NO_LINKED_BARRIER = "no_linked_barrier"
REASON_INSUFFICIENT_FRONTIER = "insufficient_frontier_evidence"
REASON_FRONTIER_BELOW_REQUIRED = "frontier_below_required"

RESIDENCY_EVENTS = frozenset({"residency_detach", "residency_barrier_outcome"})

DURABLE_TRACE = "p0_durable"


class InvalidInput(Exception):
    """The invocation itself is structurally unusable (exit 2)."""


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any) -> bool:
    return _is_int(value) and value > 0


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _lifecycle_generation(lifecycle_key: Any) -> Optional[str]:
    """``T_gen`` = suffix after the last ``:`` of the lifecycle key."""
    if not _nonempty_str(lifecycle_key) or ":" not in lifecycle_key:
        return None
    return lifecycle_key.rsplit(":", 1)[1]


def _node_id_str(value: Any) -> str:
    return value if isinstance(value, str) else str(value)


# ---------------------------------------------------------------------------
# Records and parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawRecord:
    evt: str
    fields: dict[str, Any]
    source_file: str
    source_line: int

    @property
    def source(self) -> str:
        return f"{self.source_file}:{self.source_line}"

    def v(self, name: str, default: Any = None) -> Any:
        if name in self.fields:
            return self.fields[name]
        for container in ("trace_context", "producer"):
            nested = self.fields.get(container)
            if isinstance(nested, dict) and name in nested:
                return nested[name]
        return default


def _extract_hae(text: str) -> Optional[dict[str, Any]]:
    if "[HAE] " not in text:
        return None
    payload = text.split("[HAE] ", 1)[1]
    try:
        record = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def _extract_p0_durable(text: str) -> Optional[dict[str, Any]]:
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        record = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or record.get("trace") != DURABLE_TRACE:
        return None
    return record


def parse_events(paths: list[str]) -> list[RawRecord]:
    """Parse raw ``[HAE]`` lines and ``p0_durable`` JSONL records.

    A record is kept only when it carries a non-empty ``evt``.  Files that do
    not exist are structurally unusable and raise :class:`InvalidInput`.
    """
    records: list[RawRecord] = []
    for given in paths:
        path = os.path.abspath(given)
        if not os.path.isfile(path):
            raise InvalidInput(f"raw event file is missing: {path}")
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, 1):
                text = line.rstrip("\n")
                if not text.strip():
                    continue
                record = _extract_hae(text)
                if record is None:
                    record = _extract_p0_durable(text)
                if record is None:
                    continue
                evt = record.get("evt")
                if not isinstance(evt, str) or not evt:
                    continue
                records.append(RawRecord(evt, record, path, line_number))
    return records


def load_manifest(manifest_path: str) -> dict[str, Any]:
    """Load the structural manifest; structurally unusable input is INVALID."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidInput(f"invalid provenance manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise InvalidInput("provenance manifest must be a JSON object")
    if manifest.get("format") != MANIFEST_FORMAT:
        raise InvalidInput(f"unsupported manifest format: {manifest.get('format')!r}")
    return manifest


# ---------------------------------------------------------------------------
# Evaluate the rule
# ---------------------------------------------------------------------------


def _target_view(
    rid: Any,
    lifecycle_key: Any,
    session_id: Any,
    session_generation: Any,
    build_rid: Any,
) -> dict[str, Any]:
    return {
        "rid": rid,
        "lifecycle_key": lifecycle_key,
        "session_id": session_id,
        "session_generation": session_generation,
        "build_rid": build_rid,
    }


def _barrier_view(record: RawRecord, linked: bool) -> dict[str, Any]:
    fields = record.fields
    return {
        "node_id": _node_id_str(fields.get("node_id")),
        "final_kv_hash": fields.get("final_kv_hash"),
        "kv_completed_tokens": fields.get("kv_completed_tokens"),
        "kv_requested_tokens": fields.get("kv_requested_tokens"),
        "mamba_expected_pages": fields.get("mamba_expected_pages"),
        "mamba_succeeded_pages": fields.get("mamba_succeeded_pages"),
        "linked": linked,
        "source": record.source,
    }


def _fail(result: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    result["status"] = STATUS_FAIL
    result["reason"] = reason
    result["failures"].append(detail if detail.startswith(reason) else f"{reason}: {detail}")
    return result


def _matches_target(record: RawRecord, session_id: str, generation: str, build_rid: str) -> bool:
    fields = record.fields
    if fields.get("session_id") != session_id:
        return False
    if fields.get("build_rid") != build_rid:
        return False
    generation_value = fields.get("session_generation")
    if generation_value is None or str(generation_value) != generation:
        return False
    return True


def coverage_verdict(records: list[RawRecord], manifest: dict[str, Any]) -> dict[str, Any]:
    """Apply ``durable_frontier_coverage`` and return a machine-readable verdict."""
    result: dict[str, Any] = {
        "status": STATUS_FAIL,
        "rule": RULE,
        "target": _target_view(None, None, None, None, None),
        "required_frontier": None,
        "target_restore_node_count": 0,
        "barrier_candidates": [],
        "linked_barrier": None,
        "covered_frontier": None,
        "reason": None,
        "failures": [],
    }

    target_cfg = manifest.get("target")
    if not isinstance(target_cfg, dict):
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "manifest target binding is missing",
        )
    lifecycle_key = target_cfg.get("lifecycle_key")
    rid = target_cfg.get("rid")
    if not _nonempty_str(lifecycle_key):
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "manifest target.lifecycle_key is missing",
        )
    generation = _lifecycle_generation(lifecycle_key)
    if generation is None:
        result["target"] = _target_view(rid, lifecycle_key, None, None, None)
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            f"lifecycle_key has no generation suffix: {lifecycle_key!r}",
        )

    # -- accepted finalize -> T_sid / T_build ---------------------------------
    finalize: Optional[RawRecord] = None
    for record in records:
        if (
            record.evt == "restore_hybrid_finalize"
            and record.fields.get("result") == "accepted"
            and record.fields.get("lifecycle_key") == lifecycle_key
        ):
            finalize = record
            break
    if finalize is None:
        result["target"] = _target_view(rid, lifecycle_key, None, generation, None)
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "no accepted restore_hybrid_finalize for the target lifecycle_key",
        )

    trace_context = finalize.fields.get("trace_context")
    if not isinstance(trace_context, dict):
        result["target"] = _target_view(rid, lifecycle_key, None, generation, None)
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "accepted finalize trace_context is missing",
        )
    session_id = trace_context.get("session_id")
    build_rid = trace_context.get("build_rid")
    trace_generation = trace_context.get("session_generation")
    if not _nonempty_str(session_id) or not _nonempty_str(build_rid):
        result["target"] = _target_view(rid, lifecycle_key, session_id, generation, build_rid)
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "accepted finalize trace_context lacks session_id/build_rid",
        )
    if trace_generation is None or str(trace_generation) != generation:
        result["target"] = _target_view(rid, lifecycle_key, session_id, generation, build_rid)
        return _fail(
            result,
            REASON_INSUFFICIENT_IDENTITY,
            "trace_context.session_generation does not match lifecycle_key generation: "
            f"{trace_generation!r} != {generation!r}",
        )

    result["target"] = _target_view(rid, lifecycle_key, session_id, generation, build_rid)

    # -- required frontier from the target park -------------------------------
    park: Optional[RawRecord] = None
    for record in records:
        if (
            record.evt == "restore_host_alloc_wait"
            and record.fields.get("state") == "WAIT_CAPACITY"
            and record.fields.get("reason") == "HOST_ALLOC"
            and record.fields.get("lifecycle_key") == lifecycle_key
        ):
            park = record
            break
    if park is None:
        return _fail(
            result,
            REASON_INSUFFICIENT_LINEAGE,
            "no target restore_host_alloc_wait park (WAIT_CAPACITY/HOST_ALLOC)",
        )
    required = park.fields.get("requested_primary_tokens")
    positive_hit = park.fields.get("positive_hit_tokens")
    if not _positive_int(required):
        return _fail(
            result,
            REASON_INSUFFICIENT_LINEAGE,
            f"park.requested_primary_tokens is not positive: {required!r}",
        )
    if not _is_int(positive_hit) or positive_hit < required:
        return _fail(
            result,
            REASON_INSUFFICIENT_LINEAGE,
            f"park.positive_hit_tokens ({positive_hit!r}) < required frontier ({required!r})",
        )
    kv_expected = finalize.fields.get("kv_expected")
    kv_fetched = finalize.fields.get("kv_fetched")
    if not (_is_int(kv_expected) and kv_expected == required and kv_fetched == required):
        return _fail(
            result,
            REASON_INSUFFICIENT_LINEAGE,
            "accepted finalize kv_expected/kv_fetched do not equal the required frontier: "
            f"kv_expected={kv_expected!r} kv_fetched={kv_fetched!r} required={required!r}",
        )
    result["required_frontier"] = required

    # -- target restore node set ----------------------------------------------
    n_target: set[str] = set()
    h_target: set[str] = set()
    for record in records:
        if record.evt not in RESIDENCY_EVENTS:
            continue
        if not _matches_target(record, session_id, generation, build_rid):
            continue
        if record.fields.get("node_id") is None:
            continue
        n_target.add(_node_id_str(record.fields.get("node_id")))
        final_kv_hash = record.fields.get("final_kv_hash")
        if _nonempty_str(final_kv_hash):
            h_target.add(final_kv_hash)
    result["target_restore_node_count"] = len(n_target)
    if not n_target:
        return _fail(
            result,
            REASON_INSUFFICIENT_LINEAGE,
            "no residency_detach/residency_barrier_outcome rows for the target identity",
        )

    # -- barrier candidates ---------------------------------------------------
    candidates: list[RawRecord] = []
    for record in records:
        if record.evt != "durability_barrier":
            continue
        if not _matches_target(record, session_id, generation, build_rid):
            continue
        fields = record.fields
        if fields.get("kv_durable") is not True or fields.get("mamba_durable") is not True:
            continue
        completed = fields.get("kv_completed_tokens")
        requested = fields.get("kv_requested_tokens")
        if not (_positive_int(completed) and completed == requested):
            continue
        expected_pages = fields.get("mamba_expected_pages")
        succeeded_pages = fields.get("mamba_succeeded_pages")
        if not (_positive_int(expected_pages) and expected_pages == succeeded_pages):
            continue
        if fields.get("node_id") is None or not _nonempty_str(fields.get("final_kv_hash")):
            continue
        candidates.append(record)

    linked: Optional[RawRecord] = None
    for candidate in candidates:
        node = _node_id_str(candidate.fields.get("node_id"))
        if node in n_target or candidate.fields.get("final_kv_hash") in h_target:
            linked = candidate
            break
    result["barrier_candidates"] = [
        _barrier_view(candidate, linked=candidate is linked) for candidate in candidates
    ]
    if not candidates:
        return _fail(
            result,
            REASON_NO_DURABLE_BARRIER,
            "no complete durability_barrier candidate at the target identity",
        )
    if linked is None:
        return _fail(
            result,
            REASON_NO_LINKED_BARRIER,
            "no barrier candidate node/hash is on the target restore chain",
        )
    result["linked_barrier"] = _barrier_view(linked, linked=True)

    # -- covered frontier from storage_persisted on the target chain ----------
    covered: Optional[int] = None
    for record in records:
        if record.evt != "storage_persisted":
            continue
        if not _matches_target(record, session_id, generation, build_rid):
            continue
        if _node_id_str(record.fields.get("node_id")) not in n_target:
            continue
        frontier_end = record.fields.get("frontier_end")
        if not _is_int(frontier_end):
            continue
        covered = frontier_end if covered is None else max(covered, frontier_end)
    result["covered_frontier"] = covered
    if covered is None:
        return _fail(
            result,
            REASON_INSUFFICIENT_FRONTIER,
            "no storage_persisted frontier_end on the target restore chain",
        )
    if covered < required:
        return _fail(
            result,
            REASON_FRONTIER_BELOW_REQUIRED,
            f"covered frontier {covered} < required {required}",
        )

    result["status"] = STATUS_PASS
    result["reason"] = None
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(event_paths: list[str], manifest_path: str) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    records = parse_events(event_paths)
    return coverage_verdict(records, manifest)


def _invalid_result(message: str) -> dict[str, Any]:
    return {
        "status": STATUS_INVALID,
        "rule": RULE,
        "target": _target_view(None, None, None, None, None),
        "required_frontier": None,
        "target_restore_node_count": 0,
        "barrier_candidates": [],
        "linked_barrier": None,
        "covered_frontier": None,
        "reason": message,
        "failures": [message],
    }


def _human_line(result: dict[str, Any]) -> str:
    target = result["target"]
    barrier = result.get("linked_barrier")
    linked_node = barrier.get("node_id") if isinstance(barrier, dict) else None
    parts = [
        f"{result['status']} rule={result['rule']}",
        f"target_sid={target.get('session_id')}",
        f"target_gen={target.get('session_generation')}",
        f"target_build={target.get('build_rid')}",
        f"required_frontier={result.get('required_frontier')}",
        f"covered_frontier={result.get('covered_frontier')}",
        f"barrier_candidates={len(result.get('barrier_candidates', []))}",
        f"linked_barrier_node={linked_node}",
        f"reason={result.get('reason')}",
    ]
    return " ".join(parts)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", nargs="+", required=True, help="raw + probe bundle files")
    parser.add_argument("--manifest", required=True, help="raw-provenance manifest JSON")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON verdict")
    args = parser.parse_args(argv)

    try:
        result = run(list(args.events), args.manifest)
    except InvalidInput as exc:
        result = _invalid_result(str(exc))

    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_human_line(result))

    if result["status"] == STATUS_PASS:
        return 0
    if result["status"] == STATUS_INVALID:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
