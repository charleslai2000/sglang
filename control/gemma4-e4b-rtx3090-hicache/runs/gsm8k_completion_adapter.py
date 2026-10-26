"""lm-eval completion adapter for audited, single-prompt GSM8K generation."""

import hashlib
import json
import os

import requests

from lm_eval.api.model import LM
from lm_eval.api.registry import register_model
from lm_eval.models.utils import handle_stop_sequences, postprocess_generated_text


@register_model("gsm8k-gemma-completions")
class GSM8KGemmaCompletions(LM):
    def __init__(
        self,
        base_url,
        model,
        tokenizer,
        trust_remote_code=True,
        timeout=1800,
        max_gen_toks=512,
        seed=1234,
        **kwargs,
    ):
        super().__init__()
        from transformers import AutoTokenizer

        self.base_url = base_url
        self.model = model
        self.timeout = int(timeout)
        self._max_gen_toks = int(max_gen_toks)
        self._seed = int(seed)
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer, trust_remote_code=trust_remote_code
        )
        self.tokenizer.truncation_side = "left"

    @property
    def tokenizer_name(self):
        return str(getattr(self.tokenizer, "name_or_path", ""))

    def chat_template(self, chat_template=False):
        return self.tokenizer.chat_template or ""

    def apply_chat_template(self, chat_history, add_generation_prompt=True):
        # The official GSM8K task intentionally scores plain Question/Answer
        # text, not Gemma chat messages. Preserve that exact concatenated text.
        parts = []
        for message in chat_history:
            content = message["content"]
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )
            parts.append(str(content))
        return "".join(parts)

    @property
    def eot_token_id(self):
        return self.tokenizer.eos_token_id

    @property
    def max_length(self):
        return 8192

    @property
    def max_gen_toks(self):
        return self._max_gen_toks

    def tok_encode(self, text, **kwargs):
        return self.tokenizer.encode(text, add_special_tokens=True)

    def tok_decode(self, tokens, **kwargs):
        return self.tokenizer.decode(tokens, skip_special_tokens=False)

    def generate_until(self, requests_, disable_tqdm=False):
        from tqdm import tqdm

        out = []
        for req in tqdm(requests_, disable=disable_tqdm):
            prompt, gen_kwargs = req.args
            ids = self.tok_encode(prompt)
            eos = self.tokenizer.decode(self.tokenizer.eos_token_id)
            stops = handle_stop_sequences(gen_kwargs.get("until"), eos)
            payload = {
                "prompt": ids,
                "model": self.model,
                "max_tokens": int(gen_kwargs.get("max_gen_toks", self._max_gen_toks)),
                "temperature": 0.0,
                "top_p": 1.0,
                "stop": stops,
                "return_logprob": False,
                "seed": self._seed,
                "return_token_ids": True,
            }
            response = requests.post(self.base_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            body = response.json()
            choice = body["choices"][0]
            raw = choice.get("text", "")
            record = {
                "doc_id": getattr(req, "doc_id", None),
                "prompt_sha256": hashlib.sha256(
                    json.dumps(ids, separators=(",", ":")).encode()
                ).hexdigest(),
                "request_id": body.get("id"),
                "requested_stop": stops,
                "finish_reason": choice.get("finish_reason"),
                "matched_stop": choice.get("matched_stop"),
                "prompt_tokens": body.get("usage", {}).get("prompt_tokens"),
                "completion_tokens": body.get("usage", {}).get("completion_tokens"),
                "raw_completion": raw,
                "response_token_ids": choice.get("token_ids") or [],
            }
            audit_path = os.environ.get("GSM8K_STOP_AUDIT")
            if audit_path:
                with open(audit_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            # SGLang may report the first token of a string stop (e.g. token
            # 106 == 'Question') instead of the full stop string. Its completion
            # response text is already stop-trimmed; use that exact text verbatim.
            clean = postprocess_generated_text(raw, stops, None)
            out.append(clean)
        return out

    def loglikelihood(self, requests_):
        raise NotImplementedError

    def loglikelihood_rolling(self, requests_):
        raise NotImplementedError
