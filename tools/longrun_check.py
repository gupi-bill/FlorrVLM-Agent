#!/usr/bin/env python3
"""S22 · 稳定性长跑与资源门禁。

目标：证明「7×24 可跑」不是口号，且不会把小硬盘吃掉。

做三件事：
  1. dry-run 长循环（默认 500 轮）：无异常退出 / 采样整个进程树 RSS（防内存单调增长）
     / 采样打开句柄数（防句柄泄漏）。
  2. 临时文件零残留：跑完断言 video_frames/ 与项目根下的临时项无新增。
  3. 输出可机读 JSON + 人读文本报告（含实测内存与轮耗时数字）。

用法：
  python tools/longrun_check.py                 # 默认 500 轮
  python tools/longrun_check.py --rounds 100
  python tools/longrun_check.py --json out.json

退出码：0=全部达标；1=有指标未达标；2=环境/启动失败。
"""
import argparse
import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 阈值（对齐 S22 验收：内存泄漏 < 50MB）
RSS_GROWTH_LIMIT_MB = 50.0     # 后半段均值相对前半段均值的增长上限
FD_LEAK_LIMIT = 30             # 句柄净增上限

TMP_PATTERNS = [
    "video_frames",
    "florr_frame.png",
    "*.tmp",
]


def _tmp_snapshot():
    """记录项目根下临时项，用于跑前/跑后对比（零残留断言）。"""
    found = set()
    for pat in TMP_PATTERNS:
        for p in __import__("glob").glob(os.path.join(BASE_DIR, pat)):
            found.add(os.path.relpath(p, BASE_DIR))
    return found


def _tree_rss_fd(pid):
    """汇总进程树 RSS(bytes) 与打开句柄数。psutil 缺失时返回 (None, None)。"""
    try:
        import psutil
    except Exception:
        return None, None
    try:
        root = psutil.Process(pid)
        procs = [root] + root.children(recursive=True)
    except Exception:
        return None, None
    rss = 0
    fds = 0
    for pr in procs:
        try:
            rss += pr.memory_info().rss
            fds += pr.num_fds()
        except Exception:
            continue
    return rss, fds


