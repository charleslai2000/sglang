import unittest
from types import SimpleNamespace

import torch

from sglang.srt.utils.gemma4_capture import snapshot_gemma4_logits_capture


class TestGemma4CaptureSnapshot(unittest.TestCase):
    def test_snapshot_survives_scheduler_tensor_reuse(self):
        batch = SimpleNamespace(
            input_ids=torch.tensor([2, 11, 22]),
            positions=torch.tensor([0, 1, 2]),
            extend_seq_lens=torch.tensor([3], dtype=torch.int32),
            extend_seq_lens_cpu=[3],
            extend_prefix_lens=torch.tensor([0], dtype=torch.int32),
        )
        logits = torch.arange(12, dtype=torch.float32).reshape(1, 12)
        capture = snapshot_gemma4_logits_capture(logits, batch)

        batch.input_ids.fill_(99)
        batch.positions.fill_(99)
        batch.extend_seq_lens.fill_(99)
        batch.extend_prefix_lens.fill_(99)
        logits.fill_(99)

        self.assertEqual(capture["input_ids"].tolist(), [2, 11, 22])
        self.assertEqual(capture["positions"].tolist(), [0, 1, 2])
        self.assertEqual(capture["extend_seq_lens"].tolist(), [3])
        self.assertEqual(capture["extend_seq_lens_cpu"], [3])
        self.assertEqual(capture["extend_prefix_lens"].tolist(), [0])
        self.assertEqual(capture["output"].tolist(), [list(range(12))])


if __name__ == "__main__":
    unittest.main()
