"""Actual CUDA Triton layout and state-continuation regression tests."""

import pytest
import torch
import torch.nn.functional as F

from sglang.kernels.ops.attention.fla.chunk import chunk_gated_delta_rule
from sglang.kernels.ops.attention.fla.fused_recurrent import (
    fused_recurrent_gated_delta_rule_packed_decode,
)
from sglang.kernels.ops.attention.fla.fused_sigmoid_gating_recurrent import (
    fused_sigmoid_gating_delta_rule_update,
)


def check(actual, expected, tolerance=0.015):
    assert torch.isfinite(actual).all()
    error = (
        actual.float() - expected.float()
    ).norm() / expected.float().norm().clamp_min(1e-8)
    assert error < tolerance, error.item()


@pytest.mark.parametrize(
    "heads,ratio,dim,length",
    [(2, 3, 64, 1), (2, 3, 64, 65), (16, 3, 128, 129), (2, 1, 64, 17)],
)
def test_layout_and_continuation(heads, ratio, dim, length):
    torch.manual_seed(42)
    vh = heads * ratio

    def rand(*shape):
        return torch.randn(*shape, device="cuda", dtype=torch.bfloat16)

    q, k = rand(1, length, heads, dim), rand(1, length, heads, dim)
    v = rand(1, length, vh, dim)
    a, b = rand(length, vh), rand(length, vh)
    A_log = torch.full((vh,), -2.0, device="cuda")
    dt = torch.zeros(vh, device="cuda")
    g = -A_log.exp() * F.softplus(a.float() + dt)
    beta = b.float().sigmoid()
    initial = rand(1, vh, dim, dim).float() * 0.01
    indices = torch.zeros(1, dtype=torch.int32, device="cuda")
    perm = torch.arange(vh, device="cuda").reshape(heads, ratio).T.flatten()
    inverse = perm.argsort()
    result = []
    for tiled in (False, True):
        value = v[:, :, perm].contiguous() if tiled else v
        aa, bb = (a[:, perm].contiguous(), b[:, perm].contiguous()) if tiled else (a, b)
        gg, bet = (g[:, perm], beta[:, perm]) if tiled else (g, beta)
        start = initial[:, perm].contiguous() if tiled else initial.clone()
        state = start.clone()
        output, _, _ = chunk_gated_delta_rule(
            q,
            k,
            value,
            gg.unsqueeze(0).contiguous(),
            bet.unsqueeze(0).contiguous(),
            initial_state=state,
            initial_state_indices=indices,
            use_qk_l2norm_in_kernel=True,
            tiled_v_heads=tiled,
        )
        recurrent = start.clone()
        outputs = []
        # Exercise packed decode for every token and continue from nonzero state.
        for t in range(length):
            packed = torch.cat(
                (q[:, t].flatten(1), k[:, t].flatten(1), value[:, t].flatten(1)), dim=-1
            )
            out = torch.empty(1, 1, vh, dim, device="cuda", dtype=v.dtype)
            fused_recurrent_gated_delta_rule_packed_decode(
                packed,
                aa[t : t + 1],
                bb[t : t + 1],
                A_log,
                dt,
                dim**-0.5,
                recurrent,
                out,
                indices,
                use_qk_l2norm_in_kernel=True,
                tiled_v_heads=tiled,
            )
            outputs.append(out.clone())
        decoded = torch.cat(outputs, 1)
        check(decoded, output)
        check(recurrent, state)
        # Separate sigmoid recurrent entrypoint must use the same pairing.
        separate_state = start.clone()
        separate = fused_sigmoid_gating_delta_rule_update(
            A_log,
            aa,
            dt,
            1.0,
            20.0,
            q,
            k,
            value,
            bb,
            separate_state,
            indices,
            use_qk_l2norm_in_kernel=True,
            tiled_v_heads=tiled,
        )
        check(separate, decoded)
        check(separate_state, recurrent)
        # Chunked prefill must preserve state at a split within a 64-token tile.
        split = max(1, length // 2)
        chunk_state = start.clone()
        pieces = []
        for lo, hi in ((0, split), (split, length)):
            if hi == lo:
                continue
            piece, _, _ = chunk_gated_delta_rule(
                q[:, lo:hi].contiguous(),
                k[:, lo:hi].contiguous(),
                value[:, lo:hi].contiguous(),
                gg[lo:hi].unsqueeze(0).contiguous(),
                bet[lo:hi].unsqueeze(0).contiguous(),
                initial_state=chunk_state,
                initial_state_indices=indices,
                use_qk_l2norm_in_kernel=True,
                tiled_v_heads=tiled,
            )
            pieces.append(piece)
        check(torch.cat(pieces, 1), output)
        check(chunk_state, state)
        result.append(
            (
                output[:, :, inverse] if tiled else output,
                state[:, inverse] if tiled else state,
            )
        )
    check(result[1][0], result[0][0], 1e-5)
    check(result[1][1], result[0][1], 1e-5)


def test_varlen_state_slots_and_nonuniform_gates():
    torch.manual_seed(12)
    H, HV, D, T = 2, 6, 64, 70

    def rand(*shape):
        return torch.randn(*shape, device="cuda", dtype=torch.bfloat16)

    q, k, v = rand(1, T, H, D), rand(1, T, H, D), rand(1, T, HV, D)
    a, b = rand(T, HV), rand(T, HV)
    A_log = torch.linspace(-3.0, -1.0, HV, device="cuda")
    dt = torch.linspace(-1.0, 1.0, HV, device="cuda")
    indices = torch.tensor([3, 1], device="cuda", dtype=torch.int32)
    cu = torch.tensor([0, 5, T], device="cuda", dtype=torch.int32)
    initial = rand(5, HV, D, D).float() * 0.01
    perm = torch.arange(HV, device="cuda").reshape(H, HV // H).T.flatten()
    inv = perm.argsort()
    results = []
    for tiled in (False, True):
        vv = v[:, :, perm].contiguous() if tiled else v
        aa, bb = (a[:, perm].contiguous(), b[:, perm].contiguous()) if tiled else (a, b)
        al, db = (A_log[perm], dt[perm]) if tiled else (A_log, dt)
        start = initial[:, perm].contiguous() if tiled else initial.clone()
        g = (-al.exp() * F.softplus(aa.float() + db)).unsqueeze(0).contiguous()
        beta = bb.float().sigmoid().unsqueeze(0).contiguous()
        state = start.clone()
        out, _, _ = chunk_gated_delta_rule(
            q,
            k,
            vv,
            g,
            beta,
            initial_state=state,
            initial_state_indices=indices,
            cu_seqlens=cu,
            use_qk_l2norm_in_kernel=True,
            tiled_v_heads=tiled,
        )
        recurrent = start.clone()
        decoded = fused_sigmoid_gating_delta_rule_update(
            al,
            aa,
            db,
            1.0,
            20.0,
            q,
            k,
            vv,
            bb,
            recurrent,
            indices,
            cu_seqlens=cu,
            use_qk_l2norm_in_kernel=True,
            tiled_v_heads=tiled,
        )
        check(decoded, out)
        check(recurrent, state)
        torch.testing.assert_close(state[[0, 2, 4]], start[[0, 2, 4]], rtol=0, atol=0)
        results.append(
            (out[:, :, inv] if tiled else out, state[:, inv] if tiled else state)
        )
    check(results[1][0], results[0][0], 1e-5)
    check(results[1][1], results[0][1], 1e-5)
