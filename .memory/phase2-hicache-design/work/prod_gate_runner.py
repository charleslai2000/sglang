#!/usr/bin/env python3
"""prod_gate_runner.py -- Run 5 hard gates against the deployed HiCache engine on 22151.

Focused gate validation matching the frozen baseline methodology:
  gate2: single request warm prefill succeeds
  gate3: same-session prefix hit -> device_hit (GPU L1) > 0
  gate4: cross/multi-session write + restore -> storage_hit (L3 extent) > 0
  gate5: c8 concurrency decode throughput ~= pool64+Graph ON+c8 baseline 596 tok/s

Metrics primitives (from /metrics):
  prefill_effective_tokens_total{mode=device_hit|host_hit|storage_hit|input}
  realtime_tokens_total{mode=prefill_compute|prefill_cache|decode}
"""
import json, os, subprocess, sys, time, urllib.request, threading

PORT = int(os.environ.get("SGLANG_PORT", "8024"))
BASE = f"http://127.0.0.1:{PORT}"

_CORPUS = (
    "大语言模型推理中的缓存系统分为三级：GPU 显存一级缓存、主机内存二级缓存与"
    "NVMe 固态硬盘三级缓存。一级缓存存放最近被访问的键值对与状态张量，访问速度最快"
    "但容量有限；当显存放不下时，旧的张量会被逐出到主机内存，仍然保留供后续请求复用；"
    "更久远的数据则会写入三级缓存，通过扩展文件后端按区块持久化。这套分级存储的目标是"
    "让长上下文的智能体在连续多轮对话中，只有新增内容需要真正计算，而历史内容全部命中缓存，"
    "从而大幅降低热会话下一轮的响应延迟。我们通过实验测量不同历史长度下，追加少量新内容时的"
    "首令牌延迟与整体端到端延迟，以验证三级缓存是否成功兜住了历史。"
)

def fetch(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as e:
        return None, str(e)

def metrics():
    code, text = fetch(f"{BASE}/metrics", timeout=15)
    if code != 200:
        return {}
    out = {}
    for line in text.splitlines():
        if line.startswith("#") or not line:
            continue
        if "prefill_effective_tokens_total" in line or "realtime_tokens_total" in line:
            if line.startswith("sglang:"):
                # parse {mode="..."} N
                try:
                    head, val = line.rsplit(" ", 1)
                    val = float(val)
                    mode = None
                    if 'mode="' in head:
                        mode = head.split('mode="')[1].split('"')[0]
                    if mode:
                        key = "prefill_" + mode if "prefill_effective" in head else "realtime_" + mode
                        out[key] = val
                except Exception:
                    pass
    return out

def chat(prompt, session=None, max_new=64, max_time=580):
    payload = {
        "model": "qwen3.5-9b-gptq",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_new,
        "temperature": 0,
        "stream": False,
    }
    if session:
        payload["session_id"] = session
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=max_time) as r:
            body = json.loads(r.read().decode())
            wall = time.time() - t0
            usage = body.get("usage", {})
            return {
                "ok": True, "http": r.status, "wall": wall,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "cached_tokens": usage.get("cached_tokens"),
                "finish": body.get("choices", [{}])[0].get("finish_reason"),
            }
    except Exception as e:
        return {"ok": False, "err": str(e), "wall": time.time() - t0}

def gate2():
    print("=== GATE2: warm prefill ===")
    m0 = metrics()
    r = chat("你好，请用一句话介绍你自己。", max_new=32)
    m1 = metrics()
    print(f"request: {r}")
    print(f"prefill input={m0.get('prefill_input',0)}->{m1.get('prefill_input',0)} "
          f"delta={m1.get('prefill_input',0)-m0.get('prefill_input',0)}")
    ok = r.get("ok") and r.get("completion_tokens", 0) > 0
    print(f"GATE2: {'PASS' if ok else 'FAIL'}\n")
    return ok, r

