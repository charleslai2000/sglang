#!/usr/bin/env python3
"""Capture the opt-in donor backend on SGLang's real Full CUDA Graph stream.

Requires the SGLang runtime overlay to load the model and enter FullCudaGraphBackend.capture_one.
The runner must invoke `capture_borrowed_q4_0(shape)` within the active forward_fn,
then call replay_borrowed_q4_0(shape) on the same captured graph.
"""

import torch


def capture_borrowed_q4_0(backend, qweight, activation, shape):
    """Attach one Q4_0 layer to a persistent exact-pin backend handle."""
    handle = backend._t004_handles.get(shape)
    if handle is None:
        handle = backend._t004_ext.create_borrowed(qweight, activation)
        assert backend._t004_ext.info(handle)[0] == qweight.data_ptr()
        backend._t004_handles[shape] = handle
    backend._t004_ext.run(handle)
    return handle


def replay_borrowed_q4_0(backend, shape):
    handle = backend._t004_handles[shape]
    backend._t004_ext.run(handle)


# The probe is deliberately not imported by service code until its owner has
# validated the full service integration. It provides the narrow capture/replay
# seam and enforces no full-weight copy; activation input is copied into the
# persistent graph input workspace in the binding before capture, then callers
# must update that workspace from the fixed SGLang input buffer on each replay.
