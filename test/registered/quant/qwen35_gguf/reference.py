#!/usr/bin/env python3
"""
B1a-1: single-full-GDN-layer numerical proof (synthetic, torch).

Canonical grouped reference (HF/Qwen3.5 semantics) vs candidate tiled path
(weights in llama.cpp GGUF tiled order + tiled pairing k_head(vh) = vh % K).

The proof shows the two representations compute the SAME function:
  every intermediate node (q/k/v/z projection, conv output, recurrent state
  update, gate, out_proj output) matches within FP tolerance.

Research harness only. NOT production code.
"""

import torch
import torch.nn.functional as F
import numpy as np

torch.manual_seed(0)


def reorder_block_indices(K, r, head_dim):
    """tiled[perm[i]] = grouped[i] (same as llama.cpp _reorder_v_heads)."""
    n = K * r * head_dim
    idx = np.arange(n).reshape(K, r, head_dim)
    idx_p = np.transpose(idx, (1, 0, 2))
    return idx_p.reshape(n)


def tiled_from_grouped_rows(W, K, r, head_v, offset, dim=0):
    """Reorder a row block of W (dim=0) grouped->tiled (like converter)."""
    perm = reorder_block_indices(K, r, head_v)
    idx = np.arange(W.shape[dim])
    n = K * r * head_v
    idx[offset : offset + n] = perm + offset
    return np.take(W, idx, axis=dim)


def tiled_from_grouped_cols(W, K, r, head_v, offset, dim=1):
    """Reorder a column block of W (dim=1) grouped->tiled (out_proj)."""
    perm = reorder_block_indices(K, r, head_v)
    idx = np.arange(W.shape[dim])
    n = K * r * head_v
    idx[offset : offset + n] = perm + offset
    return np.take(W, idx, axis=dim)


def gdn_layer_grouped(x, W, T=8, K=2, r=3, head_k=4, head_v=4, hidden=8):
    """
    Canonical grouped GDN forward (HF/Qwen3.5 semantics), single layer,
    sequence of T tokens. All weights in GROUPED order.
    Returns dict of intermediate nodes (as torch tensors, fp64).
    """
    V = K * r
    q_dim, k_dim, v_dim = K * head_k, K * head_k, V * head_v
    x = torch.tensor(x, dtype=torch.float64)

    W_q = torch.tensor(W["q"], dtype=torch.float64)  # (q_dim, hidden)
    W_k = torch.tensor(W["k"], dtype=torch.float64)
    W_v = torch.tensor(W["v"], dtype=torch.float64)
    W_z = torch.tensor(W["z"], dtype=torch.float64)
    W_a = torch.tensor(W["a"], dtype=torch.float64)  # (V, hidden)
    W_b = torch.tensor(W["b"], dtype=torch.float64)
    conv = torch.tensor(W["conv"], dtype=torch.float64)  # (2*q_dim+v_dim, kernel)
    W_out = torch.tensor(W["out"], dtype=torch.float64)  # (hidden, v_dim)
    A_log = torch.tensor(W["A_log"], dtype=torch.float64)
    dt_bias = torch.tensor(W["dt_bias"], dtype=torch.float64)
    norm_w = torch.tensor(W["norm_w"], dtype=torch.float64)  # (head_v,)

    # projections
    q = x @ W_q.t()  # (T, q_dim)
    k = x @ W_k.t()
    v = x @ W_v.t()  # (T, v_dim)
    z = x @ W_z.t()
    a = x @ W_a.t()  # (T, V)
    b = x @ W_b.t()

    # conv1d causal (kernel=4) over [q;k;v] channels
    mixed = torch.cat([q, k, v], dim=-1)  # (T, conv_dim)
    conv_weight = conv.unsqueeze(1)  # (conv_dim, 1, kernel)
    # causal depthwise conv, kernel=4 -> left pad by 3
    mixed_pad = F.pad(mixed.unsqueeze(0).transpose(1, 2), (3, 0))  # (1, conv_dim, T+3)
    mixed_conv = F.conv1d(
        mixed_pad,
        conv_weight,
        groups=conv.shape[0],
    )[0].transpose(0, 1)  # (T, conv_dim)
    mixed_conv = F.silu(mixed_conv)

    q_c = mixed_conv[:, :q_dim].reshape(T, K, head_k)
    k_c = mixed_conv[:, q_dim : q_dim + k_dim].reshape(T, K, head_k)
    v_c = mixed_conv[:, q_dim + k_dim :].reshape(T, V, head_v)

    # L2 norm q/k per head
    q_n = F.normalize(q_c, p=2, dim=-1)
    k_n = F.normalize(k_c, p=2, dim=-1)
    scale = head_k**-0.5

    # per-v-head state update (grouped pairing: vh -> khead = vh // r)
    state = torch.zeros(T, V, head_v, head_k, dtype=torch.float64)
    o = torch.zeros(T, V, head_v, dtype=torch.float64)
    gate = torch.zeros(T, V, dtype=torch.float64)
    beta = torch.zeros(T, V, dtype=torch.float64)
    for t in range(T):
        for vh in range(V):
            g_k = vh // r
            g_v = -torch.exp(A_log[vh]) * F.softplus(a[t, vh] + dt_bias[vh])
            beta_v = torch.sigmoid(b[t, vh])
            if t == 0:
                h = torch.zeros(head_v, head_k, dtype=torch.float64)
            else:
                h = state[t - 1, vh]
            h = h * torch.exp(g_v)
            d = v_c[t, vh] - (h @ k_n[t, g_k])
            d = d * beta_v
            h = h + torch.outer(d, k_n[t, g_k])
            o[t, vh] = h @ (q_n[t, g_k] * scale)
            gate[t, vh] = g_v
            beta[t, vh] = beta_v
            state[t, vh] = h

    # z gating + norm
    z_v = z.reshape(T, V, head_v)
    z_silu = F.silu(z_v)
    o_n = F.rms_norm(o, (head_v,), norm_w, eps=1e-6)
    out_pre = o_n * z_silu  # (T, V, head_v)
    out_flat = out_pre.reshape(T, -1)  # (T, v_dim)
    out = out_flat @ W_out.t()  # (T, hidden)

    return {
        "q_proj": q,
        "k_proj": k,
        "v_proj": v,
        "z_proj": z,
        "a_proj": a,
        "b_proj": b,
        "conv_in": mixed,
        "conv_out": mixed_conv,
        "q_conv": q_c,
        "k_conv": k_c,
        "v_conv": v_c,
        "q_norm": q_n,
        "k_norm": k_n,
        "state": state,
        "gate": gate,
        "beta": beta,
        "attn_out": o,
        "norm_out": o_n,
        "z_gated": out_pre,
        "out_proj": out,
    }


