#!/usr/bin/env python3
"""
Universal-Game-Framework 接入流程一键化  tools/onboard_game.py  (v2.0 / S17)
============================================================================
把「接入一款新游戏」从几小时的读源码 + 猜字段，压成一条命令：

    python tools/onboard_game.py demo_arcade

它会依次跑完五个环节，任一环节失败即中止（后面的环节标记为 skipped）：

    1. 生成   add_game  —— 没有档案就按 `_template.yaml` 渲染一份并落盘
    2. 校验   validate  —— game_profile_check 语义自检（strict：建议项也算问题）
    3. 冒烟   smoke     —— perception_server --selftest --backend mock，证明感知层离线可用
    4. 试跑   dry-run   —— agent_main --rounds N 真实子进程跑完 N 轮（无键鼠 / 无 LLM）
    5. 报告   report    —— 写 devplan/onboard_<game>.md

设计约束（本机硬条件：无显卡 / 无密钥 / 无 X server / 磁盘紧张）：
  - 冒烟与试跑**必须走 mock + dry-run 降级分支**，不假设真机可用；
  - 试跑用子进程而非 import，能抓到 import 期崩溃与跨进程环境丢失（S15 教训：
    `AGENT_GAME` 不透传给子进程会导致「父进程按 A 决策、子进程按 B 出数据」）；
  - 报告目录可注入（测试指到 tmp_path，不污染仓库）。

用法:
  python tools/onboard_game.py <game>                 # 默认 2 轮试跑，生成并激活
  python tools/onboard_game.py <game> --rounds 3      # 试跑 3 轮
  python tools/onboard_game.py <game> --no-activate   # 不改 config.yaml（推荐用于演示游戏）
  python tools/onboard_game.py <game> --no-dry-run    # 跳过最耗时的试跑（秒级，只做静态验证）
  python tools/onboard_game.py <game> --no-smoke
  python tools/onboard_game.py <game> --lenient       # validate 允许 WARN
  python tools/onboard_game.py <game> --json          # 机器可读结果（CI 用）
  python tools/onboard_game.py <game> --report-dir DIR

退出码：0 = 全部通过；1 = 有环节失败；2 = 参数错误。
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import yaml  # noqa: E402

from tools import add_game  # noqa: E402
import game_profile_check as gpc  # noqa: E402

DEFAULT_REPORT_DIR = os.path.join(BASE_DIR, "devplan")
# 试跑默认轮数：2 轮足以证明「感知→决策→执行→复盘→回写」全链路打通，
# 又不至于让一键接入耗时超过 30 秒（S8 实测 2 轮约 14 秒）。
DEFAULT_ROUNDS = 2
# 单个子进程环节的硬超时（秒）。超过即判失败，避免一键流程被挂死进程拖住。
STEP_TIMEOUT = 240


# ---------------------------------------------------------------------------
# 环节实现
# ---------------------------------------------------------------------------
def _profile_path(name: str) -> str:
    return os.path.join(add_game.PROFILE_DIR, f"{name}.yaml")


def _step(title: str, fn):
    """统一计时 + 异常兜底：任何环节抛异常都不让整条流水线崩掉。"""
    t0 = time.time()
    try:
        ok, detail, issues, extra = fn()
    except Exception as exc:                       # noqa: BLE001 - 流水线要能容错
        return {"key": "", "title": title, "ok": False, "skipped": False,
                "detail": f"环节异常: {type(exc).__name__}: {exc}",
                "issues": [f"{title} 抛出未捕获异常: {exc}"],
                "seconds": round(time.time() - t0, 2)}
    return {"key": "", "title": title, "ok": bool(ok), "skipped": False,
            "detail": detail, "issues": list(issues or []),
            "seconds": round(time.time() - t0, 2), **(extra or {})}


def step_generate(name: str, activate: bool = True):
    """环节 1：没有档案就生成；已有则复用（onboard 必须可重复执行）。

    注意：**生成环节绝不切默认游戏**。实测教训 —— 先切后验时，一旦档案校验
    不通过，`config.yaml` 已被指向一个坏游戏，下一次任何命令都会读到脏配置。
    切换动作推迟到校验通过之后（由 `onboard()` 里的 `_maybe_activate` 执行）。
    """
    path = _profile_path(name)

    def run():
        if os.path.exists(path):
            return True, f"档案已存在，直接复用: {path}", [], {"generated": False}
        os.environ["UGF_NONINTERACTIVE"] = "1"
        data = add_game.collect(name)
        text = add_game.render_yaml(data)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        note = "；待校验通过后再切默认游戏" if activate else "；--no-activate 保持原默认"
        return (True, f"已生成: {path}{note}", [], {"generated": True})
    result = _step("生成档案", run)
    result["key"] = "generate"
    return result


def step_validate(name: str, strict: bool = True):
    """环节 2：语义自检。ERROR 一律阻断；WARN 在 strict 下也算问题。"""

    def run():
        detail = gpc.check_detail(name)
        errors = list(detail.get("errors", []))
        warnings = list(detail.get("warnings", []))
        issues = [f"[错误] {e}" for e in errors]
        if strict:
            issues += [f"[建议] {w}" for w in warnings]
        ok = not errors and (not strict or not warnings)
        summary = (f"ERROR {len(errors)} / WARN {len(warnings)}"
                   f"（口径: {'strict' if strict else 'lenient'}）")
        return ok, summary, issues, {"errors": errors, "warnings": warnings}
    result = _step("档案校验", run)
    result["key"] = "validate"
    return result


def _run_subprocess(script, args, game, extra_env=None, timeout=STEP_TIMEOUT):
    env = {**os.environ, "AGENT_GAME": game, "UGF_GAME": game,
           "UGF_PERCEPTION_BACKEND": "mock", "UGF_DRY_RUN": "1"}
    env.update(extra_env or {})
    return subprocess.run([sys.executable, os.path.join(BASE_DIR, script), *args],
                          cwd=BASE_DIR, capture_output=True, text=True,
                          timeout=timeout, env=env)


def step_smoke(name: str, rounds: int = 2):
    """环节 3：mock 感知冒烟（无显卡 / 无 YOLO 也要能出场景）。"""

    def run():
        proc = _run_subprocess("perception_server.py",
                               ["--selftest", "--backend", "mock",
                                "--rounds", str(max(1, rounds))], name)
        out = (proc.stdout or "") + (proc.stderr or "")
        issues = []
        if proc.returncode != 0:
            issues.append(f"perception_server 自检退出码 {proc.returncode}")
        if "Traceback" in out:
            issues.append("感知自检输出含 Traceback")
        ents = len(re.findall(r'"raw_id"', out))
        if ents == 0:
            issues.append("自检输出中没有任何实体（mock 场景为空）")
        detail = f"自检 {rounds} 帧，输出实体条目 {ents} 个，退出码 {proc.returncode}"
        return not issues, detail, issues, {"entities": ents,
                                            "tail": out[-400:]}
    result = _step("感知冒烟", run)
    result["key"] = "smoke"
    return result


def step_dryrun(name: str, rounds: int = DEFAULT_ROUNDS):
    """环节 4：真实子进程跑 N 轮 —— 这是「通用性」唯一的实证方式。"""

    def run():
        proc = _run_subprocess("agent_main.py",
                               ["--rounds", str(max(1, rounds))], name,
                               timeout=STEP_TIMEOUT)
        out = (proc.stdout or "") + (proc.stderr or "")
        issues = []
        if proc.returncode != 0:
            issues.append(f"agent_main 退出码 {proc.returncode}")
        if "Traceback" in out:
            issues.append("主循环输出含 Traceback")
        if not re.search(r"回合\s*%d" % max(1, rounds), out):
            issues.append(f"输出中未见「回合 {max(1, rounds)}」，主循环可能提前退出")
        kb_dir = os.path.join(BASE_DIR, "knowledge_md", name)
        kb_files = []
        if os.path.isdir(kb_dir):
            kb_files = sorted(os.listdir(kb_dir))
        if not kb_files:
            issues.append(f"未产生游戏知识库分区: {kb_dir}")
        detail = f"试跑 {rounds} 轮，退出码 {proc.returncode}，知识库文件 {len(kb_files)} 个"
        return not issues, detail, issues, {"kb_files": kb_files,
                                            "tail": out[-600:]}
    result = _step("dry-run 试跑", run)
    result["key"] = "dryrun"
    return result


def step_report(result: dict, report_dir: str = None):
    """环节 5：写接入报告。"""

    def run():
        target_dir = report_dir or DEFAULT_REPORT_DIR
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"onboard_{result['game']}.md")
        text = render_report(result)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return True, f"已写出接入报告: {path}", [], {"path": path}
    result_step = _step("生成报告", run)
    result_step["key"] = "report"
    return result_step


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------
def render_report(result: dict) -> str:
    lines = []
    game = result["game"]
    verdict = "✅ 接入成功" if result["ok"] else "⛔ 接入未通过"
    lines.append(f"# 接入报告 · {game}")
    lines.append("")
    lines.append(f"> 由 `tools/onboard_game.py` 自动生成于 {result['finished_at']}"
                 f" ｜ 总耗时 {result['seconds']}s ｜ {verdict}")
    lines.append("")
    lines.append("## 一、结论")
    lines.append("")
    lines.append(f"- 接入环节通过：{result['passed']}/{result['total']}"
                 f"（跳过 {result['skipped']}，不含最后的报告环节）")
    lines.append(f"- 试跑轮数：{result.get('rounds', DEFAULT_ROUNDS)}"
                 f" ｜ 校验口径：{'strict（建议项也算问题）' if result.get('strict') else 'lenient'}")
    lines.append(f"- 档案：`game_profiles/{game}.yaml`"
                 f"（{'本次生成' if result.get('generated') else '已存在，复用'}）")
    lines.append(f"- 接入方式：全程未修改核心代码，仅新增/复用一份 YAML 档案")
    if result.get("activated"):
        lines.append(f"- 默认游戏切换：{result['activated']}")
    lines.append("")

    lines.append("## 二、环节明细")
    lines.append("")
    lines.append("| # | 环节 | 结果 | 耗时(s) | 说明 |")
    lines.append("|---|---|---|---|---|")
    for i, st in enumerate(result["steps"], 1):
        flag = "⏭ 跳过" if st["skipped"] else ("✅" if st["ok"] else "❌")
        lines.append(f"| {i} | {st['title']} | {flag} | {st['seconds']} | {st['detail']} |")
    lines.append("")

    prof = result.get("profile_summary") or {}
    if prof:
        lines.append("## 三、档案摘要")
        lines.append("")
        lines.append("| 字段 | 值 |")
        lines.append("|---|---|")
        for k, v in prof.items():
            lines.append(f"| `{k}` | {v} |")
        lines.append("")

    issues = result.get("issues") or []
    lines.append("## 四、发现的问题")
    lines.append("")
    if issues:
        for it in issues:
            lines.append(f"- {it}")
    else:
        lines.append("- 无。生成、校验、冒烟、试跑四个环节均未发现异常。")
    lines.append("")

    lines.append("## 五、后续建议")
    lines.append("")
    for tip in result.get("advice") or []:
        lines.append(f"- {tip}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("复现命令：")
    lines.append("")
    lines.append("```bash")
    lines.append(f"python tools/onboard_game.py {game} --rounds "
                 f"{result.get('rounds', DEFAULT_ROUNDS)}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _profile_summary(name: str) -> dict:
    path = _profile_path(name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:                              # noqa: BLE001
        return {}
    game = data.get("game", {}) or {}
    combat = data.get("combat", {}) or {}
    server = data.get("server", {}) or {}
    pred = data.get("predictor", {}) or {}
    perc = data.get("perception", {}) or {}
    mock = (perc.get("mock") or {})
    return {
        "game.name": game.get("name", ""),
        "game.description": game.get("description", ""),
        "server.perception_port": server.get("perception_port", ""),
        "combat.default_set": combat.get("default_set", ""),
        "combat.sets": ", ".join(combat.get("sets", []) or []),
        "combat.tactics": len(combat.get("tactics", []) or []),
        "predictor.threat.boss": (pred.get("threat") or {}).get("boss", ""),
        "perception.mock.entities": len(mock.get("entities", []) or []),
    }


def _advice(result: dict) -> list:
    tips = []
    st = {s["key"]: s for s in result["steps"]}
    if st.get("smoke", {}).get("skipped"):
        tips.append("本次跳过了感知冒烟；上真机前务必单独跑一次 "
                    "`python perception_server.py --selftest --backend mock`。")
    if st.get("dryrun", {}).get("skipped"):
        tips.append("本次跳过了 dry-run 试跑；建议补跑 `AGENT_GAME=<game> "
                    "UGF_DRY_RUN=1 python agent_main.py --rounds 2` 以证明全链路。")
    if not tips and result["ok"]:
        tips.append("链路已打通。下一步：在 mock 下多跑几轮观察决策分布，"
                    "确认无误后再切真实感知后端（YOLO/HTTP）上真机。")
        tips.append("若要把这款游戏设为默认，执行 `python tools/add_game.py "
                    f"{result['game']}` 或在 config.yaml 的 agent.game 手动切换。")
    tips.append("上真机前请先确认目标环境的合规性：仅在本地/自建/已授权环境运行自动化程序。")
    return tips


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def onboard(game_name: str, rounds: int = DEFAULT_ROUNDS, strict: bool = True,
            activate: bool = True, do_smoke: bool = True,
            do_dryrun: bool = True, report_dir: str = None) -> dict:
    """串起「生成 → 校验 → 冒烟 → 试跑 → 报告」，返回结构化结果。"""
    t0 = time.time()
    # 必须在 _sanitize_name **之前**校验原始输入：该函数会把 `_template` 洗成
    # `template`、把空串兜底成 `florr`（见 add_game._sanitize_name 的 `or "florr"`）。
    # 若先清洗再校验，`onboard "_template"` / `onboard ""` 会静默变成另一款游戏，
    # 这类「命令打错却跑出看似正常的结果」最难排查。
    raw = (game_name or "").strip()
    if not raw:
        raise ValueError("游戏名为空")
    if raw.startswith("_") or raw.startswith("."):
        raise ValueError(f"游戏名不能以 _ 或 . 开头（{raw} 被保留给模板/隐藏文件）")
    name = add_game._sanitize_name(raw)
    if not name:
        raise ValueError("游戏名为空")

    steps = []
    generate = step_generate(name, activate=activate)
    steps.append(generate)

    validate = step_validate(name, strict=strict)
    steps.append(validate)

    def _skipped_step(key, title, reason, failed=False):
        return {"key": key, "title": title, "ok": not failed, "skipped": True,
                "detail": reason, "issues": [], "seconds": 0.0}

    # 注意：冒烟与试跑是**真实子进程**，必须惰性执行。
    # 校验没过（档案都不合法，跑也无意义）或被参数关闭时，绝不能只是"标记跳过"
    # 却照跑不误 —— 那会让 --no-dry-run 退化成一个白等 14 秒的空开关。
    if not validate["ok"]:
        smoke = _skipped_step("smoke", "感知冒烟", "前置校验未通过，跳过", failed=True)
        dryrun = _skipped_step("dryrun", "dry-run 试跑", "前置校验未通过，跳过",
                               failed=True)
    else:
        smoke = (_skipped_step("smoke", "感知冒烟", "按参数跳过")
                 if not do_smoke else step_smoke(name, rounds=2))
        dryrun = (_skipped_step("dryrun", "dry-run 试跑", "按参数跳过")
                  if not do_dryrun else step_dryrun(name, rounds=rounds))
    steps.append(smoke)
    steps.append(dryrun)

    # 切换默认游戏：仅在「生成/校验都过了」之后才做（详见 step_generate 注释）
    activated = ""
    if activate and validate["ok"]:
        activated = add_game.activate_game(name)
    elif activate:
        steps[1]["issues"].append("校验未通过，已放弃切换 config.yaml 的默认游戏")
        activated = "校验未通过，未切换默认游戏"

    result = {
        "game": name,
        "rounds": rounds,
        "strict": strict,
        "generated": bool(generate.get("generated")),
        "steps": steps,
        "issues": [i for s in steps for i in s["issues"]],
        "profile_summary": _profile_summary(name),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
    }
    # 报告环节本身也要进明细表，但结果 dict 先补齐再渲染
    pre = dict(result)
    pre["ok"] = all(s["ok"] for s in steps if not s["skipped"])
    pre["total"] = len(steps)
    pre["passed"] = sum(1 for s in steps if s["ok"] and not s["skipped"])
    pre["skipped"] = sum(1 for s in steps if s["skipped"])
    pre["advice"] = _advice(pre)
    pre["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    pre["seconds"] = round(time.time() - t0, 2)

    report = step_report(pre, report_dir=report_dir)
    pre["steps"] = steps + [report]
    pre["total"] = len(pre["steps"])
    pre["passed"] = sum(1 for s in pre["steps"] if s["ok"] and not s["skipped"])
    pre["skipped"] = sum(1 for s in pre["steps"] if s["skipped"])
    pre["ok"] = all(s["ok"] for s in pre["steps"] if not s["skipped"])
    pre["report_path"] = report.get("path", "")
    return pre


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="UGF 接入流程一键化（S17）")
    ap.add_argument("game", help="游戏名（也是 game_profiles/<name>.yaml 的文件名）")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS,
                    help=f"dry-run 试跑轮数，默认 {DEFAULT_ROUNDS}")
    ap.add_argument("--no-activate", action="store_true", help="不改 config.yaml")
    ap.add_argument("--no-smoke", action="store_true", help="跳过感知冒烟")
    ap.add_argument("--no-dry-run", action="store_true", help="跳过 dry-run 试跑")
    ap.add_argument("--lenient", action="store_true", help="validate 允许 WARN")
    ap.add_argument("--report-dir", default=None, help="报告输出目录（默认 devplan/）")
    ap.add_argument("--json", action="store_true", help="输出机器可读结果")
    args = ap.parse_args(argv)

    # --json 要交给 CI 解析，而 add_game 的生成向导会往 stdout 打人话提示
    # （实测首行就是「【新增游戏档案】」），不拦住会让 json.loads 直接炸。
    sink = io.StringIO()
    ctx = contextlib.redirect_stdout(sink) if args.json else contextlib.nullcontext()
    try:
        with ctx:
            result = onboard(args.game, rounds=args.rounds,
                             strict=not args.lenient,
                             activate=not args.no_activate,
                             do_smoke=not args.no_smoke,
                             do_dryrun=not args.no_dry_run,
                             report_dir=args.report_dir)
    except ValueError as exc:
        print(f"参数错误: {exc}")
        return 2

    if args.json:
        slim = {k: v for k, v in result.items() if k != "steps"}
        slim["steps"] = [{k: v for k, v in s.items() if k != "tail"}
                         for s in result["steps"]]
        print(json.dumps(slim, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    print(f"\n=== 接入流程 · {result['game']} ===")
    for i, st in enumerate(result["steps"], 1):
        flag = "⏭" if st["skipped"] else ("✅" if st["ok"] else "❌")
        print(f"  {i}. {flag} {st['title']}（{st['seconds']}s）：{st['detail']}")
        for it in st["issues"]:
            print(f"       - {it}")
    print(f"\n  总耗时 {result['seconds']}s ｜ 通过 {result['passed']}/{result['total']}")
    print(f"  报告：{result.get('report_path','(未生成)')}")
    print("  " + ("✅ 接入成功" if result["ok"] else "⛔ 接入未通过") + "\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
