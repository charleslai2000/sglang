#!/usr/bin/env python3
"""Gate2 aggregate analysis: effective_cache_ratio + mamba pool saturation.

Reads a gate2 run dir:
  join.log          per-request rows (device_hit/host_hit/storage_hit/prompt_len)
  mid-run-metrics.txt  gauge time series (mamba_evictable_tokens)
  metrics-final.txt  end-of-run /metrics (mamba_available/used/evictable,
                     prefill_effective_tokens_total modes, backup/load_back)

Computes the frozen acceptance items:
  aggregate effective_cache_ratio = sum(device+host+storage) / sum(prompt_len)
  mamba pool water (evictable series min/max/mean; final available/used/evictable)
  recompute tokens = sum(new_tokens_est) and counter delta mode=input
  per-request cliff scan: prompt_hit>=X but usable_hit==0 (Mamba-gated 0-hit)
  KV hit vs usable hit
  L3 restore count (storage_hit>0 rows)
"""
import glob
import json
import os
import re
import statistics
import sys


def parse_join(run_dir):
    rows = []
    p = os.path.join(run_dir, "join.log")
    if os.path.exists(p):
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            rows.append(r)
    if rows:
        return rows
    # Reconstruct from per-turn artifacts (meta.json + body). This is the
    # authoritative source when the driver's join.log/runs.csv write was lost
    # (e.g. the early tier where the csv writer crashed on divergent counter
    # keys while all 48 requests still completed and were persisted).
    rows = _rows_from_artifacts(run_dir)
    if rows:
        return rows
    # fallback: runs.csv
    p = os.path.join(run_dir, "runs.csv")
    if os.path.exists(p):
        import csv
        try:
            with open(p) as f:
                rd = csv.DictReader(f)
                for r in rd:
                    for k, v in r.items():
                        if v == "":
                            r[k] = None
                    rows.append(r)
        except Exception:
            pass
    return rows


def _extract_sglext_from_body(body_path):
    """Best-effort sglext/cached_tokens extraction from an SSE body (mirrors
    common.extract_sglext: cached_tokens_details + cached_tokens)."""
    out = {"cached_tokens_details": None, "cached_tokens": None,
           "usage": None, "rid": None}
    try:
        with open(body_path) as f:
            for line in f:
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue
                if out["rid"] is None and obj.get("id"):
                    out["rid"] = obj.get("id")
                sg = obj.get("sglext")
                if isinstance(sg, dict):
                    ctd = sg.get("cached_tokens_details")
                    if isinstance(ctd, dict):
                        out["cached_tokens_details"] = {
                            "device": ctd.get("device"),
                            "host": ctd.get("host"),
                            "storage": ctd.get("storage"),
                        }
                u = obj.get("usage")
                if isinstance(u, dict):
                    out["usage"] = u
                    ptd = u.get("prompt_tokens_details")
                    if isinstance(ptd, dict):
                        ct = ptd.get("cached_tokens")
                        if ct is not None:
                            out["cached_tokens"] = ct
    except Exception:
        pass
    return out


def _rows_from_artifacts(run_dir):
    turns_dir = os.path.join(run_dir, "turns")
    rows = []
    if not os.path.isdir(turns_dir):
        return rows
    for meta_path in sorted(glob.glob(os.path.join(turns_dir, "**", "*.meta.json"),
                                      recursive=True)):
        try:
            meta = json.load(open(meta_path))
        except Exception:
            continue
        body_path = meta_path[:-len(".meta.json")] + ".body"
        sx = _extract_sglext_from_body(body_path) if os.path.exists(body_path) else {}
        row = _row_from_artifacts(meta_path, meta, sx)
        if row:
            rows.append(row)
    return rows


def _row_from_artifacts(meta_path, meta, sx):
    """Reconstruct a join-style row from the per-turn artifact files. The turn
    dir layout is turns/agent-<aid>/t<turn>.<kind>-<level>.meta.json; kind is
    write/restore/branch, level L0..L3 or BB*."""
    m = re.search(r"agent-(\d+)/t(\d+)\.([a-z]+)-(L\d+|BB\d+)\.meta\.json$", meta_path)
    if not m:
        return None
    aid, turn, kind, level = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    u = meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    dh = ctd.get("device")
    hh = ctd.get("host")
    sh = ctd.get("storage")
    pl = u.get("prompt_tokens")
    hits = [dh, hh, sh]
    ne = None
    if isinstance(pl, (int, float)) and all(isinstance(x, (int, float)) for x in hits):
        ne = pl - sum(hits)
    return {
        "agent_id": aid, "turn": turn, "turn_kind": kind,
        "phase": "A" if kind == "write" else "B",
        "session": aid, "level": level, "variant": None,
        "prompt_len": pl,
        "cached_tokens": (sx or {}).get("cached_tokens"),
        "device_hit": dh, "host_hit": hh, "storage_hit": sh,
        "new_tokens_est": ne,
        "ttft_s": meta.get("ttft_s"), "http": meta.get("http_code"),
        "finished": meta.get("finished"), "payload": os.path.basename(meta_path),
    }


