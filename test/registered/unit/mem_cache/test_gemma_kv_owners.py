from types import SimpleNamespace

from sglang.srt.mem_cache.gemma_kv_owners import gemma4_kv_owner_layout


def test_gemma4_owner_map_preserves_logical_layers_and_compacts_shared_layers():
    types = [
        "sliding_attention",
        "sliding_attention",
        "full_attention",
        "sliding_attention",
        "full_attention",
        "sliding_attention",
        "full_attention",
        "sliding_attention",
        "full_attention",
        "sliding_attention",
    ]
    config = SimpleNamespace(
        hf_config=SimpleNamespace(architectures=["Gemma4ForConditionalGeneration"]),
        hf_text_config=SimpleNamespace(
            num_hidden_layers=10, num_kv_shared_layers=4, layer_types=types
        ),
    )
    mapping, full_owners, swa_owners = gemma4_kv_owner_layout(config)
    assert full_owners == [2, 4]
    assert swa_owners == [0, 1, 3, 5]
    assert len(mapping) == 10
    assert mapping[6] == mapping[8] == (1, False)
    assert mapping[7] == mapping[9] == (3, True)


def test_non_gemma_model_has_no_owner_override():
    config = SimpleNamespace(
        hf_config=SimpleNamespace(architectures=["LlamaForCausalLM"]),
        hf_text_config=SimpleNamespace(),
    )
    assert gemma4_kv_owner_layout(config) is None
