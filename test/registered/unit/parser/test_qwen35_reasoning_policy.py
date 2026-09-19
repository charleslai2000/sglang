"""Deterministic, CPU-only tests for the narrow Qwen3.5 reasoning-effort policy.

Covered:
* effort -> (enable_thinking, steering, max_thinking_tokens) resolution;
* the configurable, provisional ladder override;
* the real M1/M2 chat templates render distinct prompts for graded tiers, and
  ``none`` closes the think block (skipped when /data is not present);
* the Qwen3.5 budget processor uses the model's real think token ids;
* serving wiring applies the policy only to the Qwen3.5 family and only routes a
  budget when the launch flag for one of the existing mechanisms is on.

No server, no GPU. The live served behaviour of the policy is intentionally NOT
verified here (that belongs to a follow-up calibration).
"""

from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=8, suite="base-a-test-cpu")

import json
import os
import unittest
from unittest.mock import Mock

import torch

from sglang.srt.entrypoints.openai.protocol import ChatCompletionRequest
from sglang.srt.entrypoints.openai.serving_chat import OpenAIServingChat
from sglang.srt.parser.qwen35_reasoning_policy import (
    DEFAULT_QWEN35_EFFORT_POLICY,
    QWEN35_TOGGLE_PARAM,
    Qwen35ReasoningPolicy,
    is_qwen35_reasoning_model,
    normalize_effort_tier,
    resolve_qwen35_reasoning_policy,
)
from sglang.srt.parser.template_detection import ReasoningToggleConfig
from sglang.srt.sampling.custom_logit_processor import (
    Qwen35ThinkingBudgetLogitProcessor,
    Qwen3ThinkingBudgetLogitProcessor,
)
from sglang.srt.environ import envs
from sglang.test.test_utils import CustomTestCase

QWEN35_RC = ReasoningToggleConfig(
    toggle_param="enable_thinking", default_enabled=True, effort_kwarg=None
)
M1_PATH = "/data/models/qwen35-9b-w4a16"
M2_PATH = "/data/models/omnicoder-9b-gptq-int4"


def _resolve(effort, model_type="qwen3_5", rc=QWEN35_RC):
    return resolve_qwen35_reasoning_policy(
        model_type=model_type, reasoning_config=rc, effort=effort
    )


