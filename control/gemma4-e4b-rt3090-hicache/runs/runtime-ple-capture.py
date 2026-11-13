"""Retained design note for the opt-in PLE diagnostic.

The actual capture is implemented in Gemma4TextModel.forward adjacent to the
per_layer_input selection, under SGLANG_GEMMA4_CAPTURE_PLE. That location is the
only source that can bind the already-computed context-aware PLE tensor to the
current ForwardBatch without re-running model math or relying on spawn hooks.
"""
