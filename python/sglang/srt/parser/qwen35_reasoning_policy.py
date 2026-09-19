"""Compatibility mapping for Qwen3.5-native reasoning effort.

This module deliberately does not create a prompt policy.  It only normalizes
OpenAI-style effort spellings to the values accepted by Qwen3.5 templates:
``low``, ``medium``, and ``xhigh``.  ``none`` remains the explicit off switch.

The mapping is narrow: it applies only to Qwen3.5-family models whose detected
template exposes ``enable_thinking``.  All other model families are left
untouched.  Thinking budgets are a separate, explicit request parameter; this
module must not invent one or inject any steering text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

#: ``model_type`` values that make up the Qwen3.5 family in this tree.
QWEN35_MODEL_TYPES = frozenset(
    {
        "qwen3_5",
        "qwen3_5_moe",
        "qwen3_5_text",
        "qwen3_5_moe_text",
    }
)

#: The chat-template toggle the Qwen3.5 template actually reads.
QWEN35_TOGGLE_PARAM = "enable_thinking"

EffortValue = Optional[Union[str, float]]

# Native template values. Legacy OpenAI values are intentionally normalized
# rather than forwarded, because M3's template rejects them.
_NATIVE_EFFORTS = frozenset({"low", "medium", "xhigh"})
_COMPAT_EFFORT_MAP = {
    "minimal": "low",
    "high": "xhigh",
    "max": "xhigh",
}


@dataclass(frozen=True)
class Qwen35ReasoningPolicy:
    """Normalized native effort for one request, without prompt steering."""

    tier: str
    enable_thinking: bool


# Float efforts retain the historical OpenAI-style bands while producing only
# values accepted by the native Qwen3.5 template.
_FLOAT_BANDS = (
    (0.0, "none"),
    (0.34, "low"),
    (0.67, "medium"),
    (1.01, "xhigh"),
)


def _float_band(effort: float) -> str:
    if effort <= 0.0:
        return "none"
    for upper, tier in _FLOAT_BANDS:
        if effort < upper:
            return tier
    return "xhigh"


def normalize_effort_tier(effort: EffortValue) -> Optional[str]:
    """Normalize an OpenAI-style effort to a native template value.

    Returns ``None`` for an unset or unrecognized effort, leaving the request
    unchanged. ``none`` is preserved as the explicit thinking-off value.
    """
    if effort is None or isinstance(effort, bool):
        return None
    if isinstance(effort, (int, float)):
        return _float_band(float(effort))
    if isinstance(effort, str):
        if effort == "none" or effort in _NATIVE_EFFORTS:
            return effort
        return _COMPAT_EFFORT_MAP.get(effort)
    return None


def is_qwen35_reasoning_model(
    model_type: Optional[str], reasoning_config: object
) -> bool:
    """Whether the active model declares the Qwen3.5 reasoning policy.

    Narrow on purpose: the model must be in the Qwen3.5 family **and** the
    detected template must expose the Qwen3.5 toggle. Other families (e.g.
    nemotron's ``low_effort``, mistral, Inkling) are deliberately excluded so
    their existing paths are untouched.
    """
    if model_type not in QWEN35_MODEL_TYPES:
        return False
    toggle = getattr(reasoning_config, "toggle_param", None)
    return toggle == QWEN35_TOGGLE_PARAM


def resolve_qwen35_reasoning_policy(
    *,
    model_type: Optional[str],
    reasoning_config: object,
    effort: EffortValue,
) -> Optional[Qwen35ReasoningPolicy]:
    """Resolve ``reasoning_effort`` to native Qwen3.5 template semantics.

    Returns ``None`` when this is not a Qwen3.5 reasoning model or no recognized
    effort was requested, in which case callers leave the request as-is.
    """
    if not is_qwen35_reasoning_model(model_type, reasoning_config):
        return None
    tier = normalize_effort_tier(effort)
    if tier is None:
        return None
    return Qwen35ReasoningPolicy(tier=tier, enable_thinking=tier != "none")
