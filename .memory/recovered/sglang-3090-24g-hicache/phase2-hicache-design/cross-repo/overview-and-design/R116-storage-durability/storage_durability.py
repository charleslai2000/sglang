#!/usr/bin/env python3
"""R116 storage-backed durability reducer (offline, stdlib-only, fail-closed).

This is a NEW additive reducer.  It does NOT modify or import the R111/R115
reducers.  It re-judges the FROZEN R114 bundle (raw.log + probe.log +
manifest.json) together with the FROZEN L3 evidence (l3-evidence.json plus the
frozen ``objects/<key>.bin`` copies) and exits 0 only when every one of the
eight predicates below holds.

Why a new reducer: the user ruled (A') that R111's predicate 4
(``durability_barrier`` matching only ``session_generation``) is insufficient --
a small early barrier can be mistaken for proof that the whole target restore
prefix is durable.  R116 therefore requires the target prefix's REAL durable
storage coverage plus an actual restore, joined on the full target identity:

  1. identity_consistency
  2. kv_prefix_coverage
  3. durable_object_existence
  4. durable_write_then_restore
  5. mamba_sidecar_durable
  6. l3_to_host_completed
  7. finalize_consumed_restore
  8. negative_safety

Guarantees / non-goals
----------------------
* No product imports, no server interaction, no live calls, no instrumentation,
  no synthetic events injected into a live path.  Pure standard-library parsing
  of captured text.
* Fail closed: exit ``1`` on any predicate failure, exit ``2`` on structurally
  invalid input.  A missing required record is a FAIL, never a pass.
* The reducer never trusts a bundle's own ``oracle``/``verdict``/``status``/
  ``summary`` claims.

Exit codes: ``0`` = STORAGE_DURABILITY PASS, ``1`` = FAIL, ``2`` = INVALID_INPUT.

CLI::

    python storage_durability.py --raw <raw.log> --probe <probe.log> \
        --manifest <manifest.json> --l3-evidence <l3-evidence.json> [--json]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Frozen contract
# ---------------------------------------------------------------------------

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INVALID = "INVALID_INPUT"

RULE = "R116 storage-backed durability reducer"

MANIFEST_FORMAT = "p0b.raw-bundle.v3"
DURABLE_TRACE = "p0_durable"

PREDICATE_NAMES: tuple[str, ...] = (
    "identity_consistency",
    "kv_prefix_coverage",
    "durable_object_existence",
    "durable_write_then_restore",
    "mamba_sidecar_durable",
    "l3_to_host_completed",
    "finalize_consumed_restore",
    "negative_safety",
)

# p0_durable events that carry a positive mamba durability acknowledgement.
DURABLE_ACK_EVENTS = frozenset({"backup_ack_drain", "durability_barrier"})

# Tokens that mark a full-prefix recompute or a hybrid discard.  Matched
# case-insensitively against the narrow set of fields the producer uses.
RECOMPUTE_DISCARD_TOKENS: tuple[str, ...] = (
    "recompute",
    "discard",
    "abandon",
    "no_l3",
    "miss_recompute",
)

# Terminal ``restore_disposition`` values that denote a discarded/recomputed
# hybrid.  ``WAIT``/``PARTIAL``/``COMPLETE`` are legitimate restore outcomes.
DISPOSITION_DISCARD = frozenset(
    {
        "discard",
        "discarded",
        "recompute",
        "miss_recompute",
        "no_l3",
        "abandoned",
        "aborted",
    }
)

# Raw [P3]/[P2A] key=value events we need to parse for the target identity and
# the recompute/discard safety scan.  Everything else is skipped for speed and
# because it carries no predicate evidence.
INTERESTING_KV_EVENTS = frozenset(
    {
        "restore_disposition",
        "restore_state",
        "restore_recompute",
        "rh_match_prepare",
        "ready_stage",
        "ready_host",
    }
)

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_KV_SPLIT_RE = re.compile(r"\s+(?=[A-Za-z_][A-Za-z0-9_]*=)")
_EVT_RE = re.compile(r"\bevt=([A-Za-z0-9_.]+)")
_KEY_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_INT_RE = re.compile(r"^-?\d+$")


class InvalidInput(Exception):
    """Structural input failure -> exit code 2 (INVALID_INPUT)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _positive_int(value: Any) -> bool:
    return _is_int(value) and value > 0


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json_list(value: Any) -> str:
    """SHA256 of ``json.dumps(value)`` (the producer's key-set digest)."""
    return hashlib.sha256(json.dumps(value).encode("utf-8")).hexdigest()


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text in ("None", "null"):
        return None
    if text == "True":
        return True
    if text == "False":
        return False
    if _INT_RE.fullmatch(text):
        return int(text)
    if text[:1] in ("{", "["):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
    return text


