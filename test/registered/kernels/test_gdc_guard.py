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
    REPO_ROOT / "python/sglang/kernels/ops/mamba/triton_ops/mamba_ssm.py",
)


def _load_guard(source_path: Path, arch_supported: bool, cuda_extra):
    tree = ast.parse(source_path.read_text())
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_install_gdc_shims", "_is_gdc_supported"}
    ]

    def jit(function=None, **_kwargs):
        if function is None:
            return lambda fn: fn
        return function

    namespace = {
        "is_arch_support_pdl": lambda: arch_supported,
        "tl": SimpleNamespace(extra=SimpleNamespace(cuda=cuda_extra)),
        "triton": SimpleNamespace(jit=jit),
    }
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), source_path, "exec"),
        namespace,
    )
    namespace["_GDC_INTRINSICS_AVAILABLE"] = namespace["_install_gdc_shims"]()
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


@pytest.mark.parametrize("source_path", GDC_KERNELS)
def test_gdc_shims_fill_only_missing_intrinsics(source_path: Path):
    real_wait = object()
    cuda_extra = SimpleNamespace(gdc_wait=real_wait)
    guard = _load_guard(source_path, arch_supported=True, cuda_extra=cuda_extra)

    assert not guard()
    assert cuda_extra.gdc_wait is real_wait
    assert callable(cuda_extra.gdc_launch_dependents)


@pytest.mark.parametrize("source_path", GDC_KERNELS)
def test_sm90_dispatch_requires_real_gdc_intrinsics(source_path: Path):
    gdc = SimpleNamespace(gdc_wait=object(), gdc_launch_dependents=object())
    assert _load_guard(source_path, arch_supported=True, cuda_extra=gdc)()

    missing = SimpleNamespace()
    assert not _load_guard(source_path, arch_supported=True, cuda_extra=missing)()
