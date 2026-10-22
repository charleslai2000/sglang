"""CPU tests for Gemma component snapshot identity and Fail-Closed range checks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

SCRIPT = Path(__file__).with_name("runtime-layer-components-capture.py")
_spec = importlib.util.spec_from_file_location("gemma_component_capture", SCRIPT)
_capture_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_capture_module)


class _ForwardMode:
    name = "EXTEND"

    @staticmethod
    def is_extend():
        return True

    @staticmethod
    def is_decode():
        return False


def _batch(ids, positions):
    return SimpleNamespace(
        batch_size=1,
        gemma4_forward_id="forward-uuid-1",
        rids=["request-rid-1"],
        input_ids=torch.tensor(ids),
        positions=torch.tensor(positions),
        seq_lens=torch.tensor([6]),
        extend_seq_lens=torch.tensor([4]),
        extend_prefix_lens=torch.tensor([2]),
        extend_seq_lens_cpu=[4],
        extend_prefix_lens_cpu=[2],
        out_cache_loc=torch.tensor([20, 21, 22, 23]),
        req_pool_indices=torch.tensor([3]),
        forward_mode=_ForwardMode(),
        is_prefill_only=True,
        batch_slot_offsets=None,
    )


def test_extend_snapshot_binds_uuid_ids_positions_slot_and_query_range(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA4_COMPONENT_STATE_FILE", str(tmp_path))
    monkeypatch.setenv("GEMMA4_COMPONENT_LAYER", "18")
    batch = _batch([30, 31, 32, 33], [3, 4, 5, 6])
    tensor = torch.arange(16, dtype=torch.float32).reshape(4, 4)

    _capture_module.capture(SimpleNamespace(layer_id=18), "q", tensor, batch.positions, batch)

    path = tmp_path / "component.request-rid-1.forward-uuid-1.layer18.q.json"
    rec = json.loads(path.read_text())
    assert rec["forward_id"] == "forward-uuid-1"
    assert rec["rid"] == rec["batch_slot_rid"] == "request-rid-1"
    assert rec["forward_mode"] == "EXTEND"
    assert rec["batch_slot"] == 0
    assert rec["batch_slot_req_pool_index"] == 3
    assert rec["step_input_ids"] == [30, 31, 32, 33]
    assert rec["step_positions"] == rec["token_context_positions"] == [3, 4, 5, 6]
    assert rec["extend_seq_lens"] == [4]
    assert rec["extend_prefix_lens"] == [2]
    assert rec["query_token_range_in_request"] == [2, 6]
    assert rec["shape"] == [4, 4]
    assert len(rec["value"]) == 4


def test_extend_snapshot_fails_closed_on_tensor_token_range_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMMA4_COMPONENT_STATE_FILE", str(tmp_path))
    monkeypatch.setenv("GEMMA4_COMPONENT_LAYER", "18")
    batch = _batch([30, 31, 32, 33], [3, 4, 5, 6])
    with pytest.raises(RuntimeError, match="range mismatch"):
        _capture_module.capture(
            SimpleNamespace(layer_id=18), "q", torch.zeros(3, 4), batch.positions, batch
        )
    assert not list(tmp_path.glob("*.json"))