def gdn_layer_tiled(x, W, T=8, K=2, r=3, head_k=4, head_v=4, hidden=8):
    """
    Candidate tiled GDN forward. Same weights but in TILED V order
    (as stored in GGUF), using tiled pairing k_head(vh) = vh % K.
    """
    V = K * r
    q_dim, k_dim, v_dim = K * head_k, K * head_k, V * head_v
    x = torch.tensor(x, dtype=torch.float64)

    W_q = torch.tensor(W["q"], dtype=torch.float64)
    W_k = torch.tensor(W["k"], dtype=torch.float64)
    W_v = torch.tensor(W["v"], dtype=torch.float64)  # V rows TILED
    W_z = torch.tensor(W["z"], dtype=torch.float64)  # TILED
    W_a = torch.tensor(W["a"], dtype=torch.float64)  # TILED
    W_b = torch.tensor(W["b"], dtype=torch.float64)  # TILED
    conv = torch.tensor(W["conv"], dtype=torch.float64)  # V channels TILED
    W_out = torch.tensor(W["out"], dtype=torch.float64)  # columns TILED
    A_log = torch.tensor(W["A_log"], dtype=torch.float64)  # TILED
    dt_bias = torch.tensor(W["dt_bias"], dtype=torch.float64)  # TILED
    norm_w = torch.tensor(W["norm_w"], dtype=torch.float64)

    q = x @ W_q.t()
    k = x @ W_k.t()
    v = x @ W_v.t()
    z = x @ W_z.t()
    a = x @ W_a.t()
    b = x @ W_b.t()

    mixed = torch.cat([q, k, v], dim=-1)
    conv_weight = conv.unsqueeze(1)
    mixed_pad = F.pad(mixed.unsqueeze(0).transpose(1, 2), (3, 0))
    mixed_conv = F.conv1d(
        mixed_pad,
        conv_weight,
        groups=conv.shape[0],
    )[0].transpose(0, 1)
    mixed_conv = F.silu(mixed_conv)

    q_c = mixed_conv[:, :q_dim].reshape(T, K, head_k)
    k_c = mixed_conv[:, q_dim : q_dim + k_dim].reshape(T, K, head_k)
    v_c = mixed_conv[:, q_dim + k_dim :].reshape(T, V, head_v)  # TILED v heads

    q_n = F.normalize(q_c, p=2, dim=-1)
    k_n = F.normalize(k_c, p=2, dim=-1)
    scale = head_k**-0.5

    state = torch.zeros(T, V, head_v, head_k, dtype=torch.float64)
    o = torch.zeros(T, V, head_v, dtype=torch.float64)
    gate = torch.zeros(T, V, dtype=torch.float64)
    beta = torch.zeros(T, V, dtype=torch.float64)
    for t in range(T):
        for s in range(V):  # s = tiled slot
            g_k = s % K  # TILED pairing
            g_v = -torch.exp(A_log[s]) * F.softplus(a[t, s] + dt_bias[s])
            beta_v = torch.sigmoid(b[t, s])
            if t == 0:
                h = torch.zeros(head_v, head_k, dtype=torch.float64)
            else:
                h = state[t - 1, s]
            h = h * torch.exp(g_v)
            d = v_c[t, s] - (h @ k_n[t, g_k])
            d = d * beta_v
            h = h + torch.outer(d, k_n[t, g_k])
            o[t, s] = h @ (q_n[t, g_k] * scale)
            gate[t, s] = g_v
            beta[t, s] = beta_v
            state[t, s] = h

    z_v = z.reshape(T, V, head_v)
    z_silu = F.silu(z_v)
    o_n = F.rms_norm(o, (head_v,), norm_w, eps=1e-6)
    out_pre = o_n * z_silu
    out_flat = out_pre.reshape(T, -1)
    out = out_flat @ W_out.t()

    return {
        "q_proj": q,
        "k_proj": k,
        "v_proj": v,
        "z_proj": z,
        "a_proj": a,
        "b_proj": b,
        "conv_in": mixed,
        "conv_out": mixed_conv,
        "q_conv": q_c,
        "k_conv": k_c,
        "v_conv": v_c,
        "q_norm": q_n,
        "k_norm": k_n,
        "state": state,
        "gate": gate,
        "beta": beta,
        "attn_out": o,
        "norm_out": o_n,
        "z_gated": out_pre,
        "out_proj": out,
    }


