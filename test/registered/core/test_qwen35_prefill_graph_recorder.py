"""Static regression test for Qwen3.5 piecewise CUDA Graph capture."""

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_SOURCE = REPO_ROOT / "python/sglang/srt/models/qwen3_5.py"


def test_qwen35_layer_recorder_context_is_trace_safe_when_not_recording():
    source = MODEL_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    model_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Qwen3_5ForCausalLM"
    )
    forward = next(
        node
        for node in model_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "forward"
    )

    context_assignment = next(
        node
        for node in ast.walk(forward)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "layer_context"
            for target in node.targets
        )
    )
    assert isinstance(context_assignment.value, ast.IfExp)

    conditional = context_assignment.value
    assert isinstance(conditional.test, ast.Attribute)
    assert isinstance(conditional.test.value, ast.Name)
    assert conditional.test.value.id == "recorder"
    assert conditional.test.attr == "recording"
    assert isinstance(conditional.orelse, ast.Call)
    assert isinstance(conditional.orelse.func, ast.Name)
    assert conditional.orelse.func.id == "nullcontext"

    assert isinstance(conditional.body, ast.Call)
    assert isinstance(conditional.body.func, ast.Attribute)
    assert isinstance(conditional.body.func.value, ast.Name)
    assert conditional.body.func.value.id == "recorder"
    assert conditional.body.func.attr == "with_current_layer"
