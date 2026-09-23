"""e7p recompute quantification (pure arithmetic, no torch / no tensors).

User objective: effective_cache_ratio = 1 - recompute_tokens/context_tokens >= 95%.
Node = 2048 tokens (live node size); mamba checkpoint written once per node at the
node's LAST page (node.hash_value[-1]); a checkpoint exists only for a COMPLETED
node. Growing session: each turn adds delta ~ Uniform[512, 4096] tokens, stopping
mid-node.

Two restore paths on a partial (mid-node) query prefix P:
  (a) all-or-nothing (current): final_pages clamped to 0 -> recompute = ENTIRE
      prefix (token-identical to a cold miss).
  (b) fallback (KV kept + nearest mamba node-tail checkpoint + tail recompute):
      last_valid_boundary = 2048 * floor(P/2048); recompute = P - last_valid_boundary
      = the within-node offset (uniform ~ U[0, 2047] for P well past a boundary).
      Caveat: for P < 2048 (prefix still inside the FIRST node) no node-tail
      checkpoint exists yet -> fallback degenerates to recompute = P.
"""
import random

NODE = 2048
DELTA_LO, DELTA_HI = 512, 4096
N_SESSIONS = 2000
N_TURNS = 24
CONTEXTS = [32768, 65536, 131072]  # nominal 32K / 64K / 128K

random.seed(7)


def simulate_sessions():
    """Return per-turn rows: (prefix P, recompute_all_or_nothing, recompute_fallback)."""
    rows = []
    for _ in range(N_SESSIONS):
        prefix = 0
        for _turn in range(N_TURNS):
            prefix += random.randint(DELTA_LO, DELTA_HI)
            last_valid = NODE * (prefix // NODE)  # nearest node-tail boundary <= P
            rows.append((prefix, prefix, prefix - last_valid))
    return rows


rows = simulate_sessions()
n = len(rows)
print(f"simulated: {N_SESSIONS} sessions x {N_TURNS} turns = {n} turn-samples")
print(f"node={NODE} tokens; turn delta ~ Uniform[{DELTA_LO},{DELTA_HI}]")
print(f"mamba checkpoint exists only for COMPLETED nodes "
      f"(written at node.hash_value[-1] on BACKUP_STORAGE)")
print()

# ---- 1. last-valid-boundary offset distribution ----
tails = [fb for _, _, fb in rows]
tails_sorted = sorted(tails)
def pct(p):
    return tails_sorted[min(n - 1, int(p * n))]

exact = sum(1 for P, _, _ in rows if P % NODE == 0)
first_node = sum(1 for P, _, _ in rows if P < NODE)
print("=== 1. last-valid-boundary offset (tail recompute) distribution ===")
print(f"  mean tail  = {sum(tails)/n:.1f}  tokens (U[0,2047] theory: ~1023.5)")
print(f"  p10={pct(0.10)}, p50(median)={pct(0.50)}, p90={pct(0.90)}, max={max(tails)}")
print(f"  turns with tail=0 (exact boundary): {exact}/{n} = {100.0*exact/n:.3f}%")
print(f"  turns inside FIRST node (P<{NODE}, no checkpoint -> fallback=full): "
      f"{first_node}/{n} = {100.0*first_node/n:.3f}%")
print()

# ---- 2. per-request effective_cache_ratio vs nominal context ----
print("=== 2. per-request effective_cache_ratio (denominator = nominal context) ===")
print(f"  {'ctx':>8} | {'(a) all-or-nothing':>19} | {'(b) fallback avg':>16} | "
      f"{'(b) fb min (worst req)':>20}")
for c in CONTEXTS:
    all_rat = [1.0 - all_re / c for _, all_re, _ in rows]
    fb_rat = [1.0 - fb / c for _, _, fb in rows]
    avg_all = sum(all_rat) / n
    avg_fb = sum(fb_rat) / n
    min_fb = min(fb_rat)
    print(f"  {c:>8} | {100.0*avg_all:>18.2f}% | {100.0*avg_fb:>15.2f}% | "
          f"{100.0*min_fb:>19.2f}%")
print()

# ---- 3. per-request ratio with the ACTUAL prefix as context ----
print("=== 3. per-request ratio (denominator = actual current prefix P) ===")
print("  early turns (P<2048) are the only full-loss turns under fallback")
for c in CONTEXTS:
    sel = [r for r in rows if r[0] >= (c // 2)]  # mature sessions near nominal ctx
    sel_n = len(sel)
    fb_rat = [1.0 - fb / P for P, _, fb in sel]
    avg_fb = sum(fb_rat) / sel_n
    min_fb = min(fb_rat)
    print(f"  ctx~{c:>8} ({sel_n} turns): fallback avg ratio = {100.0*avg_fb:.2f}%  "
          f"worst = {100.0*min_fb:.2f}%")
print()

# ---- 4. session-aggregate recompute fraction (total tail / total tokens) ----
print("=== 4. session-aggregate recompute fraction (total tail / total tokens) ===")
for c in CONTEXTS:
    sel = [r for r in rows if r[0] >= (c // 2)]
    total_tok = sum(P for P, _, _ in sel)
    total_fb = sum(fb for _, _, fb in sel)
    total_all = sum(all_re for _, all_re, _ in sel)
    print(f"  ctx~{c:>8}: total tokens={total_tok} | fallback recompute={total_fb} "
          f"({100.0*total_fb/total_tok:.2f}%) | all-or-nothing recompute={total_all} "
          f"({100.0*total_all/total_tok:.2f}%)")
print()

# ---- 5. verdict-ready numbers ----
print("=== 5. 5% recompute-overhead threshold check (fallback) ===")
for c in CONTEXTS:
    sel = [r for r in rows if r[0] >= (c // 2)]
    total_tok = sum(P for P, _, _ in sel)
    total_fb = sum(fb for _, _, fb in sel)
    frac = total_fb / total_tok
    print(f"  ctx~{c:>8}: recompute_overhead = {100.0*frac:.2f}%  "
          f"({'> 5% -- needs checkpoint abstraction' if frac > 0.05 else '<= 5% -- node-level enough'})")