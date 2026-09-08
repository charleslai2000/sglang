"""Regression tests for the Triton GDC feature guard."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).parents[3]
GDC_KERNELS = (
    REPO_ROOT
    / "python/sglang/kernels/ops/attention/fla/fused_norm_gate.py",
    REPO_ROOT
    / "python/sglang/kernels/ops/attention/fla/fused_sigmoid_gating_recurrent.py",
    REPO_ROOT
    / "python/sglang/kernels/ops/attention/fla/layernorm_gated.py",
    REPO_ROOT
    / "python/sglang/kernels/ops/attention/fla/fused_kda_conv_recurrent_verify.py",
    REPO_ROOT / "python/sglang/kernels/ops/mamba/causal_conv1d_triton.py",
)


def _load_guard(source_path: Path, arch_supported: bool, cuda_extra):
    tree = ast.parse(source_path.read_text())
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_is_gdc_supported"
    )
    namespace = {
        "is_arch_support_pdl": lambda: arch_supported,
        "tl": SimpleNamespace(extra=SimpleNamespace(cuda=cuda_extra)),
    }
    exec(
        compile(ast.Module(body=[guard], type_ignores=[]), source_path, "exec"),
        namespace,
    )
    return namespace["_is_gdc_supported"]


@pytest.mark.parametrize("source_path", GDC_KERNELS)
def test_gdc_guard_requires_arch_and_both_triton_intrinsics(source_path: Path):
    gdc = SimpleNamespace(gdc_wait=object(), gdc_launch_dependents=object())
    assert not _load_guard(source_path, arch_supported=False, cuda_extra=gdc)()
    assert not _load_guard(
        source_path,
        arch_supported=True,
        cuda_extra=SimpleNamespace(gdc_wait=object()),
    )()
    assert _load_guard(source_path, arch_supported=True, cuda_extra=gdc)()
