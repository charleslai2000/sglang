// Experimental independent Q4_0 MMQ, pinned to llama.cpp ce8caa6e60a03093351d6016a818720e0d46f0fb.
// Donor algorithm/header license notices and provenance are retained under vendor/llama_ce8caa6e/.
#include <cuda_runtime.h>
#include <cuda_bf16.h>
#include <torch/all.h>
#include <c10/cuda/CUDAGuard.h>
#include <c10/cuda/CUDAException.h>
#include <ATen/cuda/CUDAContext.h>
#include <mutex>
#include "vendor/llama_ce8caa6e/ggml.h"
#include "vendor/llama_ce8caa6e/ggml-impl.h"
#include <cstddef>
#define GGML_API extern
#include "vendor/llama_ce8caa6e/ggml-cuda.h"
#include "vendor/llama_ce8caa6e/common.cuh"
#include "vendor/llama_ce8caa6e/vecdotq.cuh"
#include "vendor/llama_ce8caa6e/mma.cuh"
#include "vendor/llama_ce8caa6e/mmq.cuh"
#include "vendor/llama_ce8caa6e/mmq-load-tiles.cuh"
#include "vendor/llama_ce8caa6e/mmq-vec-dot.cuh"
using namespace ggml_cuda_mma;
#include "vendor/llama_ce8caa6e/quantize.cuh"
#include "vendor/llama_ce8caa6e/quantize.cu"

namespace llama_donor {
template __global__ void quantize_mmq_q8_1<MMQ_Q8_1_DS_LAYOUT_D4, false>(
    const float*, const int32_t*, void*, int64_t, int64_t, int64_t, int64_t, int64_t, int, int, int);
}

namespace {
__global__ void bf16_to_f32(const __nv_bfloat16* x, float* y, int64_t n) {
    const int64_t i = (int64_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) y[i] = __bfloat162float(x[i]);
}

struct DeviceInfo { int cc; int sms; int warp; };
static DeviceInfo device_info() {
    int d = 0; cudaDeviceProp p{};
    C10_CUDA_CHECK(cudaGetDevice(&d));
    C10_CUDA_CHECK(cudaGetDeviceProperties(&p, d));
    return {p.major * 100 + p.minor * 10, p.multiProcessorCount, p.warpSize};
}

static size_t shared_size(const ggml_cuda_mmq_config& c, int cc) {
    const size_t ids = c.J * sizeof(int);
    const size_t x = ggml_cuda_mmq_get_nbytes_shared_x(c, cc);
    const size_t y = c.J * sizeof(block_q8_1_mmq);
    return ids + x + GGML_PAD(y, c.nthreads * sizeof(int));
}

static void launch_q4_m32(const uint8_t* w, const block_q8_1_mmq* xq, float* out,
                          int n, int k, float* tmp, cudaStream_t stream) {
    constexpr int J = 32;
    constexpr bool fallback = true;
    const auto d = device_info();
    TORCH_CHECK(d.cc >= GGML_CUDA_CC_AMPERE, "llama Q4_0 M32 requires SM80+");
    const auto c = ggml_cuda_mmq_get_config(GGML_TYPE_Q4_0, J, fallback, d.cc);
    TORCH_CHECK(c.type == GGML_TYPE_Q4_0 && c.I == 128 && c.K_vram == 256 && c.stream_k,
                "unexpected pinned Q4_0 MMQ specialization");
    TORCH_CHECK(k % c.K_vram == 0 && n % c.I == 0, "unsupported donor shape");
    const int ntx = 1, nty = n / c.I, tiles = ntx * nty;
    const int waves = (tiles + d.sms - 1) / d.sms;
    const int efficiency = 100 * tiles / (d.sms * waves);
    const int blocks = (GGML_CUDA_CC_IS_NVIDIA(d.cc) && efficiency >= 90) ? tiles : d.sms;
    const bool fix = tiles % blocks != 0;
    TORCH_CHECK(!fix || tmp, "stream-K fixup workspace required");
    const int smem = (int)shared_size(c, d.cc);
    C10_CUDA_CHECK(cudaFuncSetAttribute(mul_mat_q<GGML_TYPE_Q4_0, J, fallback>,
        cudaFuncAttributeMaxDynamicSharedMemorySize, smem));
    const dim3 block(d.warp, c.nthreads / d.warp, 1);
    const dim3 grid(blocks, 1, 1);
    const auto bpk = init_fastdiv_values(k / QK4_0);
    const auto ntxfd = init_fastdiv_values(ntx);
    const auto one = init_fastdiv_values(1);
    mul_mat_q<GGML_TYPE_Q4_0, J, fallback><<<grid, block, smem, stream>>>(
        (const char*)w, (const int*)xq, nullptr, nullptr, out, tmp, nullptr,
        bpk, n, 32, k / QK4_0, n, n, one, one, 0, 0, 0, one, one, 0, 0, 0, ntxfd);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    if (fix) {
        const dim3 fix_grid(blocks, c.I / d.warp, 1);
        const dim3 fix_block(d.warp, (c.nthreads / d.warp) / 2, 1);
        mul_mat_q_stream_k_fixup<GGML_TYPE_Q4_0, J, fallback><<<fix_grid, fix_block, 0, stream>>>(
            nullptr, nullptr, out, tmp, bpk, n, 32, n, one, 0, one, 0, ntxfd);
        C10_CUDA_KERNEL_LAUNCH_CHECK();
    }
}
} // namespace

