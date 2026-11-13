#!/usr/bin/env python3
"""Replay frozen GSM8K prompts under isolated and loaded scheduler conditions."""

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
DATA = Path("/data/sglang-hicache/gemma4")
VENV = Path("/home/ubuntu/venvs/sglang-3090")
RUN = DATA / "runs/20261026T-gsm8k-stop-onoff-rerun"
FIXTURE = RUN / "fixture-128.json"
OUT = RUN / "controlled"
MODEL = DATA / "model"
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"
IDENTITY = {
    "model_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
    "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
}
STOP_SETS = {
    "off": ["</s>", "<|im_end|>"],
    "on": ["Question:", "</s>", "<|im_end|>"],
}


def main():
    lock = open(LOCK, "a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONPATH=(
            f"{ROOT}/control/gemma4-e4b-rtx3090-hicache/runs:{ROOT}/python:"
            f"{DATA}/aot-sm86-build:"
            f"{ROOT}/3rdparty/sglang/python/sglang/kernels/aot/python"
        ),
        LD_LIBRARY_PATH=(
            f"{VENV}/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64"
        ),
        GEMMA4_MODEL_IDENTITY=json.dumps(IDENTITY),
        SGLANG_GEMMA4_CAPTURE_DECODE_LOGITS="1",
        SGLANG_GEMMA4_DECODE_LOGITS_FILE=str(OUT / "decode"),
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
        "31228",
        "--context-length",
        "8192",
        "--max-running-requests",
        "16",
        "--mem-fraction-static",
        ".94",
        "--disable-radix-cache",
        "--kv-cache-dtype",
        "bf16",
        "--attention-backend",
        "triton",
        "--cuda-graph-max-bs-decode",
        "16",
        "--skip-server-warmup",
        "--log-level",
        "info",
        "--random-seed",
        "666360643",
    ]
    log = (OUT / "server.log").open("w")
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        for _ in range(360):
            if process.poll() is not None:
                raise RuntimeError(f"server exited {process.returncode}")
            try:
                if requests.get("http://127.0.0.1:31228/health", timeout=2).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise TimeoutError("server readiness")

        fixture = json.loads(FIXTURE.read_text())
        results = []
        # C1 is strictly serial; batch16 waves create scheduler-visible overlap.
        for condition in ("c1", "batch16"):
            for policy, stops in STOP_SETS.items():
                items = list(fixture.items())
                groups = (
                    [[item] for item in items]
                    if condition == "c1"
                    else [items[i : i + 16] for i in range(0, len(items), 16)]
                )
                for group in groups:
                    payloads = []
                    for doc_id, item in group:
                        payloads.append(
                            {
                                "prompt": item["input_ids"],
                                "model": "gemma4",
                                "max_tokens": 512,
                                "temperature": 0.0,
                                "top_p": 1.0,
                                "seed": 1234,
                                "ignore_eos": True,
                                "skip_special_tokens": False,
                                "stop": stops,
                                "return_token_ids": True,
                                "no_stop_trim": True,
                                "rid": f"{condition}-{policy}-{doc_id}",
                            }
                        )
                    if len(payloads) == 1:
                        response = requests.post(
                            "http://127.0.0.1:31228/v1/completions",
                            json=payloads[0],
                            timeout=900,
                        )
                        response.raise_for_status()
                        outputs = [response.json()]
                    else:
                        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
                            futures = [
                                pool.submit(
                                    requests.post,
                                    "http://127.0.0.1:31228/v1/completions",
                                    json=payload,
                                    timeout=900,
                                )
                                for payload in payloads
                            ]
                            outputs = []
                            for future in futures:
                                response = future.result()
                                response.raise_for_status()
                                outputs.append(response.json())
                    for payload, output in zip(payloads, outputs):
                        choice = output["choices"][0]
                        echoed = choice.get("prompt_token_ids") or []
                        if echoed and echoed != payload["prompt"]:
                            raise AssertionError(
                                f"prompt echo mismatch {payload['rid']}"
                            )
                        row = {
                            "rid": payload["rid"],
                            "doc_id": payload["rid"].rsplit("-", 1)[-1],
                            "condition": condition,
                            "policy": policy,
                            "prompt_ids": payload["prompt"],
                            "prompt_sha256": hashlib.sha256(
                                json.dumps(
                                    payload["prompt"], separators=(",", ":")
                                ).encode()
                            ).hexdigest(),
                            "prompt_echo_match": echoed == payload["prompt"],
                            "output_ids": choice.get("token_ids") or [],
                            "text": choice.get("text"),
                            "finish_reason": choice.get("finish_reason"),
                            "matched_stop": choice.get("matched_stop"),
                            "completion_tokens": output.get("usage", {}).get(
                                "completion_tokens"
                            ),
                            "request_id": output.get("id"),
                            "batch_requested": len(payloads),
                        }
                        results.append(row)
                        with (OUT / "requests.jsonl").open("a") as stream:
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        (OUT / "results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n"
        )
        (OUT / "manifest.json").write_text(
            json.dumps(
                {
                    "checkpoint": IDENTITY,
                    "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                    "requests": len(results),
                    "conditions": ["c1", "batch16"],
                    "policies": STOP_SETS,
                    "decode_capture": True,
                    "server_cmd": cmd,
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        lock.close()


if __name__ == "__main__":
    main()
