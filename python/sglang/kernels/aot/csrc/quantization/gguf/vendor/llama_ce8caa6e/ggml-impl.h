#pragma once
#include "ggml.h"
#include <cstdio>
#include <cstdlib>
#define GGML_UNUSED(x) ((void)(x))
#define GGML_UNUSED_VARS(...) ((void)0)
#define GGML_ASSERT(x) do { if (!(x)) abort(); } while(0)
#define GGML_ABORT(...) do { abort(); } while(0)
#define GGML_PAD(x,n) (((x)+(n)-1)/(n)*(n))
#define GGML_MAX_SRC 10
#define GGML_CUDA_MAX_DEVICES 16
#define GGML_CUDA_NAME "cuda"
#define GGML_LOG_DEBUG(...) ((void)0)
