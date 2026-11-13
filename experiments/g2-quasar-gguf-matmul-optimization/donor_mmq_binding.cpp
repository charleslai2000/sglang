#include <torch/extension.h>
torch::Tensor gguf_q4_0_llama_mmq_m32(torch::Tensor, torch::Tensor);
PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("run", &gguf_q4_0_llama_mmq_m32);
}