def gate3():
    print("=== GATE3: same-session prefix hit (GPU L1 device_hit) ===")
    session = "prod-gate3-%d" % int(time.time())
    # Build a long history in one session, then re-send same prefix + delta
    hist = " ".join([_CORPUS] * 6)  # ~ multi-K tokens
    m0 = metrics()
    r1 = chat(hist, session=session, max_new=16)
    # same session: resend the SAME long history + a short new user turn
    r2 = chat(hist + "\n请只回复：确认。", session=session, max_new=16)
    m1 = metrics()
    d_dev = m1.get("prefill_device_hit", 0) - m0.get("prefill_device_hit", 0)
    d_inp = m1.get("prefill_input", 0) - m0.get("prefill_input", 0)
    print(f"r1={r1}")
    print(f"r2={r2}")
    print(f"device_hit delta={d_dev:.0f}, input delta={d_inp:.0f}")
    ok = r2.get("ok") and r1.get("ok") and d_dev > 0
    print(f"GATE3: {'PASS' if ok else 'FAIL'} (device_hit>0={d_dev>0})\n")
    return ok, {"r1": r1, "r2": r2, "device_hit_delta": d_dev, "input_delta": d_inp}

def gate4():
    print("=== GATE4: storage_hit (L3 extent) ===")
    # Write several sessions with large histories, then restore one old session
    # to push past host L2 budget and force L3 extent restore.
    m0 = metrics()
    # write 4 sessions of large history
    for i in range(4):
        sess = f"prod-gate4-w{i}"
        chat(" ".join([_CORPUS]*8), session=sess, max_new=8)
    # restore one old session -> should hit storage
    r = chat(" ".join([_CORPUS]*8) + "\n请只回复：完成。", session="prod-gate4-w0", max_new=16)
    m1 = metrics()
    d_sto = m1.get("prefill_storage_hit", 0) - m0.get("prefill_storage_hit", 0)
    d_host = m1.get("prefill_host_hit", 0) - m0.get("prefill_host_hit", 0)
    d_dev = m1.get("prefill_device_hit", 0) - m0.get("prefill_device_hit", 0)
    print(f"restore req: {r}")
    print(f"storage_hit delta={d_sto:.0f}, host_hit delta={d_host:.0f}, device_hit delta={d_dev:.0f}")
    ok = r.get("ok") and d_sto > 0
    print(f"GATE4: {'PASS' if ok else 'FAIL'} (storage_hit>0={d_sto>0})\n")
    return ok, {"restore": r, "storage_hit_delta": d_sto, "host_hit_delta": d_host, "device_hit_delta": d_dev}

def gate5():
    print("=== GATE5: c8 decode throughput (baseline ~596 tok/s) ===")
    prompt = " ".join([_CORPUS]*2)
    results = [None]*8
    errors = [0]*8

    def worker(i):
        payload = {
            "model": "qwen3.5-9b-gptq",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256, "temperature": 0, "stream": False,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=580) as resp:
                body = json.loads(resp.read().decode())
                u = body.get("usage", {})
                results[i] = (u.get("completion_tokens", 0), time.time())
        except Exception as e:
            errors[i] = str(e)

    # measure steady-window decode tok/s from realtime_tokens_total{mode=decode}
    m0 = metrics()
    t0 = time.time()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    m1 = metrics()
    wall = time.time() - t0
    d_dec = m1.get("realtime_decode", 0) - m0.get("realtime_decode", 0)
    nerr = sum(1 for e in errors if e)
    comp = sum((r[0] for r in results if r), 0)
    tps = d_dec / wall if wall > 0 else 0
    print(f"wall={wall:.2f}s, decode_tokens_delta={d_dec:.0f}, aggregate_decode_tok_s={tps:.1f}")
    print(f"completion_tokens_sum={comp}, errors={nerr}")
    ok = tps >= 596*0.95 and tps <= 606*1.05 and nerr == 0
    print(f"GATE5: {'PASS' if ok else 'FAIL'} (target 596-606 tok/s, got {tps:.1f})\n")
    return ok, {"wall": wall, "decode_tokens_delta": d_dec, "agg_tok_s": tps, "errors": nerr, "completion_sum": comp}

def main():
    g2 = gate2()
    g3 = gate3()
    g4 = gate4()
    g5 = gate5()
    print("===== SUMMARY =====")
    print(f"gate2 warm prefill: {'PASS' if g2[0] else 'FAIL'}")
    print(f"gate3 device_hit:   {'PASS' if g3[0] else 'FAIL'}")
    print(f"gate4 storage_hit:  {'PASS' if g4[0] else 'FAIL'}")
    print(f"gate5 c8 tok/s:     {'PASS' if g5[0] else 'FAIL'}")
    allok = all([g2[0], g3[0], g4[0], g5[0]])
    print(f"ALL GATES (2-5): {'PASS' if allok else 'FAIL'}")
    return 0 if allok else 1

if __name__ == "__main__":
    sys.exit(main())
