"""Narrow reasoning-effort policy for the Qwen3.5 model family.

This is a **runtime policy**, not a claim of Qwen3.5-native behaviour. The
Qwen3.5 chat template declares a single boolean ``enable_thinking`` variable and
no graded effort variable, so ``reasoning_effort`` tiers were previously inert
(every tier collapsed to ``enable_thinking=True`` with no budget difference).
This module turns the advertised tiers into a real, model-specific policy for
models that actually declare the Qwen3.5 toggle.

The policy deliberately stays narrow:

* It only activates for the Qwen3.5 family (``model_type`` in
  :data:`QWEN35_MODEL_TYPES`) whose detected template exposes
  ``enable_thinking``. Any other model family resolves to ``None`` and is
  untouched by the serving wiring.
* It reuses the existing thinking-budget infrastructure: the resolved
  ``max_thinking_tokens`` is enforced by
  :class:`sglang.srt.sampling.custom_logit_processor.Qwen35ThinkingBudgetLogitProcessor`
  (see :mod:`sglang.srt.sampling.custom_logit_processor`), which uses this
  model's real ``<think>`` / ``</think>`` token ids (248068 / 248069).
* The steering prompts are an explicit runtime policy following the
  Qwen3.8-style design shape (steering prompt + thinking budget). They are not
  a claim that the weights were trained to obey them.

The tier -> policy ladder is provisional and configurable via the
``SGLANG_QWEN35_EFFORT_POLICY`` JSON env var. The concrete token counts are
**experimental parameters only**, not a frozen contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)

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

# --- Runtime steering prompts (runtime policy, NOT native model behaviour) ---
# low: concise / focused, avoid unnecessary elaboration.
# medium: neutral / default (no steering).
# high/xhigh/max: fuller checking, consider alternatives, verify assumptions.
STEER_LOW = (
    "Keep your reasoning concise and focused; avoid unnecessary elaboration."
)
STEER_MEDIUM = ""  # neutral / default
STEER_HIGH = (
    "Reason carefully and thoroughly: check your work, consider alternative "
    "approaches, and verify your assumptions before giving the final answer."
)


@dataclass(frozen=True)
class Qwen35ReasoningPolicy:
    """Resolved reasoning policy for one request.

    ``enable_thinking`` is always populated. ``steering`` may be empty (medium
    / default). ``max_thinking_tokens`` is ``None`` when thinking is disabled;
    otherwise it is a provisional budget in tokens.
    """

    tier: str
    enable_thinking: bool
    steering: str
    max_thinking_tokens: Optional[int]


# Provisional ladder. Token counts are EXPERIMENTAL PARAMETERS ONLY and may be
# re-tuned by calibration without changing this file (env override below).
# They are intentionally modest so a constrained-output request still reaches
# the answer transition well before a typical max_tokens window.
DEFAULT_QWEN35_EFFORT_POLICY: Dict[str, Dict[str, object]] = {
    "minimal": {
        "enable_thinking": True,
        "steering": STEER_LOW,
        "max_thinking_tokens": 256,
    },
    "low": {
        "enable_thinking": True,
        "steering": STEER_LOW,
        "max_thinking_tokens": 512,
    },
    "medium": {
        "enable_thinking": True,
        "steering": STEER_MEDIUM,
        "max_thinking_tokens": 2048,
    },
    "high": {
        "enable_thinking": True,
        "steering": STEER_HIGH,
        "max_thinking_tokens": 8192,
    },
    "xhigh": {
        "enable_thinking": True,
        "steering": STEER_HIGH,
        "max_thinking_tokens": 8192,
    },
    "max": {
        "enable_thinking": True,
        "steering": STEER_HIGH,
        "max_thinking_tokens": 16384,
    },
    "_none": {
        "enable_thinking": False,
        "steering": "",
        "max_thinking_tokens": None,
    },
}

# Float efforts are mapped to the same bands as the string tiers. A float is
# still "thinking ON" unless the caller used "none" (or the off float 0.0,
# which is the continuous spelling of the off tier).
_FLOAT_BANDS = (
    (0.0, "none"),
    (0.34, "low"),
    (0.67, "medium"),
    (1.01, "high"),
)


def _load_effort_policy() -> Dict[str, Dict[str, object]]:
    """Return the provisional ladder, with the env override applied on top.

    The override is a JSON object of the same shape; unknown keys are ignored
    so a stale override cannot crash serving. Invalid JSON falls back to the
    defaults with a warning (mirrors ``EnvField`` semantics).
    """
    policy = {k: dict(v) for k, v in DEFAULT_QWEN35_EFFORT_POLICY.items()}
    try:
        from sglang.srt.environ import envs

        override = envs.SGLANG_QWEN35_EFFORT_POLICY.get()
    except Exception:  # pragma: no cover - env module always present in srt
        override = None
    if not isinstance(override, dict):
        return policy
    for tier, spec in override.items():
        if tier not in policy or not isinstance(spec, dict):
            logger.warning(
                "SGLANG_QWEN35_EFFORT_POLICY: ignoring unknown tier/spec %r", tier
            )
            continue
        merged = dict(policy[tier])
        merged.update({k: v for k, v in spec.items() if k in merged})
        policy[tier] = merged
    return policy


def _float_band(effort: float) -> str:
    if effort <= 0.0:
        return "none"
    for upper, tier in _FLOAT_BANDS:
        if effort < upper:
            return tier
    return "high"


def normalize_effort_tier(effort: EffortValue) -> Optional[str]:
    """Map a raw ``reasoning_effort`` value to a policy tier key.

    Returns ``None`` for an unset effort (no policy, no behaviour change) and
    for values outside the recognized set (also no behaviour change; the API
    layer already rejects these).
    """
    if effort is None:
        return None
    if isinstance(effort, bool):  # pydantic rejects this; keep the guard local
        return None
    if isinstance(effort, (int, float)):
        return _float_band(float(effort))
    if isinstance(effort, str):
        if effort == "none":
            return "none"
        if effort in DEFAULT_QWEN35_EFFORT_POLICY:
            return effort
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
    policy: Optional[Dict[str, Dict[str, object]]] = None,
) -> Optional[Qwen35ReasoningPolicy]:
    """Resolve ``reasoning_effort`` into a concrete Qwen3.5 reasoning policy.

    Returns ``None`` when the model is not a Qwen3.5 reasoning model or when no
    effort was requested, in which case callers must leave the request exactly
    as-is (no default-tier change).
    """
    if not is_qwen35_reasoning_model(model_type, reasoning_config):
        return None
    tier = normalize_effort_tier(effort)
    if tier is None:
        return None
    if policy is None:
        policy = _load_effort_policy()
    key = "_none" if tier == "none" else tier
    spec = policy[key]
    enable = bool(spec["enable_thinking"])
    steering = str(spec["steering"]) if enable else ""
    budget = spec["max_thinking_tokens"]
    if not enable or budget is None:
        budget = None
    elif not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        logger.warning(
            "Qwen3.5 effort policy: invalid max_thinking_tokens %r for tier %r; "
            "disabling the budget for this request",
            budget,
            tier,
        )
        budget = None
    return Qwen35ReasoningPolicy(
        tier=tier,
        enable_thinking=enable,
        steering=steering,
        max_thinking_tokens=budget,
    )
