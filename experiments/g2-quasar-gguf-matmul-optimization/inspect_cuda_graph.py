#!/usr/bin/env python3
"""Enumerate cudaGraphExec nodes/params through CUDA Runtime API."""

import ctypes, ctypes.util, torch, json

lib = ctypes.CDLL(ctypes.util.find_library("cudart"))
Node = ctypes.c_void_p
Graph = ctypes.c_void_p
lib.cudaGraphGetNodes.argtypes = [
    Graph,
    ctypes.POINTER(Node),
    ctypes.POINTER(ctypes.c_size_t),
]
lib.cudaGraphGetNodes.restype = ctypes.c_int
lib.cudaGraphNodeGetType.argtypes = [Node, ctypes.POINTER(ctypes.c_int)]
lib.cudaGraphNodeGetType.restype = ctypes.c_int


# cudaKernelNodeParams: func, gridDim, blockDim, sharedMemBytes, kernelParams, extra
class Dim3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_uint), ("y", ctypes.c_uint), ("z", ctypes.c_uint)]


class Params(ctypes.Structure):
    _fields_ = [
        ("func", ctypes.c_void_p),
        ("gridDim", Dim3),
        ("blockDim", Dim3),
        ("sharedMemBytes", ctypes.c_uint),
        ("kernelParams", ctypes.POINTER(ctypes.c_void_p)),
        ("extra", ctypes.POINTER(ctypes.c_void_p)),
    ]


lib.cudaGraphKernelNodeGetParams.argtypes = [Node, ctypes.POINTER(Params)]
lib.cudaGraphKernelNodeGetParams.restype = ctypes.c_int


def inspect(handle):
    n = ctypes.c_size_t()
    rc = lib.cudaGraphGetNodes(Graph(handle), None, ctypes.byref(n))
    assert rc == 0, (rc, "count")
    a = (Node * n.value)()
    rc = lib.cudaGraphGetNodes(Graph(handle), a, ctypes.byref(n))
    assert rc == 0, (rc, "nodes")
    out = []
    for i, node in enumerate(a):
        typ = ctypes.c_int()
        rc = lib.cudaGraphNodeGetType(node, ctypes.byref(typ))
        assert rc == 0
        node_ptr = node if isinstance(node, int) else node.value
        row = {"index": i, "type": typ.value, "node": hex(node_ptr)}
        if typ.value == 0:
            p = Params()
            rc = lib.cudaGraphKernelNodeGetParams(node, ctypes.byref(p))
            assert rc == 0
            row.update(
                func=hex(p.func),
                grid=[p.gridDim.x, p.gridDim.y, p.gridDim.z],
                block=[p.blockDim.x, p.blockDim.y, p.blockDim.z],
                shared=p.sharedMemBytes,
            )
        out.append(row)
    return out