# ---------------------------------------------------------------------------
# Raw record model / parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Record:
    source: str  # absolute-file:line reference
    kind: str  # "hae" | "p3" | "p2a" | "probe"
    evt: str
    fields: dict

    def v(self, name: str, default: Any = None) -> Any:
        """Field lookup, descending into ``producer`` / ``trace_context``."""
        if name in self.fields:
            return self.fields[name]
        for container in ("producer", "trace_context"):
            nested = self.fields.get(container)
            if isinstance(nested, dict) and name in nested:
                return nested[name]
        return default

    def rid(self) -> Any:
        return self.fields.get("rid")


def _parse_kv_fields(line: str) -> dict:
    """Parse a ``[P3]`` / ``[P2A]`` key=value line.

    Splitting only on whitespace directly preceding a ``key=`` token keeps
    bracketed/dict reprs with internal spaces intact (mirrors R111's
    ``_parse_ready_kv_line`` convention; no import).
    """
    marker = line.find("] ")
    payload = line[marker + 2 :] if marker >= 0 else line
    fields: dict[str, Any] = {}
    for token in _KV_SPLIT_RE.split(payload.rstrip("\n")):
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        key = key.strip()
        if _KEY_IDENT_RE.fullmatch(key):
            fields[key] = _parse_scalar(value)
    return fields


def parse_raw(path: str) -> tuple[list[Record], list[str]]:
    """Parse ``[HAE] {json}`` records and the interesting ``[P3]``/``[P2A]`` lines."""
    records: list[Record] = []
    errors: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            if "[HAE] " in line:
                payload = line.split("[HAE] ", 1)[1]
                try:
                    record = json.loads(payload)
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid [HAE] JSON at {path}:{line_number}: {exc}")
                    continue
                if not isinstance(record, dict):
                    errors.append(f"[HAE] record not an object at {path}:{line_number}")
                    continue
                records.append(
                    Record(
                        f"{path}:{line_number}",
                        "hae",
                        str(record.get("evt")),
                        record,
                    )
                )
            elif "[P3] " in line or "[P2A] " in line:
                match = _EVT_RE.search(line)
                if not match:
                    continue
                evt = match.group(1)
                if evt not in INTERESTING_KV_EVENTS:
                    continue
                fields = _parse_kv_fields(line)
                records.append(
                    Record(
                        f"{path}:{line_number}",
                        "p3" if "[P3] " in line else "p2a",
                        evt,
                        fields,
                    )
                )
    return records, errors


def parse_probe(path: str) -> tuple[list[Record], list[str]]:
    """Parse the probe JSONL (``pc_*`` events and ``p0_durable`` records)."""
    records: list[Record] = []
    errors: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid probe JSON at {path}:{line_number}: {exc}")
                continue
            if not isinstance(record, dict):
                continue
            records.append(
                Record(
                    f"{path}:{line_number}",
                    "probe",
                    str(record.get("evt")),
                    record,
                )
            )
    return records, errors


# ---------------------------------------------------------------------------
# Input gate
# ---------------------------------------------------------------------------


def _load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidInput(f"cannot read {path}: {exc}") from exc


