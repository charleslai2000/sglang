"""Register strict-last GSM8K extractor for the lm-eval task."""

import re
from lm_eval.api.filter import Filter
from lm_eval.api.registry import register_filter
from lm_eval.api.metrics import exact_match_hf_evaluate


@register_filter("gsm8k-strict-last")
class StrictLast(Filter):
    def apply(self, resps, docs):
        out = []
        for group in resps:
            text = group[0] if group else ""
            matches = list(re.finditer(r"#### (-?[0-9.,]+)", text))
            out.append([matches[-1].group(1).strip() if matches else "[invalid]"])
        return out


def strict_exact_match(prediction, target):
    return exact_match_hf_evaluate(
        [prediction],
        [target],
        regexes_to_ignore=[",", r"\\$", r"(?s).*#### ", r"\\.$"],
        ignore_case=True,
        ignore_punctuation=False,
    )["exact_match"]