torch::Tensor gguf_q4_0_llama_mmq_m32(torch::Tensor W, torch::Tensor X) {
    TORCH_CHECK(W.is_cuda() && X.is_cuda() && W.device() == X.device(), "expected same-device CUDA tensors");
    TORCH_CHECK(W.scalar_type() == torch::kUInt8 && X.scalar_type() == torch::kBFloat16,
                "expected packed Q4_0 uint8 weights and BF16 activations");
    TORCH_CHECK(W.dim() == 2 && X.dim() == 2 && X.size(0) == 32 && X.is_contiguous() && W.is_contiguous(),
                "expected contiguous M32 matrices");
    const int n = W.size(0), k = X.size(1);
    TORCH_CHECK(k % 512 == 0 && n % 128 == 0 && W.size(1) == k / 32 * 18,
                "unsupported Q4_0 packed geometry");
    at::cuda::CUDAGuard guard(X.device());
    const auto stream = at::cuda::getCurrentCUDAStream(X.device().index()).stream();
    const auto d = device_info();
    const auto c = ggml_cuda_mmq_get_config(GGML_TYPE_Q4_0, 32, true, d.cc);
    TORCH_CHECK(c.type == GGML_TYPE_Q4_0 && c.stream_k, "Q4_0 donor config unavailable");
    auto xf_flat = torch::empty({32LL * k}, X.options().dtype(torch::kFloat32));
    constexpr int qk8_1_mmq = 128;
    const int qblocks = k / qk8_1_mmq;
    const int64_t q8_bytes = (int64_t)32 * qblocks * (int64_t)sizeof(block_q8_1_mmq);
    auto q8 = torch::empty({q8_bytes}, X.options().dtype(torch::kUInt8));
    auto q8f32 = torch::empty({32LL * k}, X.options().dtype(torch::kFloat32));
    auto out = torch::empty({32, n}, X.options().dtype(torch::kFloat32));
    bf16_to_f32<<<(32LL * k + 255) / 256, 256, 0, stream>>>(
        (const __nv_bfloat16*)X.data_ptr(), (float*)xf_flat.data_ptr(), 32LL * k);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    const int qblocks_per_row = k / QK8_1_MMQ;
    llama_donor::quantize_mmq_q8_1<MMQ_Q8_1_DS_LAYOUT_D4, false><<<
        dim3(32, (k + 4 * CUDA_QUANTIZE_BLOCK_SIZE_MMQ - 1) / (4 * CUDA_QUANTIZE_BLOCK_SIZE_MMQ), 1),
        CUDA_QUANTIZE_BLOCK_SIZE_MMQ, 0, stream>>>(
        (const float*)xf_flat.data_ptr(), nullptr, q8.data_ptr(), k, (int64_t)k * sizeof(float),
        (int64_t)qblocks_per_row * sizeof(block_q8_1_mmq), (int64_t)32 * qblocks_per_row * sizeof(block_q8_1_mmq),
        k, qblocks_per_row, 1, 1);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    const int tiles = (n + c.I - 1) / c.I;
    const int waves = (tiles + d.sms - 1) / d.sms;
    const int efficiency = 100 * tiles / (d.sms * waves);
    const int blocks = (GGML_CUDA_CC_IS_NVIDIA(d.cc) && efficiency >= 90) ? tiles : d.sms;
    auto tmp = torch::empty({tiles % blocks ? (int64_t)blocks * c.J * c.I : 0}, X.options().dtype(torch::kFloat32));
    launch_q4_m32((const uint8_t*)W.data_ptr(), (const block_q8_1_mmq*)q8.data_ptr(),
                  (float*)out.data_ptr(), n, k, (float*)tmp.data_ptr(), stream);
    return out.to(X.scalar_type());
}
