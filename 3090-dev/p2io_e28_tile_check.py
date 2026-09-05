"""Verify the tiling hypothesis: the query chain (root-seeded, 20910 pages)
vs the concatenation of written radix node chains (each seeded from its
parent's last hash)."""

import json

LOG = "/tmp/p2io-e7m-ev/t38c-probe.log"

writes = {}
for line in open(LOG):
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r["evt"] == "pc_write_seed":
        writes[int(r["node_id"])] = (
            r["write_seed"],
            r["page0_hash"],
            r["n_pages"],
        )

queries = []
for line in open(LOG):
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r["evt"] == "pc_storage_query":
        queries.append(r)

# Focus: the root-anchored 20910-page query (ts 1788328950.309, 0bbca9d6).
q = None
for r in queries:
    if r["query_suffix_len"] == 20910 and r["ts"] > 1788328949:
        q = r
        break
if q is None:
    raise SystemExit("no query")
# The t38c log only records keys[:8]; use query_suffix_len as the full length.
chain8 = q["keys"]
suffix_len = q["query_suffix_len"]
print(f"query ts={q['ts']:.3f} rid={q['rid'][:8]} suffix={suffix_len} (first 8 keys logged)")
print(f"query key0={chain8[0][:16]} key1={chain8[1][:16]} key2={chain8[2][:16]}")

def ch(i):
    """chain[i] if within the logged first-8, else a placeholder."""
    if i < len(chain8):
        return chain8[i]
    return f"<beyond {len(chain8)}>"

# node19 = root child (3 pages): query chain positions 0,1,2 should be node19
# chain pages 0,1,2
print("\nnode19 (root child, n=3):")
print(f"  written page0={writes[19][1][:16]}")
print(f"  query chain[0]={ch(0)[:16]}  match={chain8[0]==writes[19][1]}")

# node18 seed = cb3d0866 == query chain[2]?
print(f"\nnode18 seed={writes[18][0][:16]}, n={writes[18][2]}")
print(f"query chain[2]={ch(2)[:16]}  match={chain8[2]==writes[18][0]}")

# If node18 is the continuation after node19 (3 pages), its chain (61 pages)
# should fill query chain positions 3..63, seeded from node19's page2 hash.
# node18 page0 hash should equal query chain[3].
print(f"\nnode18 page0={writes[18][1][:16]}")
print(f"query chain[3]={ch(3)[:16]}  match={chain8[3]==writes[18][1]}")

# Search where each written node's SEED appears in the query chain (within the
# logged first-8 keys; the full chain is not logged, so this is partial).
print("\n--- where each node's seed appears in the logged first-8 query keys ---")
for nid in sorted(writes):
    seed = writes[nid][0]
    if not seed:
        print(f"  node {nid}: root child (seed='')")
        continue
    hits = [i for i, k in enumerate(chain8) if k == seed]
    if hits:
        print(f"  node {nid}: seed8={seed[:16]} n={writes[nid][2]} at positions {hits}")
    else:
        print(f"  node {nid}: seed8={seed[:16]} n={writes[nid][2]} not in logged 8")

# key structural check within the logged 8: does the query chain[0..7] match a
# CONCATENATION of node chains? node19(3 pages: 0,1,2) then node18 seeded from
# chain[2]=(cb3d0866): its page0 should be chain[3].
print("\n--- tile continuity within logged 8 ---")
# node19 pages 0,1,2; node18 page0 at chain[3]?
m1 = chain8[3] == writes[18][1]
print(f"node19(3)+node18(61): node18.page0 == chain[3]? {m1} "
      f"({chain8[3][:16]} vs {writes[18][1][:16]})")
# node18's 61 pages end at chain[63]; node20 (seed=fbd8c9a9) should continue.
# Not logged. But node18 n=61 and node19 n=3 = 64 pages; chain[64] is beyond the 8.
# Check the OTHER 20910 query that hit node19+node18: does node20 seed appear?
for nid in (20, 22):
    seed = writes[nid][0][:16]
    hits = [i for i, k in enumerate(chain8) if k[:16] == seed]
    print(f"node{nid} seed8={seed} in logged 8 at: {hits}")
