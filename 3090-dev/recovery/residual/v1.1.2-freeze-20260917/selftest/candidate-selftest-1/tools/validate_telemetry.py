#!/usr/bin/env python3
"""LOCAL-PROD-v1.1.2-SELFTEST-DO-NOT-PROMOTE — hash-bound telemetry validator.

P0 Expert-Gate review (R8) required: a validator must FIRST bind the exact
reviewed source bytes + Gate/erratum artifacts by SHA-256, and only then
accept telemetry records.  A record is never trusted on its own.

Exit codes: 0 = all checks pass; 1 = hash binding failed; 2 = record violated.
"""
import hashlib, json, os, sys

SRC = "/tmp/opencode/v1.1.2-freeze-20260917/selftest/candidate-selftest-1/src"
EVID = f"{SRC}/.memory/phase2-hicache-design/evidence/p0-telemetry-20260914/authority"

# --- reviewed P0 source bytes (frozen; terminal review PASS_FOR_CURRENT_BYTES) ---
SOURCE_HASHES = {
    "python/sglang/srt/observability/hicache_telemetry.py":
        "788318d91dc415202737058dedd918f2f822db93f70251d9598689c84fef72aa",
    "python/sglang/srt/mem_cache/unified_radix_cache.py":
        "5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f",
    "python/sglang/srt/managers/tokenizer_manager.py":
        "9f9d38028008c7f6afe9dc58508ab9e84eb981462beff79e8f874283f69ddf46",
    "python/sglang/srt/managers/scheduler_components/output_streamer.py":
        "8485d9563e073b8e901c8e2fc5eee8156d74a9433abf212bf5167664af82e910",
    "test/registered/unit/observability/test_hicache_request_telemetry.py":
        "e577d94086dd188d4dc244056a583ef4fb7cd96a79d231691cfa6fb3e1c936b2",
    "test/registered/unit/observability/test_output_streamer_hicache_telemetry_wiring.py":
        "717ac93c6a3b1c0522274698d62c310a95bfcb2263c11fe65a688117b4ee9d00",
}
GATE_HASHES = {
    f"{EVID}/P0-TELEMETRY-EXPERT-GATE-20260914.md":
        "48b4faade00d2261889eb94f2bce44d11a62d12139b6d9200d7289c3c74f8c17",
    f"{EVID}/P0-TELEMETRY-EXPERT-GATE-20260914.json":
        "1e8277e9762cafc7336156479973d725d9bce973d245d1f62974ad407795e374",
    f"{EVID}/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.md":
        "135854e3511f416024cd1653469cae598209c6fbaf2b778b3c5e788148a317c6",
    f"{EVID}/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.json":
        "4a0f219aca6940eda00606a649d50634a87958ba1f0be84600acdb1177a8128e",
}
ALLOWED_KEYS = {
    "schema","rh_eligible","prefetch_origin","prefetch_attempt_id",
    "enqueue_mono_ns","prefetch_issue_mono_ns","storage_query_start_mono_ns",
    "storage_query_end_mono_ns","ready_mono_ns","admission_mono_ns",
    "prefill_finish_mono_ns","prompt_tokens","l1_tokens","l2_tokens","l3_tokens",
    "newly_prefilled_tokens","matched_prefix_tokens","matched_prefix_authority",
    "matched_prefix_l3_tokens","durable_reusable_prefix_tokens",
    "avoidable_recompute_tokens","completed_kv_tokens","required_aux_pools",
    "completed_aux_units","hybrid_restore_complete","rh_prefetch_lead_seconds",
    "rh_ready_slack_seconds","stage_latency_seconds","outcome","partial_reason",
    "invalid_reason",
}
SCHEMA = "hicache_request.v1"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def bind():
    bad = []
    for rel, exp in SOURCE_HASHES.items():
        p = os.path.join(SRC, rel)
        got = sha(p) if os.path.exists(p) else "MISSING"
        ok = got == exp
        print(f"  {'OK  ' if ok else 'FAIL'}  {rel}")
        if not ok: bad.append((rel, exp, got))
    for p, exp in GATE_HASHES.items():
        got = sha(p) if os.path.exists(p) else "MISSING"
        ok = got == exp
        print(f"  {'OK  ' if ok else 'FAIL'}  {os.path.basename(p)}")
        if not ok: bad.append((p, exp, got))
    return bad

def validate(path):
    n = v = 0
    if not os.path.exists(path):
        return 0, 0, [f"missing file {path}"]
    for i, ln in enumerate(open(path), 1):
        ln = ln.strip()
        if not ln: continue
        try: r = json.loads(ln)
        except Exception as e:
            v += 1; print(f"    L{i}: unparseable JSON: {e}"); continue
        h = r.get("hicache_telemetry")
        if not h: continue
        n += 1
        errs = []
        extra = set(h) - ALLOWED_KEYS
        if extra: errs.append(f"unexpected keys {sorted(extra)}")
        if h.get("schema") != SCHEMA: errs.append(f"schema {h.get('schema')!r}")
        if h.get("outcome") not in ("complete","partial","invalid"):
            errs.append(f"outcome {h.get('outcome')!r}")
        p,l1,l2,l3,npf = (h.get(k) for k in
            ("prompt_tokens","l1_tokens","l2_tokens","l3_tokens","newly_prefilled_tokens"))
        if None not in (p,l1,l2,l3,npf) and l1+l2+l3+npf != p:
            errs.append(f"conservation {l1}+{l2}+{l3}+{npf} != {p}")
        av = h.get("avoidable_recompute_tokens")
        if av is not None and (npf is None or not (0 <= av <= npf)):
            errs.append(f"avoidable {av} outside [0,{npf}]")
        # FR1 atomicity: unproven/unknown authority must carry NO positive durable
        auth, dur = h.get("matched_prefix_authority"), h.get("durable_reusable_prefix_tokens")
        if auth in ("unknown",) and dur is not None:
            errs.append(f"ATOMICITY: authority=unknown but durable={dur}")
        if dur is not None and auth != "l3_durable":
            errs.append(f"ATOMICITY: durable={dur} with authority={auth!r}")
        if h.get("outcome") == "complete" and h.get("invalid_reason"):
            errs.append("complete with invalid_reason")
        if errs:
            v += 1
            for e in errs: print(f"    L{i}: {e}")
    return n, v, []

def main():
    files = sys.argv[1:]
    if not files:
        print("usage: validate_telemetry.py <jsonl...>"); return 2
    print("=== STEP 1: hash binding (reviewed bytes + Gate/erratum) ===")
    bad = bind()
    if bad:
        print(f"\nHASH BINDING FAILED ({len(bad)} mismatch). REFUSING to accept records.")
        return 1
    print(f"\n=== hash binding PASS: {len(SOURCE_HASHES)} source + {len(GATE_HASHES)} gate artifacts ===")
    print("=== STEP 2: record validation ===")
    tn = tv = 0
    for f in files:
        n, v, errs = validate(f)
        tn += n; tv += v
        print(f"  {f}: {n} telemetry records, {v} violations")
        for e in errs: print(f"    {e}")
    print(f"\n=== RESULT: {tn} records accepted, {tv} violations ===")
    return 2 if tv else 0

if __name__ == "__main__":
    sys.exit(main())
