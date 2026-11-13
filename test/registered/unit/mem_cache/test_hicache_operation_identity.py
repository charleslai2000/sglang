"""Operation identity survives HiCache batching for node-specific ACKs."""

import torch

from sglang.srt.managers.cache_controller import CacheOperation


def _indices(start, end):
    return torch.arange(start, end, dtype=torch.int64)


def test_cache_operation_merge_preserves_node_operation_pairs():
    first = CacheOperation(_indices(0, 2), _indices(4, 6), 17)
    second = CacheOperation(_indices(2, 5), _indices(6, 9), 23)

    merged = CacheOperation.merge_ops([first, second])

    assert merged.node_ids == [17, 23]
    assert merged.operation_ids == [first.id, second.id]
    assert merged.node_operation_ids == [(17, first.id), (23, second.id)]
    assert merged.node_host_indices == [(17, first.host_indices), (23, second.host_indices)]
    assert merged.host_indices.tolist() == [0, 1, 2, 3, 4]
    assert merged.device_indices.tolist() == [4, 5, 6, 7, 8]


def test_write_with_operation_keeps_legacy_write_contract():
    from unittest import mock

    from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
        HybridCacheController,
    )

    controller = HybridCacheController.__new__(HybridCacheController)
    controller.mem_pool_host = mock.Mock()
    host_indices = _indices(20, 23)
    controller.mem_pool_host.alloc_writeback.return_value = host_indices
    controller.mem_pool_host.resolve_host_transfers.return_value = []
    controller.write_queue = []
    controller.start_writing = mock.Mock()

    result = controller.write_with_operation(_indices(4, 7), node_id=31)
    assert result is not None
    returned_indices, operation_id = result
    assert returned_indices is host_indices
    assert operation_id == controller.write_queue[0].id
    assert controller.write_queue[0].node_operation_ids == [(31, operation_id)]
    assert controller.write_queue[0].node_host_indices == [(31, host_indices)]
    controller.start_writing.assert_called_once_with()

    legacy = controller.write(_indices(8, 11), node_id=32)
    assert legacy is host_indices
    assert controller.start_writing.call_count == 2
