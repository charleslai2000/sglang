/* Copyright 2026 SGLang Team.
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once
#include <torch/all.h>
torch::Tensor gguf_q4_0_llama_mmq_m32(torch::Tensor W, torch::Tensor X);
