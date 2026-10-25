"""lm_eval adapter preserving one official Gemma user turn for SGLang."""

import json

from lm_eval.api.registry import register_model
from lm_eval.models.api_models import JsonChatStr
from lm_eval.models.openai_completions import LocalChatCompletion


@register_model("gemma-chat-preserve-messages")
class GemmaChatPreserveMessages(LocalChatCompletion):
    """Render using the pinned tokenizer, then pass the original user message."""

    def __init__(self, *args, **kwargs):
        kwargs["tokenized_requests"] = False
        super().__init__(*args, **kwargs)

    def apply_chat_template(self, chat_history, add_generation_prompt=True):
        # Exercise the pinned canonical template API, but return original messages
        # so the server owns exactly one application of that same template.
        self.tokenizer.apply_chat_template(
            chat_history,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            continue_final_message=not add_generation_prompt,
        )
        return JsonChatStr(json.dumps(chat_history, ensure_ascii=False))

    def create_message(self, messages, generate=False):
        if isinstance(messages[0], JsonChatStr):
            return json.loads(messages[0].prompt)
        if isinstance(messages[0], str):
            return [{"role": "user", "content": messages[0]}]
        return messages

    def _create_payload(self, messages, generate=False, gen_kwargs=None, **kwargs):
        gen_kwargs = dict(gen_kwargs or {})
        gen_kwargs.pop("do_sample", None)
        max_tokens = gen_kwargs.pop(
            "max_tokens", gen_kwargs.pop("max_gen_toks", self._max_gen_toks)
        )
        temperature = gen_kwargs.pop("temperature", 0)
        stop = gen_kwargs.pop("until", None) or []
        if isinstance(stop, str):
            stop = [stop]
        return {
            "messages": messages,
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": stop[:4],
            "seed": kwargs.get("seed", self._seed),
            **gen_kwargs,
        }