class TestQwen35EffortTierResolution(CustomTestCase):
    def test_family_gate_is_narrow(self):
        self.assertTrue(is_qwen35_reasoning_model("qwen3_5", QWEN35_RC))
        self.assertTrue(is_qwen35_reasoning_model("qwen3_5_moe", QWEN35_RC))
        # Other families must not be captured by this policy.
        self.assertFalse(is_qwen35_reasoning_model("qwen3", QWEN35_RC))
        self.assertFalse(is_qwen35_reasoning_model("nemotron_3", QWEN35_RC))
        self.assertFalse(is_qwen35_reasoning_model("llama", QWEN35_RC))
        # A Qwen3.5 model whose template has no enable_thinking toggle is out.
        self.assertFalse(is_qwen35_reasoning_model("qwen3_5", None))
        self.assertFalse(
            is_qwen35_reasoning_model(
                "qwen3_5", ReasoningToggleConfig(toggle_param="thinking")
            )
        )

    def test_unset_effort_is_a_no_op(self):
        # No effort -> no policy -> no default-tier change.
        self.assertIsNone(_resolve(None))

    def test_none_disables_thinking(self):
        policy = _resolve("none")
        self.assertFalse(policy.enable_thinking)
        self.assertEqual(policy.steering, "")
        self.assertIsNone(policy.max_thinking_tokens)

    def test_graded_tiers_enable_thinking_and_differ(self):
        low, medium, high = _resolve("low"), _resolve("medium"), _resolve("high")
        for policy in (low, medium, high):
            self.assertTrue(policy.enable_thinking)
        # The previous fake behaviour was identical output for every tier.
        # The policy must not permit that: distinct steering AND budget.
        self.assertNotEqual(
            (low.steering, low.max_thinking_tokens),
            (medium.steering, medium.max_thinking_tokens),
        )
        self.assertNotEqual(
            (medium.steering, medium.max_thinking_tokens),
            (high.steering, high.max_thinking_tokens),
        )
        self.assertNotEqual(
            (low.steering, low.max_thinking_tokens),
            (high.steering, high.max_thinking_tokens),
        )
        self.assertEqual(medium.steering, "")  # neutral / default
        self.assertTrue(low.steering)
        self.assertTrue(high.steering)

    def test_xhigh_and_max_are_large_effort(self):
        high, xhigh, maximum = _resolve("high"), _resolve("xhigh"), _resolve("max")
        self.assertEqual(high.steering, xhigh.steering)
        self.assertEqual(high.max_thinking_tokens, xhigh.max_thinking_tokens)
        self.assertGreaterEqual(maximum.max_thinking_tokens, high.max_thinking_tokens)

    def test_minimal_is_smaller_than_low(self):
        minimal, low = _resolve("minimal"), _resolve("low")
        self.assertLessEqual(minimal.max_thinking_tokens, low.max_thinking_tokens)

    def test_floats_map_to_bands(self):
        self.assertEqual(normalize_effort_tier(0.0), "none")
        self.assertEqual(normalize_effort_tier(0.01), "low")
        self.assertEqual(normalize_effort_tier(0.5), "medium")
        self.assertEqual(normalize_effort_tier(0.99), "high")
        # A non-zero float is still thinking ON.
        self.assertTrue(_resolve(0.5).enable_thinking)
        self.assertFalse(_resolve(0.0).enable_thinking)

    def test_boolean_effort_is_rejected_locally(self):
        self.assertIsNone(normalize_effort_tier(True))
        self.assertIsNone(normalize_effort_tier(False))

    def test_env_ladder_override_changes_counts(self):
        base = DEFAULT_QWEN35_EFFORT_POLICY["low"]["max_thinking_tokens"]
        override = {"low": {"max_thinking_tokens": base + 123}}
        with envs.SGLANG_QWEN35_EFFORT_POLICY.override(json.dumps(override)):
            policy = _resolve("low")
        self.assertEqual(policy.max_thinking_tokens, base + 123)

    def test_env_ladder_rejects_out_of_range(self):
        override = {"high": {"max_thinking_tokens": -5}}
        with envs.SGLANG_QWEN35_EFFORT_POLICY.override(json.dumps(override)):
            policy = _resolve("high")
        self.assertIsNone(policy.max_thinking_tokens)
        self.assertTrue(policy.enable_thinking)

    def test_env_ladder_ignores_unknown_tier(self):
        override = {"bogus": {"max_thinking_tokens": 1}}
        with envs.SGLANG_QWEN35_EFFORT_POLICY.override(json.dumps(override)):
            policy = _resolve("low")
        # The unknown tier is ignored; the default ladder still resolves.
        self.assertEqual(
            policy.max_thinking_tokens,
            DEFAULT_QWEN35_EFFORT_POLICY["low"]["max_thinking_tokens"],
        )


