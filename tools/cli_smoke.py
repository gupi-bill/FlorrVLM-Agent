#!/usr/bin/env python3
"""
S8 · CLI 全命令冒烟工具（tools/cli_smoke.py）

用途：
  以子进程方式批量执行 `agent_cli.py -c "<cmd>"`，生成「命令 × 结果」矩阵，
  用于验证：
    1. 每个子命令在离线/无头环境下都能执行完毕；
    2. 失败时给出的是**可读的错误提示**，而不是 traceback；
    3. 命令清单与 `help` / `describe_capabilities` 的声明一致（无孤儿命令、无漏登记命令）。

设计要点：
  - 全程子进程真实调用，不走 monkeypatch，能抓到 import 期与运行期的真实崩溃。
  - 每条命令带超时，避免 research/play 等潜在阻塞命令拖死整轮。
  - 判定"可读错误"：stderr 出现 `Traceback (most recent call last)` 即为不可读。
  - 支持 `--json` 输出机器可读结果，`--strict` 在有 traceback 时退出码非 0（S13 门禁用）。

用法：
  python tools/cli_smoke.py                # 跑默认矩阵，打印表格
  python tools/cli_smoke.py --json         # 输出 JSON
  python tools/cli_smoke.py --strict       # 有 traceback 则 exit 1
  python tools/cli_smoke.py --only kb_list kb_search
"""
import argparse
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
CLI = os.path.join(BASE_DIR, "agent_cli.py")

# 离线/无头环境下统一的环境变量：
#   UGF_DRY_RUN=1                     —— 主循环不做真实键鼠、不调外部 LLM
#   UGF_PERCEPTION_BACKEND=mock       —— 感知走合成数据，不探截图工具
#   PYTHONIOENCODING=utf-8            —— 避免中文输出在部分 locale 下报错
ENV_BASE = {
    **os.environ,
    "UGF_DRY_RUN": "1",
    "UGF_PERCEPTION_BACKEND": "mock",
    "PYTHONIOENCODING": "utf-8",
}

# 默认冒烟矩阵：(命令, 超时秒)
# 说明：play / auto 会拉起主循环，用 --rounds 限制；package 走 portable 不产生大产物。
DEFAULT_MATRIX = [
    ("help", 20),
    ("capabilities", 20),
    ("state", 20),
    ("detect florr", 20),
    ("brief", 20),
    ("research", 30),
    ("ensure", 20),
    ("validate florr", 20),
    ("validate space_invaders", 20),
    ("kb_list", 20),
    ("kb_list florr", 20),
    ("kb_write smoke_s8.md", 20),
    ("kb_append smoke_s8.md", 20),
    ("kb_search boss", 20),
    ("kb_search boss florr", 20),
    ("stats", 20),
    ("report", 20),
    ("notify", 30),
    ("session", 20),
    ("resume", 20),
    ("skills", 20),
    ("load report", 20),
    ("run_skill report", 20),
    ("unload report", 20),
    ("package portable", 60),
    ("kb_export", 40),
    ("auto florr", 90),
    ("play 2", 150),
    ("--auto florr", 90),                      # ui_pyqt 修订后的调用形状
    ("--auto search florr basic guide", 90),   # ui_pyqt.py 历史调用形状
    ("bogus_cmd_xyz", 20),   # 反向用例：未知命令必须给可读提示而非 traceback
]

# 预期失败的命令（反向用例）：不计入"有意义输出"统计
EXPECT_FAIL = {"bogus_cmd_xyz"}


def run_one(cmd: str, timeout: int = 30) -> dict:
    """执行单条 CLI 命令并返回结构化结果。"""
    # `--auto ...` 这类是 argparse 原生参数，不能包在 -c 里
    argv = [PY, CLI] + cmd.split() if cmd.startswith("--") else [PY, CLI, "-c", cmd]
    try:
        p = subprocess.run(
            argv, cwd=BASE_DIR, env=ENV_BASE,
            # stdin 必须隔离：若父进程把 tty 透传进来，任何 input() 都会永久阻塞。
            # 这正是 S8 发现 `-c brief` 超时 / `-c "play 2"` 卡死的根因。
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=timeout,
        )
        out, err, rc = p.stdout or "", p.stderr or "", p.returncode
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "ok": False, "rc": None, "timeout": True,
                "stdout": "", "stderr": f"TIMEOUT after {timeout}s",
                "traceback": False, "meaningful": False, "expected": False}
    tb = "Traceback (most recent call last)" in err or "Traceback (most recent call last)" in out
    body = (out or "").strip()
    expected_fail = cmd in EXPECT_FAIL
    # "有意义" = 有实际输出、无 traceback，且不是"未知命令"这类空壳回复
    meaningful = (bool(body) and not tb
                  and not body.startswith("未知命令")
                  and (rc == 0 or expected_fail))
    return {
        "cmd": cmd, "ok": (rc == 0 or expected_fail) and not tb,
        "rc": rc, "timeout": False, "expected_fail": expected_fail,
        "stdout": body[:400], "stderr": (err or "").strip()[:400],
        "traceback": tb, "meaningful": meaningful,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UGF CLI 全命令冒烟")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非表格")
    ap.add_argument("--strict", action="store_true", help="存在 traceback 时退出码 1")
    ap.add_argument("--only", nargs="*", default=None, help="只跑指定命令（前缀匹配）")
    ap.add_argument("--timeout", type=int, default=30, help="默认超时秒")
    args = ap.parse_args(argv)

    matrix = DEFAULT_MATRIX
    if args.only:
        matrix = [m for m in DEFAULT_MATRIX
                  if any(o in m[0] for o in args.only)] or [(o, args.timeout) for o in args.only]

    results = [run_one(cmd, timeout) for cmd, timeout in matrix]
    n_tb = sum(1 for r in results if r["traceback"])
    n_ok = sum(1 for r in results if r["ok"])
    n_mean = sum(1 for r in results if r["meaningful"])

    if args.json:
        print(json.dumps({"total": len(results), "ok": n_ok, "traceback": n_tb,
                          "meaningful": n_mean, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print(f"{'命令':<26} {'rc':>3} {'结果':<8} {'traceback':<10} 摘要")
        print("-" * 100)
        for r in results:
            flag = "TIMEOUT" if r["timeout"] else ("OK" if r["ok"] else "FAIL")
            summary = (r["stdout"] or r["stderr"]).replace("\n", " ")[:52]
            print(f"{r['cmd']:<26} {str(r['rc']):>3} {flag:<8} {str(r['traceback']):<10} {summary}")
        total = len(results)
        print("-" * 100)
        print(f"合计 {total} 条：ok {n_ok} / 有意义输出 {n_mean} "
              f"({n_mean * 100 // max(total, 1)}%) / traceback {n_tb}")
    return 1 if (args.strict and n_tb) else 0


if __name__ == "__main__":
    sys.exit(main())
