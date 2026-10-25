import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import torch

from sglang.srt.layers.logits_processor import LogitsProcessorOutput
from sglang.srt.model_executor.forward_batch_info import ForwardMode
from sglang.srt.model_executor.model_runner import ModelRunner


class TestGemma4DecodeLogitCapture(unittest.TestCase):
    def _runner_and_batch(self, graph):
        runner = ModelRunner.__new__(ModelRunner)
        runner.is_generation = True
        runner.device = torch.device("cuda")
        runner.model_config = SimpleNamespace(
            hf_config=SimpleNamespace(model_type="gemma4_text")
        )
        runner.model = SimpleNamespace(
            config=SimpleNamespace(text_config=SimpleNamespace(sliding_window=512))
        )
        runner.kv_cache_dtype_str = "fp8_e5m2"
        runner.token_to_kv_pool_allocator = SimpleNamespace(
            dtype=torch.float8_e5m2, size_full=2048, size_swa=2048
        )
        batch = SimpleNamespace(
            forward_mode=ForwardMode.DECODE,
            gemma4_forward_id="forward-id",
            gemma4_decode_step=[7],
            rids=["request-id"],
            batch_size=1,
            positions=torch.tensor([513], device="cuda"),
            input_ids=torch.tensor([107], device="cuda"),
            seq_lens_cpu=torch.tensor([514]),
        )
        output = SimpleNamespace(
            logits_output=LogitsProcessorOutput(
                next_token_logits=torch.zeros((1, 262144), device="cuda")
            ),
            can_run_graph=graph,
        )
        return runner, output, batch

    def test_disabled_is_noop(self):
        runner, output, batch = self._runner_and_batch(False)
        with patch.dict(os.environ, {}, clear=True):
            runner._capture_gemma4_decode_logits(output, batch)

    def test_enabled_records_full_logits_and_bound_decode_metadata(self):
        runner, output, batch = self._runner_and_batch(True)
        with tempfile.TemporaryDirectory() as directory:
            base = os.path.join(directory, "decode")
            with patch.dict(
                os.environ,
                {
                    "SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS": "1",
                    "SGLANG_GEMMA4_DECODE_LOGITS_FILE": base,
                    "GEMMA4_MODEL_IDENTITY": json.dumps({"revision": "pinned"}),
                },
                clear=True,
            ):
                runner._capture_gemma4_decode_logits(output, batch)
            records = [f for f in os.listdir(directory) if f.endswith(".decode")]
            self.assertEqual(len(records), 1)
            record = torch.load(os.path.join(directory, records[0]), weights_only=True)
            self.assertEqual(record["rid"], ["request-id"])
            self.assertEqual(record["decode_step"], [7])
            self.assertEqual(record["position"], [513])
            self.assertEqual(record["input_token_id"], [107])
            self.assertEqual(record["seq_len_after_kv_write"], [514])
            self.assertEqual(record["kv_cache_dtype"], "fp8_e5m2")
            self.assertTrue(record["cuda_graph_replay"])
            self.assertEqual(tuple(record["logits"].shape), (1, 262144))

    def test_non_gemma_and_non_decode_are_noop(self):
        runner, output, batch = self._runner_and_batch(False)
        runner.model_config.hf_config.model_type = "llama"
        with patch.dict(
            os.environ, {"SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS": "1"}, clear=True
        ):
            runner._capture_gemma4_decode_logits(output, batch)
        runner.model_config.hf_config.model_type = "gemma4_text"
        batch.forward_mode = ForwardMode.EXTEND
        with patch.dict(
            os.environ, {"SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS": "1"}, clear=True
        ):
            runner._capture_gemma4_decode_logits(output, batch)

    def test_capture_refuses_unaligned_metadata(self):
        runner, output, batch = self._runner_and_batch(False)
        batch.gemma4_decode_step = None
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS": "1",
                    "SGLANG_GEMMA4_DECODE_LOGITS_FILE": os.path.join(
                        directory, "decode"
                    ),
                },
                clear=True,
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "incomplete host decode metadata"
            ):
                runner._capture_gemma4_decode_logits(output, batch)


if __name__ == "__main__":
    unittest.main()
