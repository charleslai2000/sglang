import torch

from sglang.srt.utils.gemma4_capture import snapshot_gemma4_logits_capture


def test_snapshot_gemma4_capture_clones_reused_forward_batch_tensors(monkeypatch):
    monkeypatch.setenv("SGLANG_GEMMA4_CAPTURE_LOGITS", "1")
    input_ids = torch.tensor([2, 11, 22], dtype=torch.int64)
    positions = torch.tensor([0, 1, 2], dtype=torch.int64)
    seq_lens = torch.tensor([3], dtype=torch.int32)
    prefix_lens = torch.tensor([0], dtype=torch.int32)
    fb = type(
        "FB",
        (),
        {
            "input_ids": input_ids,
            "positions": positions,
            "extend_seq_lens": seq_lens,
            "extend_seq_lens_cpu": [3],
            "extend_prefix_lens": prefix_lens,
        },
    )()
    logits = torch.arange(12, dtype=torch.float32).reshape(1, 12)

    record = snapshot_gemma4_logits_capture(logits, fb)
    input_ids.fill_(99)
    positions.fill_(99)
    seq_lens.fill_(99)
    prefix_lens.fill_(99)
    logits.fill_(99)

    assert record["input_ids"].tolist() == [2, 11, 22]
    assert record["positions"].tolist() == [0, 1, 2]
    assert record["extend_seq_lens"].tolist() == [3]
    assert record["extend_seq_lens_cpu"] == [3]
    assert record["extend_prefix_lens"].tolist() == [0]
    assert record["output"].tolist() == [list(range(12))]
