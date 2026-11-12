#include <ggml.h>
#include <ggml-backend.h>
#include <ggml-cuda.h>
#include <ggml-cpu.h>
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <algorithm>

int main(int argc, char **argv) {
    if (argc != 6) { fprintf(stderr, "usage: %s q4-weight-raw K N M input-f32-raw\n", argv[0]); return 2; }
    const int64_t K = atoll(argv[2]), N = atoll(argv[3]), M = atoll(argv[4]);
    ggml_backend_t backend = ggml_backend_cuda_init(0);
    if (!backend) { fprintf(stderr, "CUDA backend init failed\n"); return 3; }
    ggml_init_params p{64*1024*1024, nullptr, true};
    ggml_context *ctx = ggml_init(p);
    ggml_tensor *w = ggml_new_tensor_2d(ctx, GGML_TYPE_Q4_0, K, N);
    ggml_tensor *x = ggml_new_tensor_2d(ctx, GGML_TYPE_F32, K, M);
    ggml_tensor *y = ggml_mul_mat(ctx, w, x);
    ggml_cgraph *graph = ggml_new_graph(ctx);
    ggml_build_forward_expand(graph, y);
    ggml_backend_register(ggml_backend_cpu_reg());
    ggml_backend_t backends[] = {backend, ggml_backend_cpu_init()};
    if (!backends[1]) { fprintf(stderr, "CPU backend init failed\n"); return 8; }
    ggml_backend_sched_t sched = ggml_backend_sched_new(backends, nullptr, 2, 128, false, true);
    ggml_backend_sched_set_tensor_backend(sched, y, backend);
    if (!ggml_backend_sched_alloc_graph(sched, graph)) { fprintf(stderr, "graph allocation failed\n"); return 4; }
    const size_t wbytes = ggml_nbytes(w);
    std::vector<unsigned char> wb(wbytes);
    FILE *f = fopen(argv[1], "rb"); if (!f || fread(wb.data(), 1, wbytes, f) != wbytes) { fprintf(stderr, "weight read failed, expected %zu bytes\n", wbytes); return 5; }
    fclose(f);
    std::vector<float> xb(K*M);
    FILE *xf = fopen(argv[5], "rb"); if (!xf || fread(xb.data(), sizeof(float), xb.size(), xf) != xb.size()) { fprintf(stderr, "input read failed\n"); return 9; }
    fclose(xf);
    ggml_backend_tensor_set(w, wb.data(), 0, wbytes);
    ggml_backend_tensor_set(x, xb.data(), 0, xb.size()*sizeof(float));
    for (int i=0;i<5;i++) if (ggml_backend_sched_graph_compute(sched, graph) != GGML_STATUS_SUCCESS) return 6;
    ggml_backend_sched_synchronize(sched);
    std::vector<float> ms(30);
    for (int i=0;i<30;i++) {
        cudaEvent_t a,b; cudaEventCreate(&a); cudaEventCreate(&b); cudaEventRecord(a);
        if (ggml_backend_sched_graph_compute(sched, graph) != GGML_STATUS_SUCCESS) return 7;
        ggml_backend_sched_synchronize(sched); cudaEventRecord(b); cudaEventSynchronize(b); cudaEventElapsedTime(&ms[i],a,b); cudaEventDestroy(a); cudaEventDestroy(b);
    }
    std::sort(ms.begin(),ms.end());
    std::vector<float> out(N*M); ggml_backend_tensor_get(y, out.data(), 0, out.size()*sizeof(float));
    printf("{\"K\":%lld,\"N\":%lld,\"M\":%lld,\"weight_bytes\":%zu,\"median_ms\":%.9f,\"p10_ms\":%.9f,\"p90_ms\":%.9f,\"output\":[",(long long)K,(long long)N,(long long)M,wbytes,ms[15],ms[3],ms[26]);
    for (int i=0;i<(int)out.size();i++) printf("%s%.9g",i?",":"",out[i]);
    printf("]}\n");
    ggml_backend_sched_free(sched); ggml_free(ctx); ggml_backend_free(backend); return 0;
}
