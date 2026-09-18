---
Status: DONE
---

## Task
Update `reasoning_effort` field description in `protocol.py` to be honest about which models support reasoning-effort capabilities.

## Scope
- File: `python/sglang/srt/entrypoints/openai/protocol.py`
- Section: Lines 869-876 (reasoning_effort Field on ChatCompletionRequest)
- Change type: Wording only, no behavior changes

## Result
Minimal edit applied:
```diff
-    reasoning_effort: ReasoningEffortType = Field(
-        default=None,
-        description="Constrains effort on reasoning for reasoning models. "
-        "Accepts string levels ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max') or a "
-        "float in [0.0, 0.99] for fine-grained control. "
-        "'none' disables reasoning entirely, 'low' is the least effort, 'high' is the most effort. "
-        "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning "
-        "in a response. 'none' defaults thinking and enable_thinking to false in "
-        "chat_template_kwargs (unless explicitly overridden). Not supported in the harmony path."
-        "'max' is an sglang extension to the OpenAI schema for "
-        "models that expose a maximum-effort tier above 'high'; models that don't "
-        "support it treat it the same as 'high'.",
-    )
+    reasoning_effort: ReasoningEffortType = Field(
+        default=None,
+        description="Constrains effort on reasoning for reasoning models when the model "
+        "exposes a reasoning-effort policy. Honors fixed tiers and the float form "
+        "for models that declare the policy; unsupported values are not guaranteed to yield "
+        "distinct behavior. For models without this policy, the field may be ignored or "
+        "honored with model-specific behavior; supported tiers vary by model family.",
+    )
```

## Evidence

### Syntax validation
```
Exit: $ python3 -m py_compile python/sglang/srt/entrypoints/openai/protocol.py
```
-pythonic check passed.

### Source after change (lines 869-876)
```
869:000791131412
reasoning_effort: ReasoningEffortType = Field(
870:000791131412
    default=None,
871:000791131412
    description="Constrains effort on reasoning for reasoning models when the model "
872:000791131412
    "exposes a reasoning-effort policy. Honors fixed tiers and the float form "
873:000791131412
    "for models that declare the policy; unsupported values are not guaranteed to yield "
874:000791131412
    "distinct behavior. For models without this policy, the field may be ignored or "
875:000791131412
    "honored with model-specific behavior; supported tiers vary by model family.",
876:000791131412
)
```

### Test search
A second occurrence of "Constrains effort on reasoning for reasoning models" exists at line 1519 of `protocol.py`, within `ReasoningEffortConfiguration` class (different from `ChatCompletionRequest`). Task scope applies only to `ChatCompletionRequest.reasoning_effort`, so line 1519 remains unchanged.

### Documentation search
No occurrences found in `docs/` directory snapshots for the old description wording.

## Defects / blockers
None.

## Remaining claims / exclusions
- Final production tier ladder not decided (as required)
- No behavior changes made
- No changes to validation, parsing, defaults, or field types
- Other occurrences in different classes in `protocol.py` are out of scope

## Terminal state: DONE
