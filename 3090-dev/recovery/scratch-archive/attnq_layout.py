"""Row-order forensics of the fused attn_q (q|gate) in the 27B GGUF files.

If the two independently-produced files share the same row order, compare the
per-row L2-norm profile: a period-2*head_dim alternation means the HF-style
per-head [q_h, gate_h] interleave; a single step at (2*H*D)/2 means a blocked
[all q | all gate] layout.
"""
import numpy as np, gguf
from gguf.quants import dequantize

FILES = {
 'M3': '/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf',
 'M4': '/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf',
}
H, D = 24, 256          # 24 heads, head_dim 256 (from GGUF metadata)
INTER = 2 * D           # 512 rows per head block under per-head interleave

profs = {}
for label, path in FILES.items():
    r = gguf.GGUFReader(path)
    t = [x for x in r.tensors if x.name == 'blk.3.attn_q.weight'][0]
    raw = np.ascontiguousarray(t.data)
    out = []
    for i in range(0, raw.shape[0], 256):
        out.append(dequantize(np.ascontiguousarray(raw[i:i+256]), t.tensor_type))
    W = np.concatenate(out, axis=0).astype(np.float32)   # (nrows, K)
    n = np.linalg.norm(W, axis=1)
    profs[label] = n
    print(f'{label} blk.3.attn_q rows={n.shape[0]} type={t.tensor_type.name} '
          f'norm mean={n.mean():.4f} std={n.std():.4f} min={n.min():.4f} max={n.max():.4f}', flush=True)
    del W, out, raw

# cross-file correlation of the row-norm profiles
a, b = profs['M3'], profs['M4']
print(f'cross-file Pearson r(M3,M4) = {np.corrcoef(a,b)[0,1]:.6f}')

for label in FILES:
    n = profs[label]
    # blocked signature: first half vs second half
    h = n.shape[0] // 2
    print(f'-- {label}: mean(firsthalf)={n[:h].mean():.4f} mean(secondhalf)={n[h:].mean():.4f} '
          f'ratio={n[h:].mean()/n[:h].mean():.4f}')
    # per-head-block means under per-head interleave (512 rows = one head's q+gate)
    nb = n.shape[0] // INTER
    bm = n.reshape(nb, INTER)
    q_mean = bm[:, :D].mean(axis=1)
    g_mean = bm[:, D:].mean(axis=1)
    print(f'   per-head-block [{D} q rows | {D} gate rows]: '
          f'mean|q|={q_mean.mean():.4f} mean|gate|={g_mean.mean():.4f} '
          f'ratio gate/q={g_mean.mean()/q_mean.mean():.4f} '
          f'corr(q_mean,gate_mean)={np.corrcoef(q_mean,g_mean)[0,1]:.4f}')
    # blocked hypothesis: q rows = [0, n/2), gate rows = [n/2, n)
    bq = n[:n.shape[0]//2].reshape(-1, D).mean(axis=1)
    bg = n[n.shape[0]//2:].reshape(-1, D).mean(axis=1)
    print(f'   blocked split: mean|q|={bq.mean():.4f} mean|gate|={bg.mean():.4f} '
          f'ratio gate/q={bg.mean()/bq.mean():.4f}')
    # autocorrelation at lags 256 / 512 / 6144 (period signatures)
    x = n - n.mean()
    ac = lambda lag: float(np.dot(x[:-lag], x[lag:]) / np.dot(x, x))
    print(f'   autocorr lag256={ac(256):.4f} lag512={ac(512):.4f} lag1024={ac(1024):.4f} lag6144={ac(6144):.4f}')