class TestQwen35BudgetProcessor(CustomTestCase):
    START = 248068
    END = 248069
    NL = 198
    VOCAB = 250000

    def _make_req(self, origin_input_ids=None, output_ids=None):
        from array import array

        req = Mock()
        req.origin_input_ids = array("q", origin_input_ids or [])
        req.output_ids = array("q", output_ids or [])
        return req

    def test_uses_qwen35_ids_not_qwen3_ids(self):
        proc = Qwen35ThinkingBudgetLogitProcessor()
        self.assertEqual(proc.THINKING_START_TOKEN_ID, self.START)
        self.assertEqual(proc.THINKING_END_TOKEN_ID, self.END)
        # The wrong ids must not be used.
        self.assertNotEqual(
            proc.THINKING_START_TOKEN_ID,
            Qwen3ThinkingBudgetLogitProcessor.THINKING_START_TOKEN_ID,
        )
        self.assertNotEqual(
            proc.THINKING_END_TOKEN_ID,
            Qwen3ThinkingBudgetLogitProcessor.THINKING_END_TOKEN_ID,
        )
        self.assertEqual(
            (proc.THINKING_START_TOKEN_ID, proc.THINKING_END_TOKEN_ID),
            (248068, 248069),
        )

    def test_budget_exhaustion_transitions_to_answer(self):
        proc = Qwen35ThinkingBudgetLogitProcessor()
        req = self._make_req(origin_input_ids=[self.START], output_ids=[7] * 5)
        params = [{"thinking_budget": 5, "__req__": req}]

        # Not yet at the budget: untouched.
        in_budget = self._make_req(origin_input_ids=[self.START], output_ids=[7] * 2)
        logits = torch.zeros(1, self.VOCAB)
        self.assertTrue(
            torch.equal(
                proc(logits, [{"thinking_budget": 5, "__req__": in_budget}]),
                logits,
            )
        )

        # At the budget and not on a newline: force the newline token first.
        logits = torch.zeros(1, self.VOCAB)
        out = proc(logits, params)
        self.assertEqual(out[0, self.NL].item(), 0.0)
        self.assertTrue(torch.isinf(out[0, 0]) and out[0, 0] < 0)

        # Once the newline is present: force </think> (answer transition).
        req.output_ids.append(self.NL)
        logits = torch.zeros(1, self.VOCAB)
        out = proc(logits, params)
        self.assertEqual(out[0, self.END].item(), 0.0)
        self.assertTrue(torch.isinf(out[0, 0]) and out[0, 0] < 0)

    def test_does_not_touch_generation_after_think_end(self):
        proc = Qwen35ThinkingBudgetLogitProcessor()
        req = self._make_req(
            origin_input_ids=[self.START],
            output_ids=[7, 7, self.END, 7, 7],
        )
        logits = torch.zeros(1, self.VOCAB)
        self.assertTrue(
            torch.equal(proc(logits, [{"thinking_budget": 0, "__req__": req}]), logits)
        )

    def test_tool_call_tokens_after_transition_are_untouched(self):
        """The budget transition must not clobber the answer/tool-call phase.

        Once ``</think>`` has been emitted, the processor is a no-op for the
        rest of the generation, so tool-call markup produced after the
        transition is unaffected.
        """
        proc = Qwen35ThinkingBudgetLogitProcessor()
        # A plausible answer/tool-call tail after the thinking transition.
        tail = [self.END, 198, 100, 101, 102, 103]
        req = self._make_req(
            origin_input_ids=[self.START],
            output_ids=[7, 7, self.NL] + tail,
        )
        logits = torch.zeros(1, self.VOCAB)
        self.assertTrue(
            torch.equal(proc(logits, [{"thinking_budget": 0, "__req__": req}]), logits)
        )

    def test_no_thinking_block_is_untouched(self):
        proc = Qwen35ThinkingBudgetLogitProcessor()
        req = self._make_req(origin_input_ids=[100, 101], output_ids=[7])
        logits = torch.zeros(1, self.VOCAB)
        self.assertTrue(
            torch.equal(proc(logits, [{"thinking_budget": 0, "__req__": req}]), logits)
        )


class _FakeTokenizer:
    def __init__(self):
        self.calls = []
        self.chat_template = "{{ messages }}"  # non-None, so default jinja path

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return "rendered"

    def encode(self, text, add_special_tokens=False):
        return [1, 2, 3]

    def decode(self, ids):
        return "decoded"


class _FakeTokenizerManager:
    def __init__(self, model_type, flags=None):
        self.model_config = Mock()
        self.model_config.is_multimodal = False
        self.model_config.hf_config = Mock()
        self.model_config.hf_config.model_type = model_type
        self.model_config.hf_config.architectures = ["Qwen3_5ForConditionalGeneration"]
        self.tokenizer = _FakeTokenizer()
        self.server_args = Mock(default_chat_template_kwargs=None)
        self.served_model_name = "m"
        self._flags = flags or {}

    def config_value(self, name):
        return self._flags.get(name, False)


