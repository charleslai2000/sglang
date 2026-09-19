"""CPU-only checks for Qwen3.5 native-effort compatibility and strict budgets."""

import unittest
from unittest.mock import Mock

from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat
from sglang.srt.parser.qwen35_reasoning_policy import (
    QWEN35_TOGGLE_PARAM,
    is_qwen35_reasoning_model,
    normalize_effort_tier,
    resolve_qwen35_reasoning_policy,
)
from sglang.srt.parser.template_detection import ReasoningToggleConfig
from sglang.test.ci.ci_register import register_cpu_ci
from sglang.test.test_utils import CustomTestCase

register_cpu_ci(est_time=8, suite="base-a-test-cpu")

QWEN35_RC = ReasoningToggleConfig(
    toggle_param="enable_thinking", default_enabled=True, effort_kwarg=None
)


def _resolve(effort, model_type="qwen3_5", rc=QWEN35_RC):
    return resolve_qwen35_reasoning_policy(
        model_type=model_type, reasoning_config=rc, effort=effort
    )


class TestQwen35NativeEffortCompatibility(CustomTestCase):
    def test_family_gate_is_narrow(self):
        self.assertTrue(is_qwen35_reasoning_model("qwen3_5", QWEN35_RC))
        self.assertTrue(is_qwen35_reasoning_model("qwen3_5_text", QWEN35_RC))
        self.assertFalse(is_qwen35_reasoning_model("qwen3", QWEN35_RC))
        self.assertFalse(is_qwen35_reasoning_model("qwen3_5", None))

    def test_native_values_are_preserved(self):
        self.assertEqual(normalize_effort_tier("low"), "low")
        self.assertEqual(normalize_effort_tier("medium"), "medium")
        self.assertEqual(normalize_effort_tier("xhigh"), "xhigh")
        self.assertEqual(normalize_effort_tier("none"), "none")

    def test_legacy_values_map_to_native_values(self):
        self.assertEqual(normalize_effort_tier("minimal"), "low")
        self.assertEqual(normalize_effort_tier("high"), "xhigh")
        self.assertEqual(normalize_effort_tier("max"), "xhigh")

    def test_floats_map_to_native_values(self):
        self.assertEqual(normalize_effort_tier(0.0), "none")
        self.assertEqual(normalize_effort_tier(0.01), "low")
        self.assertEqual(normalize_effort_tier(0.5), "medium")
        self.assertEqual(normalize_effort_tier(0.99), "xhigh")
        self.assertEqual(normalize_effort_tier(1.0), "xhigh")

    def test_none_disables_and_all_mapped_tiers_enable_thinking(self):
        self.assertFalse(_resolve("none").enable_thinking)
        for effort, native in (
            ("minimal", "low"),
            ("low", "low"),
            ("medium", "medium"),
            ("high", "xhigh"),
            ("xhigh", "xhigh"),
            ("max", "xhigh"),
        ):
            policy = _resolve(effort)
            self.assertEqual(policy.tier, native)
            self.assertTrue(policy.enable_thinking)

    def test_unset_and_invalid_values_are_noop(self):
        self.assertIsNone(_resolve(None))
        self.assertIsNone(normalize_effort_tier(True))
        self.assertIsNone(normalize_effort_tier("unsupported"))


class _FakeTokenizer:
    def __init__(self):
        self.calls = []
        self.chat_template = "{{ messages }}"

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "rendered"

    def encode(self, text, add_special_tokens=False):
        return [1, 2, 3]

    def decode(self, ids):
        return "decoded"


class _FakeTokenizerManager:
    def __init__(self, model_type):
        self.model_config = Mock()
        self.model_config.is_multimodal = False
        self.model_config.hf_config = Mock()
        self.model_config.hf_config.model_type = model_type
        self.model_config.hf_config.architectures = ["Qwen3_5ForConditionalGeneration"]
        self.tokenizer = _FakeTokenizer()
        self.server_args = Mock(default_chat_template_kwargs=None)
        self.served_model_name = "m"


class TestServingChatQwen35Wiring(CustomTestCase):
    def _make_serving(self, model_type="qwen3_5"):
        serving = object.__new__(OpenAIServingChat)
        serving.tokenizer_manager = _FakeTokenizerManager(model_type)
        serving.template_manager = Mock(
            reasoning_config=QWEN35_RC,
            chat_template_name=None,
            jinja_template_content_format="openai",
            force_reasoning=False,
        )
        serving.chat_encoding_spec = None
        serving.reasoning_parser = "qwen3"
        serving.tool_call_parser = "qwen3_coder"
        serving.is_gpt_oss = False
        serving.is_gemma4 = False
        serving.default_chat_template_kwargs = {}
        serving.default_sampling_params = {}
        serving.allowed_custom_labels = None
        serving._reasoning_detector = None
        serving._tokenizer_auto_adds_specials = False
        serving._dsv4_reasoning_effort_profile = None
        serving._inkling_default_reasoning_effort = None
        return serving

    def _run(self, effort, messages=None):
        serving = self._make_serving()
        request = ChatCompletionRequest(
            model="m",
            messages=messages or [{"role": "user", "content": "hi"}],
            reasoning_effort=effort,
        )
        serving._process_messages(request, is_multimodal=False)
        return request, serving.tokenizer_manager.tokenizer.calls[-1]

    def test_compatibility_mapping_reaches_template(self):
        request, (_, kwargs) = self._run("high")
        self.assertEqual(request.reasoning_effort, "xhigh")
        self.assertEqual(kwargs["reasoning_effort"], "xhigh")
        self.assertIs(kwargs["enable_thinking"], True)

    def test_policy_never_mutates_or_injects_messages(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
        ]
        _, (rendered_messages, _) = self._run("xhigh", messages)
        self.assertEqual(rendered_messages, messages)
        self.assertEqual([m["role"] for m in rendered_messages], ["system", "user"])
        self.assertNotIn("verify your assumptions", rendered_messages[0]["content"])

    def test_none_disables_thinking_without_injection(self):
        request, (messages, kwargs) = self._run("none")
        self.assertEqual(request.reasoning_effort, "none")
        self.assertIs(kwargs["enable_thinking"], False)
        self.assertEqual([m["role"] for m in messages], ["user"])

    def test_explicit_budget_reaches_internal_request(self):
        serving = self._make_serving()
        request = ChatCompletionRequest(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort="medium",
            max_thinking_tokens=512,
        )
        adapted, _ = serving._convert_to_internal_request(request)
        self.assertEqual(adapted.max_thinking_tokens, 512)

    def test_other_family_is_untouched(self):
        serving = self._make_serving("qwen3")
        request = ChatCompletionRequest(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort="high",
        )
        serving._process_messages(request, is_multimodal=False)
        self.assertEqual(request.reasoning_effort, "high")


if __name__ == "__main__":
    unittest.main()
