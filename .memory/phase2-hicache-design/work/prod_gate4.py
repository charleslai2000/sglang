#!/usr/bin/env python3
"""prod_gate4.py -- Drive real L3 extent pressure -> storage_hit on 22151.

Strategy: write several large sessions (each ~30K tokens) whose cumulative
history exceeds the host L2 budget (98305 tokens), forcing older sessions'
pages to be written through to the L3 extent. Then restore an old session:
its history should be served as storage_hit (L3 restore).

Requires: engine running on SGLANG_PORT (default 8024).
"""
import json, os, sys, time, urllib.request

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

def metrics():
    try:
        with urllib.request.urlopen(f"{BASE}/metrics", timeout=20) as r:
            text = r.read().decode()
    except Exception as e:
        return {}, str(e)
    out = {}
    for line in text.splitlines():
        if line.startswith("sglang:") and ("prefill_effective_tokens_total" in line
                                           or "realtime_tokens_total" in line):
            try:
                head, val = line.rsplit(" ", 1)
                val = float(val)
                mode = head.split('mode="')[1].split('"')[0]
                key = "prefill_" + mode if "prefill_effective" in head else "realtime_" + mode
                out[key] = val
            except Exception:
                pass
    return out, None

def chat(prompt, session, max_new=8, max_time=580):
    payload = {"model": "qwen3.5-9b-gptq",
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_new, "temperature": 0, "stream": False,
               "session_id": session}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{BASE}/v1/chat/completions", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=max_time) as r:
            body = json.loads(r.read().decode())
            u = body.get("usage", {})
            return {"ok": True, "http": r.status, "wall": time.time() - t0,
                    "prompt_tokens": u.get("prompt_tokens"),
                    "completion_tokens": u.get("completion_tokens")}
    except Exception as e:
        return {"ok": False, "err": str(e), "wall": time.time() - t0}

def main():
    nwrite = int(os.environ.get("GW4_WRITE", "8"))   # sessions to write
    reps = int(os.environ.get("GW4_REPS", "184"))    # corpus reps ~30K tokens
    # DISTINCT per-session content: each session gets a unique opening marker
    # so the token sequences do NOT share prefixes -> independent history
    # pressure (each session fills device+host, older ones spill to L3 extent).
    base = " ".join([_CORPUS] * reps)
    m0, err = metrics()
    if err:
        print("metrics fetch failed:", err); sys.exit(1)
    print(f"writing {nwrite} DISTINCT sessions x ~{reps*164} tokens each (cumulative target > device 65536 + host 98305 = ~164K)")
    wrote = []
    for i in range(nwrite):
        sess = f"prod-g4-w{i}"
        # unique opener per session -> distinct token stream
        big = f"【会话{i}专用起始标记-{i*7919}】\n" + base
        r = chat(big, sess, max_new=8)
        wrote.append((sess, r))
        print(f"  write[{i}] {sess} -> ok={r.get('ok')} prompt={r.get('prompt_tokens')} wall={r.get('wall'):.1f}s")
        if not r.get("ok"):
            print("  WRITE FAILED:", r)
    # now restore the OLDEST session (w0) -> its history should now be in L3
    print("\nrestoring oldest session prod-g4-w0")
    rr = chat(f"【会话0专用起始标记-0】\n" + base + "\n请只回复：完成。", "prod-g4-w0", max_new=16)
    print("restore req:", rr)
    m1, _ = metrics()
    for k in ("prefill_storage_hit", "prefill_host_hit", "prefill_device_hit", "prefill_input"):
        print(f"  {k}: {m0.get(k,0):.0f} -> {m1.get(k,0):.0f}  delta={m1.get(k,0)-m0.get(k,0):.0f}")
    d_sto = m1.get("prefill_storage_hit", 0) - m0.get("prefill_storage_hit", 0)
    d_host = m1.get("prefill_host_hit", 0) - m0.get("prefill_host_hit", 0)
    d_dev = m1.get("prefill_device_hit", 0) - m0.get("prefill_device_hit", 0)
    ok = rr.get("ok") and d_sto > 0
    print(f"\nGATE4: {'PASS' if ok else 'FAIL'} (storage_hit delta={d_sto:.0f}, host={d_host:.0f}, device={d_dev:.0f})")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
