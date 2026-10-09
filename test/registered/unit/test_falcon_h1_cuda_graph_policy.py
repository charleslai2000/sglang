from pathlib import Path


SOURCE = Path(__file__).parents[3] / "python/sglang/srt/server_args.py"


def test_falcon_h1_defaults_to_eager_prefill_and_graph_decode():
    source = SOURCE.read_text()
    marker = 'if arch == "FalconH1ForCausalLM":'
    assert marker in source
    start = source.index(marker)
    block = source[start : source.index("        # Breakable", start)]
    assert "Phase.PREFILL, backend=Backend.DISABLED" in block
    assert "decode CUDA graph remains enabled" in block
    assert "_cuda_graph_config_locked" in source