def _validate_manifest(manifest: Any, raw_path: str, probe_path: str) -> None:
    if not isinstance(manifest, dict):
        raise InvalidInput("manifest is not a JSON object")
    if manifest.get("format") != MANIFEST_FORMAT:
        raise InvalidInput(f"unsupported manifest format: {manifest.get('format')!r}")
    target = manifest.get("target")
    if not isinstance(target, dict):
        raise InvalidInput("manifest.target is missing")
    if not _nonempty_str(target.get("rid")):
        raise InvalidInput("manifest.target.rid is missing")
    if not _nonempty_str(target.get("lifecycle_key")):
        raise InvalidInput("manifest.target.lifecycle_key is missing")

    raw_files = manifest.get("raw_files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise InvalidInput("manifest.raw_files is missing")
    requested = {os.path.abspath(raw_path), os.path.abspath(probe_path)}
    for name, digest in raw_files.items():
        if not (isinstance(name, str) and os.path.isabs(name)):
            raise InvalidInput(f"raw_files key is not an absolute path: {name!r}")
        if not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
            raise InvalidInput(f"raw_files digest is not SHA256: {name!r}")
    for path in sorted(requested):
        if path not in raw_files:
            raise InvalidInput(f"input path is not bound by raw_files: {path}")
    for name, digest in raw_files.items():
        if not os.path.isfile(name):
            raise InvalidInput(f"raw file is missing: {name}")
        if _sha256_file(name) != digest.lower():
            raise InvalidInput(f"raw file hash mismatch: {name}")


def _validate_l3_evidence(l3: Any) -> None:
    if not isinstance(l3, dict):
        raise InvalidInput("l3 evidence is not a JSON object")
    target = l3.get("target")
    if not isinstance(target, dict):
        raise InvalidInput("l3-evidence.target is missing")
    for name in ("rid", "session_id", "build_rid"):
        if not _nonempty_str(target.get(name)):
            raise InvalidInput(f"l3-evidence.target.{name} is missing")
    if target.get("session_generation") is None:
        raise InvalidInput("l3-evidence.target.session_generation is missing")
    if not _positive_int(target.get("prefix_tokens")):
        raise InvalidInput("l3-evidence.target.prefix_tokens is missing")
    if not _nonempty_str(l3.get("key_set_sha256")):
        raise InvalidInput("l3-evidence.key_set_sha256 is missing")
    objects = l3.get("objects")
    if not isinstance(objects, list) or not objects:
        raise InvalidInput("l3-evidence.objects is missing or empty")


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


def _detect_recompute_discard(
    records: list[Record], target_rid: str, lifecycle_key: str
) -> list[str]:
    """Return named findings for any target recompute / hybrid-discard path."""
    findings: list[str] = []
    for record in records:
        is_target = (
            record.fields.get("rid") == target_rid
            or record.fields.get("lifecycle_key") == lifecycle_key
            or record.fields.get("warm_rid") == target_rid
        )
        if not is_target:
            continue
        evt = record.evt
        if evt == "restore_recompute":
            findings.append(f"{record.source} target restore_recompute")
            continue
        if evt == "restore_disposition":
            disposition = str(record.fields.get("disposition", "")).lower()
            if disposition in DISPOSITION_DISCARD or any(
                token in disposition for token in RECOMPUTE_DISCARD_TOKENS
            ):
                findings.append(
                    f"{record.source} restore_disposition="
                    f"{record.fields.get('disposition')!r} indicates recompute/discard"
                )
            continue
        if evt in ("restore_state", "rh_match_prepare", "ready_stage"):
            if record.fields.get("negative_cache_blocked") is True:
                findings.append(f"{record.source} {evt} negative_cache_blocked=True")
            blob = " ".join(
                str(record.fields.get(name, ""))
                for name in (
                    "result",
                    "reason",
                    "state",
                    "restore_state_before",
                    "restore_state_after",
                )
            ).lower()
            for token in RECOMPUTE_DISCARD_TOKENS:
                if token in blob:
                    findings.append(f"{record.source} {evt} indicates {token}")
                    break
            continue
        blob = " ".join(
            str(record.fields.get(name, ""))
            for name in ("result", "disposition", "state", "outcome")
        ).lower()
        for token in RECOMPUTE_DISCARD_TOKENS:
            if token in blob:
                findings.append(f"{record.source} {evt} indicates {token}")
                break
    return findings


def judge(
    manifest: dict,
    l3: dict,
    raw: list[Record],
    probe: list[Record],
    parse_errors: list[str],
    l3_path: str,
) -> dict:
    predicates: list[dict] = []
    failures: list[str] = []
    def mark(name: str, passed: bool, reason: str) -> None:
        predicates.append({"name": name, "passed": bool(passed), "reason": reason})
        if not passed:
            failures.append(f"{name}: {reason}")

    evidence_dir = os.path.dirname(os.path.abspath(l3_path))
    # ---- derive target identity T (from frozen evidence only) --------------
    t_rid = manifest["target"]["rid"]
    lifecycle_key = manifest["target"]["lifecycle_key"]
    t_gen = lifecycle_key.rsplit(":", 1)[1] if ":" in lifecycle_key else None
    target_parks = [
        r
        for r in raw
        if r.evt == "restore_host_alloc_wait"
        and r.fields.get("rid") == t_rid
        and r.fields.get("lifecycle_key") == lifecycle_key
    ]
    park = next(
        (
            r
            for r in target_parks
            if r.fields.get("state") == "WAIT_CAPACITY"
            and r.fields.get("reason") == "HOST_ALLOC"
        ),
        target_parks[0] if target_parks else None,
    )
    t_prefix = None
    if park is not None:
        requested = park.fields.get("requested_primary_tokens")
        positive = park.fields.get("positive_hit_tokens")
        if _positive_int(requested) and requested == positive:
            t_prefix = requested
    finalizes = [
        r
        for r in raw
        if r.evt == "restore_hybrid_finalize"
        and r.fields.get("lifecycle_key") == lifecycle_key
    ]
    finalize = next(
        (r for r in finalizes if r.fields.get("result") == "accepted"),
        finalizes[0] if finalizes else None,
    )
    t_sid = None
    t_build = None
    finalize_contradictions: list[str] = []
    if finalize is not None:
        trace_context = finalize.fields.get("trace_context")
        if isinstance(trace_context, dict):
            t_sid = trace_context.get("session_id")
            t_build = trace_context.get("build_rid")
            generation = trace_context.get("session_generation")
            if t_gen is not None and str(generation) != t_gen:
                finalize_contradictions.append(
                    "finalize trace_context.session_generation="
                    f"{generation!r} != manifest target generation {t_gen!r}"
                )

    target_meta = {
        "rid": t_rid,
        "session_id": t_sid,
        "session_generation": t_gen,
        "build_rid": t_build,
        "prefix_tokens": t_prefix,
    }
    # ---- target probe records ---------------------------------------------
    target_probe = [r for r in probe if r.fields.get("rid") == t_rid]
    restore_queries = [
        r for r in target_probe if r.evt == "pc_storage_query"
    ]
    restore_query = (
        max(
            restore_queries,
            key=lambda r: r.fields.get("kv_hit_pages")
            if _is_int(r.fields.get("kv_hit_pages"))
            else -1,
        )
        if restore_queries
        else None
    )
    restore_keys = restore_query.fields.get("keys") if restore_query else None

    l3_target = l3.get("target") if isinstance(l3.get("target"), dict) else {}
    join_contradictions: list[str] = list(finalize_contradictions)
    # ==== predicate 1: identity_consistency ================================
    identity_problems: list[str] = []
    if park is None:
        identity_problems.append("target restore_host_alloc_wait not found")
    else:
        requested = park.fields.get("requested_primary_tokens")
        positive = park.fields.get("positive_hit_tokens")
        if not (_positive_int(requested) and requested == positive):
            identity_problems.append(
                "target park requested_primary_tokens != positive_hit_tokens > 0"
            )
    if finalize is None:
        identity_problems.append("accepted target restore_hybrid_finalize not found")
    else:
        if not _nonempty_str(t_sid):
            identity_problems.append("finalize trace_context.session_id missing")
        if not _nonempty_str(t_build):
            identity_problems.append("finalize trace_context.build_rid missing")
        identity_problems.extend(finalize_contradictions)
    l3_checks = (
        ("rid", t_rid),
        ("session_id", t_sid),
        ("session_generation", t_gen),
        ("build_rid", t_build),
        ("prefix_tokens", t_prefix),
    )
    for name, expected in l3_checks:
        got = l3_target.get(name)
        if expected is None or str(got) != str(expected):
            message = (
                f"l3-evidence.target.{name}={got!r} != target {expected!r}"
            )
            identity_problems.append(message)
            join_contradictions.append(message)
    if not restore_queries:
        identity_problems.append("no target pc_storage_query (rid==target rid)")
    for record in target_probe:
        for name, expected in (
            ("session_id", t_sid),
            ("build_rid", t_build),
            ("session_generation", t_gen),
        ):
            if name in record.fields and record.fields.get(name) is not None:
                if expected is None or str(record.fields.get(name)) != str(expected):
                    message = (
                        f"{record.source} {name}={record.fields.get(name)!r} "
                        f"!= target {expected!r}"
                    )
                    identity_problems.append(message)
                    join_contradictions.append(message)
    mark(
        "identity_consistency",
        not identity_problems,
        "target identity consistent across park/finalize/probe/l3-evidence"
        if not identity_problems
        else "; ".join(dict.fromkeys(identity_problems)),
    )
    # ==== predicate 2: kv_prefix_coverage ==================================
    coverage_problems: list[str] = []
    if restore_query is None:
        coverage_problems.append("no target restore pc_storage_query")
    else:
        hits = restore_query.fields.get("kv_hit_pages")
        storage = restore_query.fields.get("storage_hit_count")
        suffix = restore_query.fields.get("query_suffix_len")
        if hits != t_prefix:
            coverage_problems.append(
                f"restore pc_storage_query kv_hit_pages={hits!r} != T_prefix {t_prefix!r}"
            )
        if storage != t_prefix:
            coverage_problems.append(
                f"restore pc_storage_query storage_hit_count={storage!r} "
                f"!= T_prefix {t_prefix!r}"
            )
        if not (_is_int(suffix) and _is_int(t_prefix) and suffix >= t_prefix):
            coverage_problems.append(
                f"restore pc_storage_query query_suffix_len={suffix!r} < T_prefix"
            )
    for record in restore_queries:
        hits = record.fields.get("kv_hit_pages")
        if _is_int(hits) and _is_int(t_prefix) and hits != t_prefix and hits != 0:
            coverage_problems.append(
                f"target pc_storage_query {record.source} has partial "
                f"kv_hit_pages={hits}"
            )
    kv_batches = [
        r
        for r in target_probe
        if r.evt == "pc_get_v2" and r.fields.get("sidecar") == "kv"
    ]
    if not kv_batches:
        coverage_problems.append("no target kv_batch pc_get_v2 records")
    batch_sum = 0
    for record in kv_batches:
        n_keys = record.fields.get("n_keys")
        kv_hits = record.fields.get("kv_hits")
        if not (_is_int(n_keys) and _is_int(kv_hits)):
            coverage_problems.append(
                f"{record.source} kv_batch missing integer n_keys/kv_hits"
            )
            continue
        batch_sum += kv_hits
        if n_keys != kv_hits:
            coverage_problems.append(
                f"{record.source} n_keys={n_keys} != kv_hits={kv_hits} (missing pages)"
            )
    if _is_int(t_prefix) and batch_sum != t_prefix:
        coverage_problems.append(
            f"sum(pc_get_v2.kv_hits)={batch_sum} != T_prefix {t_prefix}"
        )
    mark(
        "kv_prefix_coverage",
        not coverage_problems,
        f"kv_hit_pages==storage_hit_count==T_prefix ({t_prefix}) and read-path "
        f"kv_hits sum matches"
        if not coverage_problems
        else "; ".join(dict.fromkeys(coverage_problems)),
    )
    # ==== predicate 3: durable_object_existence ============================
    object_problems: list[str] = []
    if restore_query is None or not isinstance(restore_keys, list) or not all(
        _nonempty_str(key) for key in restore_keys
    ):
        object_problems.append("target restore query key set is missing")
    else:
        want_digest = _sha256_json_list(restore_keys)
        if l3.get("key_set_sha256") != want_digest:
            object_problems.append(
                f"l3-evidence.key_set_sha256={l3.get('key_set_sha256')!r} != "
                f"sha256(restore keys)={want_digest!r}"
            )
        object_keys: list[str] = []
        objects = l3.get("objects")
        if not isinstance(objects, list):
            object_problems.append("l3-evidence.objects is not a list")
            objects = []
        for index, entry in enumerate(objects):
            if not isinstance(entry, dict):
                object_problems.append(f"l3-evidence.objects[{index}] is not an object")
                continue
            key = entry.get("key")
            if not _nonempty_str(key):
                object_problems.append(f"l3-evidence.objects[{index}].key is missing")
                continue
            object_keys.append(key)
            expected_path = os.path.join(evidence_dir, "objects", f"{key}.bin")
            frozen_copy = entry.get("frozen_copy")
            if _nonempty_str(frozen_copy):
                resolved = os.path.normpath(os.path.join(evidence_dir, frozen_copy))
                if resolved != os.path.normpath(expected_path):
                    object_problems.append(
                        f"objects[{index}].frozen_copy={frozen_copy!r} != objects/{key}.bin"
                    )
            if not os.path.isfile(expected_path):
                object_problems.append(f"frozen object missing: objects/{key}.bin")
                continue
            try:
                actual_size = os.path.getsize(expected_path)
            except OSError as exc:
                object_problems.append(f"frozen object unreadable: objects/{key}.bin: {exc}")
                continue
            if actual_size <= 0:
                object_problems.append(f"frozen object is empty: objects/{key}.bin")
                continue
            recorded_sha = entry.get("sha256")
            if not (isinstance(recorded_sha, str) and _HEX64.fullmatch(recorded_sha)):
                object_problems.append(
                    f"objects[{index}].sha256 is missing/invalid for key {key}"
                )
                continue
            if _sha256_file(expected_path) != recorded_sha.lower():
                object_problems.append(
                    f"frozen object hash mismatch: objects/{key}.bin"
                )
            recorded_size = entry.get("size")
            if _is_int(recorded_size) and recorded_size != actual_size:
                object_problems.append(
                    f"frozen object size mismatch: objects/{key}.bin "
                    f"recorded={recorded_size} actual={actual_size}"
                )
        if isinstance(restore_keys, list) and set(object_keys) != set(restore_keys):
            object_problems.append(
                "l3-evidence object key set != target restore key set"
            )
        if _is_int(l3.get("key_count")) and isinstance(objects, list) and l3[
            "key_count"
        ] != len(objects):
            object_problems.append("l3-evidence.key_count != len(objects)")
    mark(
        "durable_object_existence",
        not object_problems,
        "every enumerated target object exists, is non-empty, and matches its "
        "recorded sha256; key-set digest matches the restore query"
        if not object_problems
        else "; ".join(dict.fromkeys(object_problems)),
    )
    # ==== predicate 4: durable_write_then_restore ==========================
    causality_problems: list[str] = []
    if restore_query is None or not isinstance(restore_keys, list):
        causality_problems.append("no target restore query to join against")
    else:
        restore_hits = restore_query.fields.get("kv_hit_pages")
        if restore_hits != t_prefix:
            causality_problems.append(
                f"restore query kv_hit_pages={restore_hits!r} != T_prefix {t_prefix!r}"
            )
        # The build-time query is identified by the SAME key-set as the target
        # restore query with kv_hit_pages==0 under a DIFFERENT rid.  In the
        # frozen R114 evidence this is the warm/build record rid
        # ``25dd9122...`` (key-set identical to the target restore query),
        # which is distinct from both T_rid and the finalize trace_context
        # build_rid; the spec keys the causal join on "different rid", not on
        # the trace_context build_rid.
        build_queries = [
            r
            for r in probe
            if r.evt == "pc_storage_query"
            and r.fields.get("rid") != t_rid
            and r.fields.get("keys") == restore_keys
            and r.fields.get("kv_hit_pages") == 0
        ]
        if not build_queries:
            causality_problems.append(
                "no build-time pc_storage_query (different rid) with the same "
                "key-set and kv_hit_pages==0"
            )
    mark(
        "durable_write_then_restore",
        not causality_problems,
        "same target key-set observed absent (kv_hit_pages==0 at build rid) then "
        "fully durable at restore rid"
        if not causality_problems
        else "; ".join(dict.fromkeys(causality_problems)),
    )
    # ==== predicate 5: mamba_sidecar_durable ===============================
    mamba_problems: list[str] = []
    acks = [
        r
        for r in probe
        if r.evt in DURABLE_ACK_EVENTS
        and _nonempty_str(t_sid)
        and r.v("session_id") == t_sid
        and str(r.v("session_generation")) == str(t_gen)
        and r.v("build_rid") == t_build
        and r.fields.get("mamba_durable") is True
    ]
    if not acks:
        mamba_problems.append(
            "no p0_durable durable-ACK (backup_ack_drain/durability_barrier) with "
            "mamba_durable=True for the target session/generation/build"
        )
    sidecars = None
    if finalize is not None:
        sidecars = finalize.fields.get("sidecars")
        if not isinstance(sidecars, dict):
            sidecars = finalize.fields.get("per_sidecar")
    mamba_sidecar = sidecars.get("mamba") if isinstance(sidecars, dict) else None
    if not (
        isinstance(mamba_sidecar, dict)
        and mamba_sidecar.get("expected") == 1
        and mamba_sidecar.get("fetched") == 1
    ):
        mamba_problems.append("finalize sidecars.mamba.expected/fetched != 1")
    if restore_query is None:
        mamba_problems.append("no target restore query sidecar_hits")
    else:
        sidecar_hits = restore_query.fields.get("sidecar_hits")
        mamba_hits = (
            sidecar_hits.get("mamba") if isinstance(sidecar_hits, dict) else None
        )
        if not (_is_int(mamba_hits) and mamba_hits > 0):
            mamba_problems.append(
                "target restore sidecar_hits.mamba is not a positive int"
            )
    mark(
        "mamba_sidecar_durable",
        not mamba_problems,
        "durable mamba ACK for target identity AND finalize mamba 1/1 AND "
        "restore sidecar_hits.mamba positive"
        if not mamba_problems
        else "; ".join(dict.fromkeys(mamba_problems)),
    )
    # ==== predicate 6: l3_to_host_completed ================================
    l3_host_problems: list[str] = []
    l3_hosts = [r for r in target_probe if r.evt == "pc_l3_host"]
    if not l3_hosts:
        l3_host_problems.append("no target pc_l3_host record")
    else:
        satisfied = False
        for record in l3_hosts:
            completed = record.fields.get("completed_tokens")
            requested = record.fields.get("requested_tokens")
            if (
                completed == t_prefix
                and _is_int(requested)
                and _is_int(t_prefix)
                and requested >= t_prefix
            ):
                satisfied = True
        if not satisfied:
            l3_host_problems.append(
                "target pc_l3_host completed_tokens != T_prefix or "
                "requested_tokens < T_prefix"
            )
    mark(
        "l3_to_host_completed",
        not l3_host_problems,
        f"target pc_l3_host completed_tokens==T_prefix ({t_prefix}) and "
        f"requested_tokens>=T_prefix"
        if not l3_host_problems
        else "; ".join(dict.fromkeys(l3_host_problems)),
    )
    # ==== predicate 7: finalize_consumed_restore ===========================
    finalize_problems: list[str] = []
    if finalize is None:
        finalize_problems.append("no target restore_hybrid_finalize")
    else:
        if finalize.fields.get("result") != "accepted":
            finalize_problems.append(
                f"finalize result={finalize.fields.get('result')!r} != accepted"
            )
        if finalize.fields.get("all_or_nothing") is not True:
            finalize_problems.append("finalize all_or_nothing is not True")
        if finalize.fields.get("kv_fetched") != t_prefix:
            finalize_problems.append(
                f"finalize kv_fetched={finalize.fields.get('kv_fetched')!r} "
                f"!= T_prefix {t_prefix!r}"
            )
        wake_event_id = finalize.fields.get("wake_event_id")
        grants = [
            r
            for r in raw
            if r.evt == "restore_host_alloc_wake_decision"
            and r.fields.get("event_id") == wake_event_id
            and r.fields.get("decision") == "grant"
            and _nonempty_str(wake_event_id)
        ]
        if not grants:
            finalize_problems.append(
                f"finalize wake_event_id={wake_event_id!r} does not name a real "
                "target grant"
            )
    finalize_problems.extend(
        _detect_recompute_discard(raw + probe, t_rid, lifecycle_key)
    )
    mark(
        "finalize_consumed_restore",
        not finalize_problems,
        "accepted all_or_nothing finalize consumed T_prefix via a real grant with "
        "no recompute/discard path"
        if not finalize_problems
        else "; ".join(dict.fromkeys(finalize_problems)),
    )
    # ==== predicate 8: negative_safety =====================================
    safety_problems: list[str] = list(parse_errors) + list(join_contradictions)
    mark(
        "negative_safety",
        not safety_problems,
        "no unreadable required records and no contradictory identity/join"
        if not safety_problems
        else "; ".join(dict.fromkeys(safety_problems)),
    )
    passed = all(item["passed"] for item in predicates)
    return {
        "status": STATUS_PASS if passed else STATUS_FAIL,
        "rule": RULE,
        "target": target_meta,
        "predicates": predicates,
        "failures": failures,
    }
def reduce_paths(
    raw_path: str, probe_path: str, manifest_path: str, l3_path: str
) -> dict:
    manifest = _load_json(manifest_path)
    _validate_manifest(manifest, raw_path, probe_path)
    l3 = _load_json(l3_path)
    _validate_l3_evidence(l3)
    raw_records, raw_errors = parse_raw(raw_path)
    probe_records, probe_errors = parse_probe(probe_path)
    parse_errors = list(raw_errors) + list(probe_errors)
    return judge(manifest, l3, raw_records, probe_records, parse_errors, l3_path)
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _empty_target() -> dict:
    return {
        "rid": None,
        "session_id": None,
        "session_generation": None,
        "build_rid": None,
        "prefix_tokens": None,
    }
def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True))
        return
    print(f"{result['status']}: {result['rule']}")
    target = result.get("target", {})
    print(
        "target rid={rid} session={session_id} gen={session_generation} "
        "build={build_rid} prefix_tokens={prefix_tokens}".format(**{**_empty_target(), **target})
    )
    for item in result.get("predicates", []):
        print(
            f"  [{'PASS' if item['passed'] else 'FAIL'}] {item['name']}: "
            f"{item['reason']}"
        )
    for failure in result.get("failures", []):
        print(f"  failure: {failure}")
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", required=True, help="frozen R114 raw.log")
    parser.add_argument("--probe", required=True, help="frozen R114 probe.log")
    parser.add_argument("--manifest", required=True, help="frozen R114 manifest.json")
    parser.add_argument(
        "--l3-evidence",
        dest="l3_evidence",
        required=True,
        help="frozen l3-evidence.json",
    )
    parser.add_argument("--json", action="store_true", help="emit machine JSON")
    args = parser.parse_args(argv)

    try:
        result = reduce_paths(args.raw, args.probe, args.manifest, args.l3_evidence)
    except InvalidInput as exc:
        result = {
            "status": STATUS_INVALID,
            "rule": RULE,
            "target": _empty_target(),
            "predicates": [],
            "failures": [f"invalid_input: {exc}"],
        }
        _emit(result, args.json)
        return 2

    _emit(result, args.json)
    return 0 if result["status"] == STATUS_PASS else 1
if __name__ == "__main__":
    sys.exit(main())