def make_weights(K, r, head_k, head_v, hidden, seed=7):
    """Build grouped weights, then also produce the tiled variant via the
    exact converter permutation."""
    rng = np.random.default_rng(seed)
    V = K * r
    q_dim, v_dim = K * head_k, V * head_v
    W = {
        "q": rng.normal(size=(q_dim, hidden)).astype(np.float64),
        "k": rng.normal(size=(q_dim, hidden)).astype(np.float64),
        "v": rng.normal(size=(v_dim, hidden)).astype(np.float64),
        "z": rng.normal(size=(v_dim, hidden)).astype(np.float64),
        "a": rng.normal(size=(V, hidden)).astype(np.float64),
        "b": rng.normal(size=(V, hidden)).astype(np.float64),
        "conv": rng.normal(size=(2 * q_dim + v_dim, 4)).astype(np.float64),
        "out": rng.normal(size=(hidden, v_dim)).astype(np.float64),
        "A_log": rng.normal(size=(V,)).astype(np.float64),
        "dt_bias": rng.normal(size=(V,)).astype(np.float64),
        "norm_w": rng.normal(size=(head_v,)).astype(np.float64),
    }
    Wt = {
        "q": W["q"],
        "k": W["k"],
        "v": tiled_from_grouped_rows(W["v"], K, r, head_v, 0, dim=0),
        "z": tiled_from_grouped_rows(W["z"], K, r, head_v, 0, dim=0),
        "a": tiled_from_grouped_rows(W["a"], K, r, 1, 0, dim=0),
        "b": tiled_from_grouped_rows(W["b"], K, r, 1, 0, dim=0),
        "conv": tiled_from_grouped_rows(W["conv"], K, r, head_v, 2 * q_dim, dim=0),
        "out": tiled_from_grouped_cols(W["out"], K, r, head_v, 0, dim=1),
        "A_log": tiled_from_grouped_rows(
            W["A_log"].reshape(-1, 1), K, r, 1, 0, dim=0
        ).reshape(-1),
        "dt_bias": tiled_from_grouped_rows(
            W["dt_bias"].reshape(-1, 1), K, r, 1, 0, dim=0
        ).reshape(-1),
        "norm_w": W["norm_w"],
    }
    return W, Wt


