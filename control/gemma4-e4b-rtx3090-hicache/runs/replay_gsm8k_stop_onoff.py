#!/usr/bin/env python3
"""Locked single-request RTX3090 Stop ON/OFF replay for frozen GSM8K examples."""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests
import torch
from transformers import AutoTokenizer

ROOT = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
DATA = Path("/data/sglang-hicache/gemma4")
VENV = Path("/home/ubuntu/venvs/sglang-3090")
MODEL = DATA / "model"
RUN = DATA / "runs/20261026T-gsm8k-stop-onoff-rerun"
FIXTURE = RUN / "cases.json"
PORT = 31225
LOCK = Path("/tmp/f1-r16b-gpu-exclusive.lock")
IDENTITY = {
    "model_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
    "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
}


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "a+")
    import fcntl

    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("RTX3090 GPU lock unavailable")

    env = os.environ.copy()
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONPATH=f"{ROOT}/control/gemma4-e4b-rtx3090-hicache/runs:{ROOT}/python:{DATA}/aot-sm86-build:{ROOT}/3rdparty/sglang/python/sglang/kernels/aot/python",
        LD_LIBRARY_PATH=f"{VENV}/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64",
        GEMMA4_MODEL_IDENTITY=json.dumps(IDENTITY),
        SGLANG_GEMMA4_CAPTURE_LOGITS="1",
        SGLANG_GEMMA4_LOGITS_FILE=str(RUN / "forward"),
    )
    cmd = [
        str(VENV / "bin/python"),
        "-m",
        "sglang.launch_server",
        "--model-path",
        str(MODEL),
        "--trust-remote-code",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--context-length",
        "8192",
        "--max-running-requests",
        "1",
        "--mem-fraction-static",
        ".94",
        "--disable-radix-cache",
        "--kv-cache-dtype",
        "bf16",
        "--attention-backend",
        "triton",
        "--cuda-graph-max-bs-decode",
        "1",
        "--skip-server-warmup",
        "--log-level",
        "info",
        "--random-seed",
        "666360643",
    ]
    for stale in RUN.glob("forward.*.logits"):
        stale.unlink()
    log = (RUN / "server.log").open("w")
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    results = []
    try:
        for _ in range(360):
            if proc.poll() is not None:
                raise RuntimeError(
                    f"server exited {proc.returncode}; inspect {RUN / 'server.log'}"
                )
            try:
                if requests.get(f"http://127.0.0.1:{PORT}/health", timeout=2).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise TimeoutError("server readiness timeout")

        tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
        cases = json.loads(FIXTURE.read_text())
        assert len(cases) == 12
        # Interleave policies on the same loaded process and fixed prompt. Three
        # independent requests per condition; one at a time, no shared prefix.
        sequence = []
        for key in sorted(cases):
            for repeat in range(3):
                sequence += [(key, "off", repeat), (key, "on", repeat)]
        for key, policy, repeat in sequence:
            case = cases[key]
            ids = [tok.bos_token_id] + tok.encode(
                case["prompt"], add_special_tokens=False
            )
            body = {
                "prompt": ids,
                "model": "gemma4",
                "max_tokens": 512,
                "temperature": 0.0,
                "top_p": 1.0,
                "seed": 1234,
                "ignore_eos": True,
                "skip_special_tokens": False,
                "stop": (
                    ["</s>", "<|im_end|>"]
                    if policy == "off"
                    else ["Question:", "</s>", "<|im_end|>"]
                ),
                "echo": False,
                "return_logprob": False,
                "logprobs": None,
                "return_token_ids": True,
                "no_stop_trim": True,
            }
            rid_local = f"{key.replace(':', '-')}-{policy}-r{repeat}"
            body["rid"] = rid_local
            response = requests.post(
                f"http://127.0.0.1:{PORT}/v1/completions", json=body, timeout=600
            )
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            output_ids = choice.get("token_ids") or []
            prompt_ids_returned = choice.get("prompt_token_ids") or []
            text = choice.get("text", "")
            completion_text = text
            results.append(
                {
                    "case": key,
                    "arm": "bf16",
                    "doc_id": int(key),
                    "policy": policy,
                    "repeat": repeat,
                    "request_id": data.get("id"),
                    "rid": rid_local,
                    "prompt_ids": ids,
                    "prompt_sha256": hashlib.sha256(
                        json.dumps(ids, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "prompt_ids_echo": prompt_ids_returned,
                    "prompt_ids_echo_match": prompt_ids_returned == ids,
                    "stop": body["stop"],
                    "finish_reason": choice.get("finish_reason"),
                    "matched_stop": choice.get("matched_stop"),
                    "output_ids": output_ids,
                    "output_token_logprobs": [],
                    "text": completion_text,
                    "text_from_output_ids": tok.decode(
                        output_ids, skip_special_tokens=False
                    ),
                    "completion_tokens": data.get("usage", {}).get("completion_tokens"),
                    "batch_size": 1,
                    "sampler": {"temperature": 0.0, "top_p": 1.0, "seed": 1234},
                }
            )
            print(
                key,
                policy,
                repeat,
                "tokens",
                len(output_ids),
                "finish",
                choice.get("finish_reason"),
                "match",
                choice.get("matched_stop"),
                flush=True,
            )
        (RUN / "replays.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n"
        )
        (RUN / "replay-manifest.json").write_text(
            json.dumps(
                {
                    "checkpoint": IDENTITY,
                    "request_count": len(results),
                    "repeats_per_policy": 3,
                    "policy_order": "per-case interleaved OFF then ON",
                    "batch_size": 1,
                    "device": torch.cuda.get_device_name(),
                    "torch": torch.__version__,
                    "server_cmd": cmd,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=45)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.close()
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        time.sleep(3)
        (RUN / "gpu-final.csv").write_text(
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used",
                    "--format=csv,noheader",
                ],
                text=True,
            )
        )
        lock.close()


if __name__ == "__main__":
    main()
