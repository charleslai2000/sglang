from types import SimpleNamespace

import torch

from sglang.srt.mem_cache.gemma_kv_owners import gemma4_kv_owner_layout
from sglang.srt.mem_cache.hybrid_cache.hybrid_pool_assembler import _swa_layer_mappings
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost


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


def test_owner_layer_mappings_are_compact_and_transfer_indices_are_component_local():
    class Pool:
        full_owner_layer_ids = [2, 4]
        swa_owner_layer_ids = [0, 1, 3, 5]
        layers_mapping = {
            0: (0, True),
            1: (1, True),
            2: (0, False),
            3: (2, True),
            4: (1, False),
            5: (3, True),
            6: (1, False),
            7: (3, True),
        }
        _transfer_owner_ids = {
            2: 0,
            4: 1,
            0: 2,
            1: 3,
            3: 4,
            5: 5,
            6: 1,
            7: 5,
        }

    full, swa = _swa_layer_mappings(Pool())
    assert full == {0: (0, 0), 1: (1, 1)}
    assert swa == {2: (0, 0), 3: (1, 1), 4: (2, 2), 5: (3, 3)}


def test_owner_pool_host_uses_compact_layer_storage():
    class DevicePool:
        layer_num = 2
        head_num = 2
        head_dim = 8
        store_dtype = torch.float16
        logical_owner_layer_ids = [2, 4]
        _hicache_logical_to_physical = {2: 0, 4: 1}

    host = object.__new__(MHATokenToKVPoolHost)
    host.device_pool = DevicePool()
    host.logical_owner_layer_ids = list(DevicePool.logical_owner_layer_ids)
    host.physical_layer_num = len(host.logical_owner_layer_ids)
    host.physical_to_logical_layer = {
        physical: logical
        for physical, logical in enumerate(host.logical_owner_layer_ids)
    }
    host.logical_to_physical_layer = {
        logical: physical
        for physical, logical in host.physical_to_logical_layer.items()
    }
    host.logical_to_device_physical_layer = DevicePool._hicache_logical_to_physical
    host.mtp_draft_device_pools = ()
    host.dtype = DevicePool.store_dtype

    assert host.get_size_per_token() == 2 * 8 * 2 * 2 * 2


def test_non_gemma_model_has_no_owner_override():
    config = SimpleNamespace(
        hf_config=SimpleNamespace(architectures=["LlamaForCausalLM"]),
        hf_text_config=SimpleNamespace(),
    )
    assert gemma4_kv_owner_layout(config) is None