def compare(name, a, b, tol):
    a = a.detach().numpy() if torch.is_tensor(a) else np.asarray(a)
    b = b.detach().numpy() if torch.is_tensor(b) else np.asarray(b)
    if a.shape != b.shape:
        print(f"  {name:14s} SHAPE MISMATCH {a.shape} vs {b.shape}")
        return False
    md = float(np.max(np.abs(a - b)))
    ok = md < tol
    print(f"  {name:14s} {str(a.shape):16s} max-abs-diff={md:.3e}  OK={ok}")
    return ok


def run_proof(tag, K, r, head_k, head_v, hidden, T, tol=1e-12):
    V = K * r
    q_dim, v_dim = K * head_k, V * head_v
    print(
        f"\n=== {tag}: K={K} r={r} V={V} head_k={head_k} head_v={head_v} hidden={hidden} T={T} ==="
    )
    rng = np.random.default_rng(123)
    x = rng.normal(size=(T, hidden)).astype(np.float64)
    Wg, Wt = make_weights(K, r, head_k, head_v, hidden, seed=7)
    g = gdn_layer_grouped(x, Wg, T, K, r, head_k, head_v, hidden)
    t = gdn_layer_tiled(x, Wt, T, K, r, head_k, head_v, hidden)
    ok = True
    for name in [
        "q_proj",
        "k_proj",
        "v_proj",
        "z_proj",
        "a_proj",
        "b_proj",
        "conv_in",
        "conv_out",
        "q_conv",
        "k_conv",
        "v_conv",
        "q_norm",
        "k_norm",
        "state",
        "gate",
        "beta",
        "attn_out",
        "norm_out",
        "z_gated",
        "out_proj",
    ]:
        # note: V-head slots are relabeled between representations, so per-slot
        # tensors (state, gate, beta, attn_out, v_conv) differ by the head
        # permutation; the FINAL scalar output (out_proj) must match exactly.
        ok &= compare(name, g[name], t[name], tol)
    print(
        f"  >>> {tag}: out_proj max-abs-diff = "
        f"{float(torch.max(torch.abs(g['out_proj'] - t['out_proj']))):.3e}"
    )
    # Per-slot tensors MUST match up to the head relabel. tiled slot s = j*K+i
    # (i=khead, j=vpos) corresponds to grouped vh = i*r+j. The take-map G has
    # tiled[s] = grouped[G[s]]; recovering grouped from tiled needs invG.
    G = reorder_block_indices(K, r, 1).reshape(-1)  # take map (head level)
    invG = np.empty_like(G)
    invG[G] = np.arange(len(G))  # grouped[vh]=tiled[invG[vh]]
    gv = g["v_conv"].reshape(-1, V, head_v).numpy()
    tv = t["v_conv"].reshape(-1, V, head_v).numpy()
    tv_g = tv[:, invG, :]
    print(
        f"  V-conv head-perm check  max-abs-diff={np.max(np.abs(tv_g - gv)):.3e}  "
        f"(should be ~0)"
    )
    gs = g["state"].reshape(-1, V, head_v, head_k).numpy()
    ts = t["state"].reshape(-1, V, head_v, head_k).numpy()
    ts_g = ts[:, invG, :, :]
    print(
        f"  state head-perm check   max-abs-diff={np.max(np.abs(ts_g - gs)):.3e}  "
        f"(should be ~0)"
    )
    ga = g["gate"].reshape(-1, V).numpy()
    ta = t["gate"].reshape(-1, V).numpy()
    ta_g = ta[:, invG]
    print(
        f"  gate head-perm check    max-abs-diff={np.max(np.abs(ta_g - ga)):.3e}  "
        f"(should be ~0)"
    )
    return ok


if __name__ == "__main__":
    # Expert synthetic config K=2, V=6
    run_proof("synthetic K=2,V=6", 2, 3, 4, 4, 8, 6)
    # Real Qwen3.8-27B config (head 128), smaller hidden/T for speed
    run_proof("real-shape 27B K=16,V=48", 16, 3, 128, 128, 5120, 4)
