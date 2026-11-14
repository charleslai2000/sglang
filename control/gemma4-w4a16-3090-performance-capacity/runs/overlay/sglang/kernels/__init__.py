from pkgutil import extend_path

# Allow repository kernel packages to supply the rest of sglang.kernels.
__path__ = extend_path(__path__, __name__)
from sglang.kernels import ops
