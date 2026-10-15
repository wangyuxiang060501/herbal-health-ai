# -*- coding: utf-8 -*-
"""6.1.4 性能测试：并发问诊 + 接口响应时间

做法：**起真实 uvicorn 进程**再用 HTTP 并发打，而不是用 TestClient 在进程内跑。
理由是要把 uvicorn 的调度、SQLite 的连接竞争、GIL 争用都算进去，
否则测出来的数字没有参考价值。

LLM 的影响单独说明：
  默认 `LLM_PROVIDER=mock`（离线、确定性），测的是**系统自身的处理开销**；
  真实 LLM 的耗时是叠加项，用 `--provider ollama` 可再跑一遍做对比。

用法：
    python scripts/bench_api.py
    python scripts/bench_api.py --concurrency 32 --requests 200
    python scripts/bench_api.py --markdown docs/性能测试报告.md
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

QUESTIONS = {
    "阳虚质_1": 5, "阳虚质_2": 5, "阳虚质_3": 5,
    "气虚质_1": 4, "气虚质_2": 3, "气虚质_3": 3,
    "阴虚质_1": 1, "阴虚质_2": 1, "阴虚质_3": 1,
    "痰湿质_1": 1, "痰湿质_2": 1, "痰湿质_3": 1,
    "湿热质_1": 1, "湿热质_2": 1, "湿热质_3": 1,
    "血瘀质_1": 1, "血瘀质_2": 1, "血瘀质_3": 1,
    "气郁质_1": 1, "气郁质_2": 1, "气郁质_3": 1,
    "特禀质_1": 1, "特禀质_2": 1, "特禀质_3": 1,
    "平和质_1": 3, "平和质_2": 3, "平和质_3": 3,
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(url: str, timeout: float = 60.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    return False


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = int(round((len(sorted_vals) - 1) * p))
    return sorted_vals[k]


def fmt(vals: list[float]) -> str:
    if not vals:
        return "—"
    s = sorted(vals)
    return (f"p50={pct(s, .5):.0f}ms  p95={pct(s, .95):.0f}ms  "
            f"max={s[-1]:.0f}ms  mean={statistics.mean(s):.0f}ms")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--provider", default="mock")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--markdown", default="")
    args = ap.parse_args()

    try:
        import httpx
    except ImportError:  # pragma: no cover
        print("[FAIL] 需要 httpx：pip install httpx")
        return 1

    port = args.port or free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LLM_PROVIDER": args.provider,
           "LLM_FALLBACK_CHAIN": args.provider, "PORT": str(port)}

    print(f"[启动] uvicorn on {base}  provider={args.provider}")
    # 注意：stdout 必须落到文件而不是 PIPE。
    # 应用每个请求都会打 JSON 日志，管道缓冲（约 64KB）一旦写满且无人读取，
    # 服务进程会阻塞在写日志上 —— 表现是客户端莫名 ReadTimeout，极易误判成性能问题。
    log_path = Path(tempfile.gettempdir()) / f"bench_uvicorn_{port}.log"
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=str(BACKEND_ROOT), env=env,
        stdout=log_file, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not wait_ready(f"{base}/health"):
            log_file.flush()
            print(f"[FAIL] 服务未就绪，日志见 {log_path}")
            print((log_path.read_text(encoding="utf-8", errors="replace"))[:2000])
            return 1

        results: dict[str, dict] = {}

        # ---- 1) 单接口串行延迟 ----
        print("\n=== 单接口响应时间（串行 30 次）===")
        with httpx.Client(base_url=base, timeout=60) as cl:
            serial_cases = [
                ("GET  /health", lambda: cl.get("/health")),
                ("GET  /api/v1/meta/dataset", lambda: cl.get("/api/v1/meta/dataset")),
                ("GET  /api/v1/herbs?size=20", lambda: cl.get("/api/v1/herbs?size=20")),
                ("GET  /api/v1/herbs/search", lambda: cl.get("/api/v1/herbs/search?q=黄芪")),
                ("GET  /api/v1/rag/search", lambda: cl.get("/api/v1/rag/search?q=怕冷")),
                ("POST /api/v1/safety/probe-herbs",
                 lambda: cl.post("/api/v1/safety/probe-herbs",
                                 json={"herb_names": ["黄芪", "山药", "附子"]})),
                ("POST /api/v1/consultation/start",
                 lambda: cl.post("/api/v1/consultation/start",
                                 json={"chief_complaint": "怕冷手脚冰凉",
                                       "questionnaire": QUESTIONS})),
            ]
            for name, fn in serial_cases:
                vals = []
                for _ in range(30):
                    t0 = time.perf_counter()
                    r = fn()
                    vals.append((time.perf_counter() - t0) * 1000)
                    if r.status_code >= 500:
                        print(f"  !! {name} 返回 {r.status_code}")
                        break
                results[name] = {"p50": pct(sorted(vals), .5),
                                 "p95": pct(sorted(vals), .95),
                                 "max": max(vals), "mean": statistics.mean(vals)}
                print(f"  {name:<36} {fmt(vals)}")

        # ---- 2) 并发问诊 ----
        print(f"\n=== 并发问诊（{args.requests} 请求 / 并发 {args.concurrency}）===")
        payload = {"chief_complaint": "冬天怕冷手脚冰凉，容易累",
                   "questionnaire": QUESTIONS}
        lats: list[float] = []
        codes: dict[int, int] = {}
        errs: list[str] = []

        def one():
            t0 = time.perf_counter()
            try:
                with httpx.Client(base_url=base, timeout=120) as cl:
                    r = cl.post("/api/v1/consultation/start", json=payload)
                return (time.perf_counter() - t0) * 1000, r.status_code, ""
            except Exception as e:  # noqa: BLE001
                return (time.perf_counter() - t0) * 1000, 0, str(e)[:120]

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            for lat, code, err in pool.map(lambda _: one(), range(args.requests)):
                lats.append(lat)
                codes[code] = codes.get(code, 0) + 1
                if err:
                    errs.append(err)
        wall = time.perf_counter() - t_start

        ok = sum(v for k, v in codes.items() if 200 <= k < 300)
        print(f"  完成 {len(lats)} 个请求，耗时 {wall:.1f}s")
        print(f"  吞吐 {len(lats) / wall:.1f} req/s   成功率 {ok}/{len(lats)}")
        print(f"  状态码分布 {codes}")
        print(f"  延迟 {fmt(lats)}")
        if errs:
            print(f"  错误样例 {errs[:3]}")

        conc = {
            "requests": args.requests, "concurrency": args.concurrency,
            "wall_s": round(wall, 2), "throughput_rps": round(len(lats) / wall, 2),
            "success": ok, "p50": pct(sorted(lats), .5),
            "p95": pct(sorted(lats), .95), "max": max(lats),
            "mean": statistics.mean(lats), "codes": codes,
        }

        # ---- 3) 结论 ----
        print("\n=== 结论 ===")
        biz = results.get("POST /api/v1/consultation/start", {})
        print(f"  1. 含完整编排的问诊接口：p50={biz.get('p50', 0):.0f}ms "
              f"p95={biz.get('p95', 0):.0f}ms（provider={args.provider}，"
              f"{'含本地 LLM' if args.provider != 'mock' else '不含 LLM 网络/推理耗时'}）")
        print(f"  2. 并发 {args.concurrency} 下成功率 {ok}/{len(lats)}，"
              f"吞吐 {len(lats) / wall:.1f} req/s")
        bottleneck = ("SQLite 写锁" if codes.get(500, 0) else "未见明显瓶颈")
        print(f"  3. 瓶颈判断：{bottleneck}")

        if args.markdown:
            out = Path(args.markdown)
            if not out.is_absolute():
                out = BACKEND_ROOT.parent / out
            out.parent.mkdir(parents=True, exist_ok=True)
            md = [
                "# 性能测试报告（6.1.4）", "",
                f"- 方式：起真实 uvicorn 进程，HTTP 并发压测（非进程内 TestClient）",
                f"- LLM：`{args.provider}`"
                + ("（离线确定性，不含 LLM 推理耗时）" if args.provider == "mock"
                   else "（含本地模型推理耗时）"),
                f"- 机器：Windows / Python {sys.version.split()[0]}", "",
                "## 单接口响应时间（串行 30 次）", "",
                "| 接口 | p50 | p95 | max | 均值 |", "| --- | --- | --- | --- | --- |",
            ]
            for k, v in results.items():
                md.append(f"| `{k}` | {v['p50']:.0f}ms | {v['p95']:.0f}ms | "
                          f"{v['max']:.0f}ms | {v['mean']:.0f}ms |")
            md += [
                "", f"## 并发问诊（{args.requests} 请求 / 并发 {args.concurrency}）", "",
                "| 指标 | 值 |", "| --- | --- |",
                f"| 总耗时 | {wall:.1f}s |",
                f"| 吞吐 | {len(lats) / wall:.1f} req/s |",
                f"| 成功率 | {ok}/{len(lats)} |",
                f"| p50 / p95 / max | {conc['p50']:.0f} / {conc['p95']:.0f} / {conc['max']:.0f} ms |",
                f"| 状态码分布 | {json.dumps(codes, ensure_ascii=False)} |",
                "", "## 结论", "",
                f"1. 问诊接口 p50={biz.get('p50', 0):.0f}ms、p95={biz.get('p95', 0):.0f}ms。",
                f"2. 并发 {args.concurrency} 下成功率 {ok}/{len(lats)}，吞吐 {len(lats) / wall:.1f} req/s。",
                f"3. 瓶颈判断：{bottleneck}。",
            ]
            out.write_text("\n".join(md), encoding="utf-8")
            print(f"\n[OK] Markdown 已导出：{out}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()
        log_file.close()
        print(f"\n[INFO] 服务端日志：{log_path}")


if __name__ == "__main__":
    sys.exit(main())