def _make_serving(model_type, flags=None, reasoning_config=QWEN35_RC):
    serving = object.__new__(OpenAIServingChat)
    serving.tokenizer_manager = _FakeTokenizerManager(model_type, flags)
    serving.template_manager = Mock(
        reasoning_config=reasoning_config,
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


class TestServingChatQwen35Wiring(CustomTestCase):
    def _run(self, model_type, effort, flags=None, messages=None):
        serving = _make_serving(model_type, flags)
        request = ChatCompletionRequest(
            model="m",
            messages=messages or [{"role": "user", "content": "hi"}],
            reasoning_effort=effort,
        )
        serving._process_messages(request, is_multimodal=False)
        tokenizer = serving.tokenizer_manager.tokenizer
        return serving, request, tokenizer.calls[-1]

    def test_none_disables_thinking_in_template_kwargs(self):
        _, request, (messages, kwargs) = self._run("qwen3_5", "none")
        self.assertIs(kwargs["enable_thinking"], False)
        # none has no steering, so no system message is injected.
        self.assertEqual([m["role"] for m in messages], ["user"])
        self.assertFalse(request._qwen35_policy.enable_thinking)

    def test_low_medium_high_render_distinct_prompts(self):
        rendered = {}
        for effort in ("low", "medium", "high"):
            _, request, (messages, kwargs) = self._run("qwen3_5", effort)
            rendered[effort] = (
                repr(messages),
                request._qwen35_max_thinking_tokens,
            )
        # No two tiers may collapse to an identical prompt+budget.
        self.assertEqual(len(set(rendered.values())), 3)
        self.assertNotEqual(rendered["low"][1], rendered["medium"][1])
        self.assertNotEqual(rendered["medium"][1], rendered["high"][1])

    def test_steering_merged_into_system_message(self):
        _, _, (messages, _) = self._run(
            "qwen3_5",
            "high",
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hi"},
            ],
        )
        system = [m for m in messages if m["role"] == "system"]
        self.assertEqual(len(system), 1)
        self.assertIn("You are helpful.", system[0]["content"])
        self.assertIn("verify your assumptions", system[0]["content"])

    def test_steering_inserted_when_no_system_message(self):
        _, _, (messages, _) = self._run("qwen3_5", "low")
        self.assertEqual(messages[0]["role"], "system")
        self.assertTrue(messages[0]["content"])

    def test_other_family_untouched(self):
        serving = _make_serving("qwen3")
        request = ChatCompletionRequest(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort="high",
        )
        serving._process_messages(request, is_multimodal=False)
        # No policy attribute / no injected system message. The template kwargs
        # are exactly what the generic protocol materialization produced; the
        # Qwen3.5 policy must not add to or rewrite them for other families.
        self.assertFalse(hasattr(request, "_qwen35_policy"))
        self.assertEqual(
            request.chat_template_kwargs,
            {"thinking": True, "enable_thinking": True},
        )

    def test_budget_route_strict_thinking(self):
        serving = _make_serving("qwen3_5", {"enable_strict_thinking": True})
        policy = _resolve("high")
        max_tokens, processor, custom_params = serving._plan_qwen35_budget(policy)
        self.assertEqual(max_tokens, policy.max_thinking_tokens)
        self.assertIsNone(processor)
        self.assertIsNone(custom_params)

    def test_budget_route_custom_logit_processor(self):
        serving = _make_serving(
            "qwen3_5", {"enable_custom_logit_processor": True}
        )
        policy = _resolve("high")
        max_tokens, processor, custom_params = serving._plan_qwen35_budget(policy)
        self.assertIsNone(max_tokens)
        self.assertIsNotNone(processor)
        self.assertEqual(
            custom_params, {"thinking_budget": policy.max_thinking_tokens}
        )

    def test_budget_not_routed_without_launch_flag(self):
        serving = _make_serving("qwen3_5", {})
        policy = _resolve("high")
        max_tokens, processor, custom_params = serving._plan_qwen35_budget(policy)
        self.assertEqual((max_tokens, processor, custom_params), (None, None, None))

    def test_none_policy_never_plans_a_budget(self):
        serving = _make_serving("qwen3_5", {"enable_strict_thinking": True})
        self.assertEqual(
            serving._plan_qwen35_budget(_resolve("none")), (None, None, None)
        )

    def _internal_request(self, model_type, effort, flags):
        serving = _make_serving(model_type, flags)
        request = ChatCompletionRequest(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            reasoning_effort=effort,
        )
        return serving._convert_to_internal_request(request)

    def test_strict_route_reaches_generate_req_input(self):
        adapted, _ = self._internal_request(
            "qwen3_5", "high", {"enable_strict_thinking": True}
        )
        self.assertEqual(adapted.max_thinking_tokens, 8192)
        self.assertIsNone(adapted.custom_logit_processor)

    def test_processor_route_reaches_sampling_params(self):
        adapted, _ = self._internal_request(
            "qwen3_5", "high", {"enable_custom_logit_processor": True}
        )
        self.assertIsNone(adapted.max_thinking_tokens)
        self.assertIsNotNone(adapted.custom_logit_processor)
        self.assertEqual(
            adapted.sampling_params["custom_params"]["thinking_budget"], 8192
        )
        # The serialized processor round-trips to the Qwen3.5 variant.
        from sglang.srt.sampling.custom_logit_processor import CustomLogitProcessor

        processor = CustomLogitProcessor.from_str(adapted.custom_logit_processor)
        self.assertIsInstance(processor, Qwen35ThinkingBudgetLogitProcessor)
        self.assertEqual(processor.THINKING_END_TOKEN_ID, 248069)

    def test_no_budget_on_unflagged_launch_but_prompt_policy_applies(self):
        adapted, _ = self._internal_request("qwen3_5", "high", {})
        self.assertIsNone(adapted.max_thinking_tokens)
        self.assertIsNone(adapted.custom_logit_processor)
        # The prompt-level policy still applies via the rendered input ids.
        self.assertTrue(adapted.input_ids)

    def test_no_budget_for_other_family(self):
        adapted, _ = self._internal_request(
            "qwen3", "high", {"enable_strict_thinking": True}
        )
        self.assertIsNone(adapted.max_thinking_tokens)


