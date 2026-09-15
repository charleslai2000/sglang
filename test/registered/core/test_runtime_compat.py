import argparse
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch

from sglang.srt.distributed.device_communicators import pynccl_allocator
from sglang.srt.server_args import ServerArgs


def test_server_args_help_escapes_literal_percent():
    parser = argparse.ArgumentParser(prog="sglang serve")
    ServerArgs.add_cli_args(parser)

    help_text = parser.format_help()

    assert "67% of the kv pool at 8G/1.5G" in help_text


def _group(world_size):
    return SimpleNamespace(
        world_size=world_size,
        unique_name="test-group",
        pynccl_comm=SimpleNamespace(comm=SimpleNamespace(value=123)),
    )


def test_symmetric_memory_disabled_returns_nullcontext_without_controls(monkeypatch):
    monkeypatch.setattr(
        pynccl_allocator, "_cuda_beginAllocateCurrentThreadToPool", None
    )
    monkeypatch.setattr(pynccl_allocator, "_cuda_endAllocateToPool", None)
    monkeypatch.setattr(pynccl_allocator, "_cuda_releasePool", None)
    monkeypatch.setattr(
        pynccl_allocator, "is_symmetric_memory_enabled", lambda: True
    )

    context = pynccl_allocator.use_symmetric_memory(_group(2), disabled=True)

    assert isinstance(context, nullcontext)


def test_single_rank_symmetric_memory_returns_nullcontext_without_controls(monkeypatch):
    monkeypatch.setattr(
        pynccl_allocator, "_cuda_beginAllocateCurrentThreadToPool", None
    )
    monkeypatch.setattr(pynccl_allocator, "_cuda_endAllocateToPool", None)
    monkeypatch.setattr(pynccl_allocator, "_cuda_releasePool", None)
    monkeypatch.setattr(
        pynccl_allocator, "is_symmetric_memory_enabled", lambda: True
    )

    context = pynccl_allocator.use_symmetric_memory(_group(1))

    assert isinstance(context, nullcontext)


def test_symmetric_memory_missing_controls_fails_before_pool_creation(monkeypatch):
    missing_controls = (
        "_cuda_beginAllocateCurrentThreadToPool",
        "_cuda_endAllocateToPool",
        "_cuda_releasePool",
    )
    for name in missing_controls:
        monkeypatch.setattr(pynccl_allocator, name, None)
    pool_creation = Mock(side_effect=AssertionError("pool must not be created"))
    monkeypatch.setattr(pynccl_allocator, "get_nccl_mem_pool", pool_creation)

    with pytest.raises(RuntimeError) as exc_info:
        pynccl_allocator.SymmetricMemoryContext(_group(2))

    message = str(exc_info.value)
    assert f"Torch {torch.__version__}" in message
    assert (
        "NCCL symmetric memory requires Torch's current-thread MemPool API"
        in message
    )
    assert all(name in message for name in missing_controls)
    pool_creation.assert_not_called()


def test_symmetric_memory_uses_all_current_thread_controls(monkeypatch):
    controls = {
        name: Mock(name=name)
        for name in (
            "_cuda_beginAllocateCurrentThreadToPool",
            "_cuda_endAllocateToPool",
            "_cuda_releasePool",
        )
    }
    for name, control in controls.items():
        monkeypatch.setattr(pynccl_allocator, name, control)
    monkeypatch.setattr(
        pynccl_allocator,
        "get_nccl_mem_pool",
        lambda: SimpleNamespace(id=456),
    )
    monkeypatch.setattr(torch.cuda, "current_device", lambda: 0)
    monkeypatch.setattr(torch.cuda, "is_current_stream_capturing", lambda: False)

    context = pynccl_allocator.SymmetricMemoryContext(_group(2))
    monkeypatch.setattr(context, "_register_segments_for_comm", Mock())

    with context:
        pass

    controls["_cuda_beginAllocateCurrentThreadToPool"].assert_called_once_with(
        0, 456
    )
    controls["_cuda_endAllocateToPool"].assert_called_once_with(0, 456)
    controls["_cuda_releasePool"].assert_called_once_with(0, 456)
