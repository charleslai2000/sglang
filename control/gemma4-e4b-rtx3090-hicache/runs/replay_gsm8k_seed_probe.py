#!/usr/bin/env python3
"""Probe historical server-seed difference on representative fixed GSM8K prompts."""

import fcntl, json, os, signal, subprocess, time
from pathlib import Path
import requests
from transformers import AutoTokenizer

ROOT = Path("/home/ubuntu/workspaces/3rdparty/sglang-hicache")
DATA = Path("/data/sglang-hicache/gemma4")
V = Path("/home/ubuntu/venvs/sglang-3090")
BASE = DATA / "runs/20261026T-gsm8k-stop-onoff-rerun"
OUT = BASE / "seed-probe"
MODEL = DATA / "model"
PORT = 31226
LOCK = "/tmp/f1-r16b-gpu-exclusive.lock"
IDENTITY = {
    "model_revision": "6cd26aaa2357fb2bad8c51699a7558a4d1a965bb",
    "model_sha256": "19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = open(LOCK, "a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = os.environ.copy()
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONPATH=f"{ROOT}/control/gemma4-e4b-rtx3090-hicache/runs:{ROOT}/python:{DATA}/aot-sm86-build:{ROOT}/3rdparty/sglang/python/sglang/kernels/aot/python",
        LD_LIBRARY_PATH=f"{V}/lib/python3.12/site-packages/torch/lib:/usr/local/cuda-12.9/lib64",
        GEMMA4_MODEL_IDENTITY=json.dumps(IDENTITY),
    )
    cases = json.load(open(BASE / "cases.json"))
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    records = []
    for seed in (991613486, 666360643):
        env["SGLANG_GEMMA4_CAPTURE_LOGITS"] = "1"
        env["SGLANG_GEMMA4_LOGITS_FILE"] = str(OUT / f"seed-{seed}-forward")
        cmd = [
            str(V / "bin/python"),
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
            str(seed),
        ]
        log = (OUT / f"server-{seed}.log").open("w")
        p = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            for _ in range(360):
                if p.poll() is not None:
                    raise RuntimeError(f"server exited {p.returncode}")
                try:
                    if requests.get(f"http://127.0.0.1:{PORT}/health", timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(2)
            else:
                raise TimeoutError("server readiness")
            for case in ("8", "18", "20"):
                ids = [tok.bos_token_id] + tok.encode(
                    cases[case]["prompt"], add_special_tokens=False
                )
                for pol in ("off", "on"):
                    for rep in range(3):
                        rid = f"seed-{seed}-{case}-{pol}-r{rep}"
                        body = {
                            "prompt": ids,
                            "model": "gemma4",
                            "max_tokens": 512,
                            "temperature": 0.0,
                            "top_p": 1.0,
                            "seed": 1234,
                            "ignore_eos": True,
                            "skip_special_tokens": False,
                            "stop": ["</s>", "<|im_end|>"]
                            if pol == "off"
                            else ["Question:", "</s>", "<|im_end|>"],
                            "return_token_ids": True,
                            "no_stop_trim": True,
                            "rid": rid,
                        }
                        res = requests.post(
                            f"http://127.0.0.1:{PORT}/v1/completions",
                            json=body,
                            timeout=600,
                        )
                        res.raise_for_status()
                        data = res.json()
                        c = data["choices"][0]
                        records.append(
                            {
                                "server_seed": seed,
                                "case": case,
                                "policy": pol,
                                "repeat": rep,
                                "rid": rid,
                                "request_id": data["id"],
                                "prompt_ids": ids,
                                "prompt_echo": c.get("prompt_token_ids"),
                                "output_ids": c.get("token_ids"),
                                "text": c.get("text"),
                                "finish_reason": c.get("finish_reason"),
                                "matched_stop": c.get("matched_stop"),
                            }
                        )
                        print(
                            seed,
                            case,
                            pol,
                            rep,
                            len(c.get("token_ids") or []),
                            c.get("matched_stop"),
                            flush=True,
                        )
        finally:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=45)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            log.close()
            time.sleep(2)
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    (OUT / "records.json").write_text(json.dumps(records, indent=2) + "\n")
    (OUT / "gpu-final.csv").write_text(
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
