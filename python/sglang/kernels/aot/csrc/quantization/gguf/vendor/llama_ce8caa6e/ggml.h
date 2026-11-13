#pragma once
#include <stdint.h>
#if defined(__CUDACC__)
#define GGML_COMMON_DECL_CUDA
#include "ggml-common.h"
#undef GGML_COMMON_DECL_CUDA
#elif defined(__cplusplus)
#define GGML_COMMON_DECL_CPP
#include "ggml-common.h"
#undef GGML_COMMON_DECL_CPP
#else
#define GGML_COMMON_DECL_C
#include "ggml-common.h"
#undef GGML_COMMON_DECL_C
#endif
typedef enum ggml_type { GGML_TYPE_F32=0, GGML_TYPE_F16=1, GGML_TYPE_Q4_0=2, GGML_TYPE_Q4_1=3, GGML_TYPE_Q5_0=6, GGML_TYPE_Q5_1=7, GGML_TYPE_Q8_0=8, GGML_TYPE_Q8_1=9, GGML_TYPE_Q2_K=10, GGML_TYPE_Q3_K=11, GGML_TYPE_Q4_K=12, GGML_TYPE_Q5_K=13, GGML_TYPE_Q6_K=14, GGML_TYPE_IQ2_XXS=16, GGML_TYPE_IQ2_XS=17, GGML_TYPE_IQ3_XXS=18, GGML_TYPE_IQ1_S=19, GGML_TYPE_IQ4_NL=20, GGML_TYPE_IQ3_S=21, GGML_TYPE_IQ2_S=22, GGML_TYPE_IQ4_XS=23, GGML_TYPE_I8=24, GGML_TYPE_I16=25, GGML_TYPE_I32=26, GGML_TYPE_I64=27, GGML_TYPE_F64=28, GGML_TYPE_IQ1_M=29, GGML_TYPE_BF16=30, GGML_TYPE_TQ1_0=34, GGML_TYPE_TQ2_0=35, GGML_TYPE_MXFP4=39, GGML_TYPE_NVFP4=40, GGML_TYPE_Q1_0=41, GGML_TYPE_Q2_0=42, GGML_TYPE_COUNT=43 } ggml_type;
typedef enum ggml_glu_op { GGML_GLU_OP_NONE=0 } ggml_glu_op;
typedef struct ggml_tensor { void* data; size_t nb[4]; struct ggml_tensor* view_src; struct ggml_tensor* src[10]; const char* name; } ggml_tensor;
static inline size_t ggml_nbytes(const ggml_tensor* t) { return t->nb[0]; }