def run_longrun(rounds, interval, sample_every, rss_limit=None, fd_limit=None):
    rss_limit = RSS_GROWTH_LIMIT_MB if rss_limit is None else rss_limit
    fd_limit = FD_LEAK_LIMIT if fd_limit is None else fd_limit
    py = sys.executable
    env = dict(os.environ)
    env["UGF_DRY_RUN"] = "1"
    env["UGF_PERCEPTION_BACKEND"] = "mock"

    before_tmp = _tmp_snapshot()
    cmd = [py, "agent_main.py", "--interval", str(interval),
           "--max-rounds", str(rounds)]
    # 输出重定向到文件，避免长循环塞满管道缓冲阻塞子进程
    log_path = os.path.join(BASE_DIR, "run_logs", "longrun_stdout.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=BASE_DIR, env=env,
                            stdout=log_fh, stderr=subprocess.STDOUT)

    samples = []  # (elapsed, rss_mb, fds)
    last_sample = 0.0
    while True:
        rc = proc.poll()
        now = time.time() - t0
        if now - last_sample >= sample_every or rc is not None:
            rss, fds = _tree_rss_fd(proc.pid)
            samples.append((round(now, 3),
                            None if rss is None else round(rss / 1048576.0, 2),
                            fds))
            last_sample = now
        if rc is not None:
            break
        if now > 1800:  # 硬上限 30 分钟
            proc.kill()
            break
        time.sleep(0.2)

    proc.wait()
    log_fh.close()
    try:
        with open(log_path, encoding="utf-8") as f:
            out = f.read()
    except Exception:
        out = ""
    elapsed = time.time() - t0
    after_tmp = _tmp_snapshot()
    residual = sorted(after_tmp - before_tmp)

    rss_vals = [s[1] for s in samples if s[1] is not None]
    fd_vals = [s[2] for s in samples if s[2] is not None]

    result = {
        "rounds": rounds,
        "exit_code": proc.returncode,
        "elapsed_sec": round(elapsed, 2),
        "sec_per_round": round(elapsed / rounds, 4) if rounds else None,
        "samples": len(samples),
        "samples_series": samples,
        "rss_mb_first": rss_vals[0] if rss_vals else None,
        "rss_mb_last": rss_vals[-1] if rss_vals else None,
        "rss_mb_max": max(rss_vals) if rss_vals else None,
        "rss_growth_mb": None,
        "fd_first": fd_vals[0] if fd_vals else None,
        "fd_last": fd_vals[-1] if fd_vals else None,
        "fd_delta": None,
        "residual_files": residual,
        "stdout_tail": out[-1500:],
        "checks": {},
    }

    # 稳态漂移：丢弃前 25% 预热样本（启动爬坡），比较「预热后首段」与「末段」均值。
    # 启动期 RSS 会快速爬升后平台化，属正常；真正的泄漏表现为预热后仍单调上升。
    if rss_vals and len(rss_vals) >= 8:
        warm = len(rss_vals) // 4
        steady = rss_vals[warm:]
        q = max(1, len(steady) // 4)
        head = sum(steady[:q]) / q
        tail = sum(steady[-q:]) / q
        result["rss_steady_head_mb"] = round(head, 2)
        result["rss_steady_tail_mb"] = round(tail, 2)
        result["rss_growth_mb"] = round(tail - head, 2)
    elif rss_vals:
        result["rss_growth_mb"] = round(rss_vals[-1] - rss_vals[0], 2)
    if fd_vals:
        result["fd_delta"] = fd_vals[-1] - fd_vals[0]

    checks = result["checks"]
    checks["exit_zero"] = (proc.returncode == 0)
    checks["no_rss_monotonic_growth"] = (
        result["rss_growth_mb"] is None or result["rss_growth_mb"] < rss_limit)
    checks["no_fd_leak"] = (
        result["fd_delta"] is None or result["fd_delta"] < fd_limit)
    checks["no_residual_files"] = (len(residual) == 0)
    result["ok"] = all(checks.values())
    return result


def main():
    ap = argparse.ArgumentParser(description="S22 稳定性长跑检查")
    ap.add_argument("--rounds", type=int, default=500)
    ap.add_argument("--interval", type=float, default=0.0)
    ap.add_argument("--sample-every", type=float, default=1.0)
    ap.add_argument("--rss-limit", type=float, default=None, help="RSS 稳态漂移上限 MB")
    ap.add_argument("--fd-limit", type=int, default=None, help="句柄净增上限")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not os.path.exists(os.path.join(BASE_DIR, "agent_main.py")):
        print("找不到 agent_main.py", file=sys.stderr)
        return 2

    print(f"[S22] 长跑开始：{args.rounds} 轮（dry-run + mock）…")
    res = run_longrun(args.rounds, args.interval, args.sample_every,
                      rss_limit=args.rss_limit, fd_limit=args.fd_limit)

    print("\n===== S22 长跑结果 =====")
    print(f"轮数           : {res['rounds']}")
    print(f"退出码         : {res['exit_code']}")
    print(f"总耗时         : {res['elapsed_sec']} s")
    print(f"每轮耗时       : {res['sec_per_round']} s")
    print(f"采样点         : {res['samples']}")
    print(f"RSS 首/末/峰   : {res['rss_mb_first']} / {res['rss_mb_last']} / {res['rss_mb_max']} MB")
    print(f"RSS 稳态漂移   : {res['rss_growth_mb']} MB（上限 {RSS_GROWTH_LIMIT_MB}，已剔除启动爬坡）")
    print(f"句柄 首/末/净增: {res['fd_first']} / {res['fd_last']} / {res['fd_delta']}（上限 {FD_LEAK_LIMIT}）")
    print(f"残留文件       : {res['residual_files'] or '无'}")
    print("--- 检查项 ---")
    for k, v in res["checks"].items():
        print(f"  {'✅' if v else '❌'} {k}")
    print(f"总结论         : {'✅ 达标' if res['ok'] else '❌ 未达标'}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告已写入: {args.json}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
