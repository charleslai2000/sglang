from pathlib import Path

# Order the isolated W4A16 attention overlay before all repository ops groups.
_here = Path(__file__).parent
_repo_ops = Path(
    "/home/ubuntu/workspaces/3rdparty/sglang-hicache/python/sglang/kernels/ops"
)
__path__ = [str(_here), str(_repo_ops)]