@unittest.skipUnless(
    os.path.isdir(M1_PATH) and os.path.isdir(M2_PATH),
    "Qwen3.5 model directories are not present",
)
class TestRealQwen35TemplateRender(CustomTestCase):
    """Render-level checks against the actual M1/M2 chat templates (offline)."""

    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer

        cls.tokenizers = {
            M1_PATH: AutoTokenizer.from_pretrained(M1_PATH, trust_remote_code=False),
            M2_PATH: AutoTokenizer.from_pretrained(M2_PATH, trust_remote_code=False),
        }

    def _render(self, tok, effort):
        policy = _resolve(effort)
        messages = [{"role": "user", "content": "What is 2+2?"}]
        messages = OpenAIServingChat._merge_qwen35_steering(
            [dict(m) for m in messages], policy.steering
        )
        return tok.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=policy.enable_thinking,
            reasoning_effort=effort,
        )

    def test_real_think_token_ids(self):
        for path, tok in self.tokenizers.items():
            with self.subTest(path=path):
                self.assertEqual(
                    tok.encode("<think>", add_special_tokens=False), [248068]
                )
                self.assertEqual(
                    tok.encode("</think>", add_special_tokens=False), [248069]
                )
                self.assertEqual(
                    Qwen35ThinkingBudgetLogitProcessor.THINKING_START_TOKEN_ID,
                    tok.encode("<think>", add_special_tokens=False)[0],
                )
                self.assertEqual(
                    Qwen35ThinkingBudgetLogitProcessor.THINKING_END_TOKEN_ID,
                    tok.encode("</think>", add_special_tokens=False)[0],
                )

    def test_none_closes_think_block_and_graded_tiers_differ(self):
        for path, tok in self.tokenizers.items():
            with self.subTest(path=path):
                none = self._render(tok, "none")
                low = self._render(tok, "low")
                medium = self._render(tok, "medium")
                high = self._render(tok, "high")
                # none: pre-filled closed empty think block.
                self.assertIn("<think>\n\n</think>", none)
                # thinking tiers are open and genuinely different.
                self.assertNotIn("<think>\n\n</think>", low)
                self.assertNotEqual(none, low)
                self.assertNotEqual(low, medium)
                self.assertNotEqual(medium, high)
                # steering text is present per tier (runtime policy).
                self.assertIn("concise and focused", low)
                self.assertIn("verify your assumptions", high)
                self.assertNotIn("verify your assumptions", low)

    def test_tools_render_and_budget_is_separate_from_tool_markup(self):
        """Tool calling still renders with the policy applied.

        The budget only affects the thinking phase; the tools block and the
        tool-call format are rendered by the template independently.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }
        ]
        for path, tok in self.tokenizers.items():
            with self.subTest(path=path):
                policy = _resolve("high")
                messages = [{"role": "user", "content": "weather in Paris?"}]
                messages = OpenAIServingChat._merge_qwen35_steering(
                    [dict(m) for m in messages], policy.steering
                )
                text = tok.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    tools=tools,
                    enable_thinking=policy.enable_thinking,
                    reasoning_effort="high",
                )
                self.assertIn("get_weather", text)
                self.assertIn("<tool_call>", text)

    def test_legacy_graded_tiers_were_byte_identical(self):
        """Documents the pre-fix fake behaviour at the real template level.

        Forwarding only ``reasoning_effort`` (as the old path did) leaves the
        template output identical for every graded tier, because the template
        reads no effort variable. This must stay True so the contrast with the
        policy path is real.
        """
        for path, tok in self.tokenizers.items():
            with self.subTest(path=path):
                messages = [{"role": "user", "content": "What is 2+2?"}]
                renders = {
                    effort: tok.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True,
                        reasoning_effort=effort,
                    )
                    for effort in ("minimal", "low", "medium", "high", "xhigh", "max")
                }
                self.assertEqual(len(set(renders.values())), 1)


if __name__ == "__main__":
    unittest.main()