def g(snap, prefix):
    for k, v in snap.items():
        if k.startswith(prefix):
            return v
    return None


def parse_mid(f):
    snaps = []
    for line in open(f):
        try:
            d = json.loads(line)
        except Exception:
            continue
        snaps.append(d.get("metrics", {}))
    return snaps


def series(snaps, prefix):
    out = []
    for s in snaps:
        v = g(s, prefix)
        if v is not None:
            out.append(v)
    return out


def parse_final(f):
    snap = {}
    if not os.path.exists(f):
        return snap
    for line in open(f):
        if line.startswith("sglang:"):
            try:
                k, _, v = line.strip().partition(" ")
                snap[k] = float(v)
            except Exception:
                pass
    return snap


def counter(snap, name, label_contains=None):
    for k, v in snap.items():
        if k.startswith(name + "{"):
            if label_contains is None or label_contains in k:
                return v
    return None


def main(run_dir, tag="run"):
    rows = parse_join(run_dir)
    if not rows:
        print("ERROR: no join rows in %s" % run_dir)
        return 1
    phase_b = [r for r in rows if r.get("phase") == "B"]
    phase_a = [r for r in rows if r.get("phase") == "A"]
    mid = parse_mid(os.path.join(run_dir, "mid-run-metrics.txt"))
    fin = parse_final(os.path.join(os.path.dirname(run_dir.rstrip("/")), "metrics-final.txt"))
    if not fin:
        fin = parse_final(os.path.join(os.path.dirname(run_dir.rstrip("/")) + "/", "metrics-final.txt"))

    # --- per-request ---
    total_prompt = 0
    total_hit = 0
    total_dev = total_host = total_stor = 0
    recompute = 0
    restore_rows = 0
    cliff_rows = []
    per_tier = {"device": [], "host": [], "storage": []}
    n_ok = 0
    n_bad = 0
    for r in rows:
        pl = r.get("prompt_len")
        if not isinstance(pl, (int, float)):
            continue
        dh = r.get("device_hit")
        hh = r.get("host_hit")
        sh = r.get("storage_hit")
        if not all(isinstance(x, (int, float)) for x in (dh, hh, sh)):
            continue
        n_ok += 1
        usable = dh + hh + sh
        total_prompt += pl
        total_hit += usable
        total_dev += dh
        total_host += hh
        total_stor += sh
        per_tier["device"].append(dh)
        per_tier["host"].append(hh)
        per_tier["storage"].append(sh)
        ne = r.get("new_tokens_est")
        if isinstance(ne, (int, float)):
            recompute += ne
        if sh > 0:
            restore_rows += 1
        # usable-hit < some floor while prompt huge: recompute-heavy request
        if usable == 0 and pl > 100:
            n_bad += 1
        # cliff candidate: decent device+host hit but zero storage AND zero
        # usable total cannot happen (usable = d+h+s); the Mamba-gated cliff is
        # rather a full-cache-miss on a previously-written chain -> usable 0.
        if usable == 0 and pl > 1000:
            cliff_rows.append({
                "turn": r.get("turn"), "agent": r.get("agent_id"),
                "kind": r.get("turn_kind"), "session": r.get("session"),
                "prompt": pl, "device": dh, "host": hh, "storage": sh,
                "ttft": r.get("ttft_s"), "http": r.get("http"),
            })

    agg = total_hit / total_prompt if total_prompt else None
    if agg is None:
        agg = 0.0

    # --- mamba pool ---
    mev = series(mid, "sglang:mamba_evictable_tokens")
    m_avail_f = g(fin, "sglang:mamba_available_tokens")
    m_used_f = g(fin, "sglang:mamba_used_tokens")
    m_evict_f = g(fin, "sglang:mamba_evictable_tokens")
    pool_size = None
    if m_avail_f is not None and m_evict_f is not None and m_used_f is not None:
        pool_size = m_avail_f + m_evict_f + m_used_f

    # --- counters ---
    inp = counter(fin, "sglang:prefill_effective_tokens_total", 'mode="input"')
    dhc = counter(fin, "sglang:prefill_effective_tokens_total", 'mode="device_hit"')
    hhc = counter(fin, "sglang:prefill_effective_tokens_total", 'mode="host_hit"')
    shc = counter(fin, "sglang:prefill_effective_tokens_total", 'mode="storage_hit"')
    eff_counters = {"input": inp, "device": dhc, "host": hhc, "storage": shc}
    agg_counter = None
    if all(v is not None for v in (dhc, hhc, shc, inp)) and inp > 0:
        agg_counter = (dhc + hhc + shc) / inp
    hicache_dropped_mamba = counter(fin, "sglang:hicache_dropped_tokens_total", 'pool="mamba"')
    backup_mamba = counter(fin, "sglang:hicache_backup_tokens_total", 'pool="mamba"')
    loadback_mamba = counter(fin, "sglang:load_back_tokens_total", 'pool="mamba"')
    backup_kv = counter(fin, "sglang:hicache_backup_tokens_total", 'pool="kv"')
    loadback_kv = counter(fin, "sglang:load_back_tokens_total", 'pool="kv"')

    print("=" * 70)
    print("GATE2 aggregate analysis: %s" % tag)
    print("=" * 70)
    print("requests parsed=%d (usable rows %d)" % (len(rows), n_ok))
    print("-- aggregate effective cache ratio (join per-request) --")
    print("  total_prompt=%d total_hit=%d ratio=%.4f (%s)" % (
        total_prompt, total_hit, agg, "PASS >=0.95" if agg >= 0.95 else "FAIL <0.95"))
    print("  device=%d host=%d storage=%d restore_rows=%d recompute=%d" % (
        total_dev, total_host, total_stor, restore_rows, recompute))
    print("-- aggregate via engine counters (prefill_effective_tokens_total) --")
    print("  input=%s device=%s host=%s storage=%s ratio=%s" % (
        eff_counters["input"], eff_counters["device"], eff_counters["host"],
        eff_counters["storage"],
        ("%.4f" % agg_counter) if agg_counter is not None else None))
    print("-- mamba pool water --")
    if mev:
        print("  mamba_evictable series n=%d min=%d max=%d mean=%.1f" % (
            len(mev), min(mev), max(mev), statistics.mean(mev)))
    print("  final: available=%s evictable=%s used=%s -> pool_size=%s" % (
        m_avail_f, m_evict_f, m_used_f, pool_size))
    print("  hicache dropped(pool=mamba)=%s backup(mamba)=%s load_back(mamba)=%s" % (
        hicache_dropped_mamba, backup_mamba, loadback_mamba))
    print("  backup(kv)=%s load_back(kv)=%s" % (backup_kv, loadback_kv))
    print("-- cliff scan --")
    print("  zero-usable requests with prompt>100: %d; prompt>1000: %d" % (
        n_bad, len(cliff_rows)))
    for c in cliff_rows[:15]:
        print("    %s" % c)
    # per-tier hit ratio distribution
    if per_tier["device"]:
        print("-- per-request hit tiers (nonzero counts) --")
        for t in ("device", "host", "storage"):
            nz = sum(1 for v in per_tier[t] if v and v > 0)
            print("  %-8s nonzero=%d/%d" % (t, nz, len(per_tier[t])))

    # Phase A/B split: Phase B (read/verify: restore + mid-branch) is the
    # acceptance metric for gate2; Phase A (write/saturate) is shown for
    # context -- its ratio is capped by the new tokens written, by design.
    for ph, label in (("A", "Phase A write/saturate"),
                      ("B", "Phase B read/verify")):
        sub = [r for r in rows if r.get("phase") == ph]
        sp = sh_sum = sd = shh = sst = 0
        sr = 0
        for r in sub:
            pl = r.get("prompt_len")
            if not isinstance(pl, (int, float)):
                continue
            dh, hh, st = r.get("device_hit"), r.get("host_hit"), r.get("storage_hit")
            if not all(isinstance(x, (int, float)) for x in (dh, hh, st)):
                continue
            sp += pl
            sd += dh
            shh += hh
            sst += st
            sh_sum += dh + hh + st
            if st > 0:
                sr += 1
        print("-- %s --" % label)
        print("  requests=%d prompt=%d hit=%d ratio=%.4f (dev=%d host=%d stor=%d restore=%d)" % (
            len(sub), sp, sh_sum,
            (sh_sum / sp) if sp else 0.0, sd, shh, sst, sr))

    # Exact-checkpoint retrieval: restore rows of a previously-written chain
    # level (same-session L0/L1/L2 restores). This is the acceptance metric for
    # "old session / mid-branch no systematic 0-hit" under pool pressure.
    print("-- exact-checkpoint retrieval (restore rows, phase B) --")
    for lvl in ("L0", "L1", "L2"):
        sub = [r for r in rows
               if r.get("phase") == "B" and r.get("turn_kind") == "restore"
               and r.get("level") == lvl]
        if not sub:
            continue
        sp = sh_sum = 0
        n_zero = 0
        per = []
        for r in sub:
            pl = r.get("prompt_len")
            dh, hh, st = r.get("device_hit"), r.get("host_hit"), r.get("storage_hit")
            if not isinstance(pl, (int, float)):
                continue
            if not all(isinstance(x, (int, float)) for x in (dh, hh, st)):
                continue
            usable = dh + hh + st
            sp += pl
            sh_sum += usable
            per.append(usable / pl if pl else 0.0)
            if usable < 100:
                n_zero += 1
        print("  %s restore n=%d prompt=%d hit=%d ratio=%.4f full_miss(<100)=%d"
              % (lvl, len(sub), sp, sh_sum, (sh_sum / sp) if sp else 0.0, n_zero))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: gate2_analyze.py <run-dir> [tag]")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "run"))
