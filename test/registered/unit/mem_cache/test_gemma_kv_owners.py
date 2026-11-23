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


def test_owner_device_pointer_resolution_avoids_uint64_advanced_indexing():
    class DevicePool:
        device = torch.device("cpu")
        k_data_ptrs = torch.tensor([101, 202], dtype=torch.uint64)
        v_data_ptrs = torch.tensor([303, 404], dtype=torch.uint64)
        k_buffer = ["k0", "k1"]
        v_buffer = ["v0", "v1"]
        logical_owner_layer_ids = [5, 11]
        _hicache_logical_to_physical = {5: 0, 11: 1}

    host = object.__new__(MHATokenToKVPoolHost)
    host.mtp_draft_device_pools = ()
    k_ptrs, v_ptrs, k_buffers, v_buffers = host._resolve_device_transfer_buffers(
        DevicePool()
    )

    assert k_ptrs is DevicePool.k_data_ptrs
    assert v_ptrs is DevicePool.v_data_ptrs
    assert k_buffers == ["k0", "k1"]
    assert v_buffers == ["v0", "v1"]


def test_owner_only_pointer_mapping_keeps_full_and_swa_order_stable():
    class DevicePool:
        device = torch.device("cpu")
        layer_num = 3
        head_num = 2
        head_dim = 4
        store_dtype = torch.float32
        logical_owner_layer_ids = [2, 5, 8]
        _hicache_logical_to_physical = {2: 0, 5: 1, 8: 2}
        k_data_ptrs = torch.tensor([10, 20, 30], dtype=torch.uint64)
        v_data_ptrs = torch.tensor([40, 50, 60], dtype=torch.uint64)
        k_buffer = ["k2", "k5", "k8"]
        v_buffer = ["v2", "v5", "v8"]

    host = object.__new__(MHATokenToKVPoolHost)
    host.mtp_draft_device_pools = ()
    k_ptrs, v_ptrs, k_buffers, v_buffers = host._resolve_device_transfer_buffers(
        DevicePool()
    )
    assert [int(ptr) for ptr in k_ptrs] == [10, 20, 30]
    assert [int(ptr) for ptr in v_ptrs] == [40, 50, 60]
    assert k_buffers == ["k2", "k5", "k8"]
    assert v_buffers == ["v2", "v5", "v8"]


def test_non_gemma_model_has_no_owner_override():
    config = SimpleNamespace(
        hf_config=SimpleNamespace(architectures=["LlamaForCausalLM"]),
        hf_text_config=SimpleNamespace(),
    )
    assert gemma4_kv_owner_layout(config) is None
