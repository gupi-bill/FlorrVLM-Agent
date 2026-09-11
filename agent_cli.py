#!/usr/bin/env python3
"""
FlorrVLM-Agent 交互式入口 agent_cli.py
=======================================
v0.6 —— 从"后台脚本"变成"能对话、能汇报、能编排"的 Agent。
v1.0 —— 界面美化 + 开玩前"了解游戏"问答流程(brief)。

生命周期：
  detect(这是什么游戏) → research(去查) → ensure(确认能玩) → play(玩) → report(汇报)
开玩前适应项：play 前若还没做过"游戏了解(brief)"，会先问你几个问题，
再把答案归档，之后 research/ensure 才知道要重点关注什么。

命令：help 查看全部；quit 退出。会话状态持久化到 agent_state.json。
"""
import argparse
import asyncio
import json
import os
import sys

import config
import session  # v1.4 会话记忆 & 断点续玩
from cli_ui import banner, panel, chip, bold, cyan, green, magenta, dim, yellow, red
from report_notifier import notify  # v1.2 自动汇报
from skill_manager import SkillManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "agent_state.json")

SKILLS = SkillManager()                       # v0.8
ACTIVE_GAME = os.getenv("AGENT_GAME", "florr")  # v0.9 由游戏档案读取

# v1.0 开玩前"了解游戏"问答
BRIEF_QUESTIONS = [
    ("game_type", "这是什么类型/玩法？(如: 网页对战、RPG、卡牌、策略)"),
    ("focus", "这一局你最看重什么？(保命优先 / 刷分升级 / 打Boss / 组队配合)"),
    ("watch_out", "有什么规则或坑要特别注意？(没有可直接回车)"),
]


# ---------------------------------------------------------------------------
# 会话状态（持久化）
# ---------------------------------------------------------------------------
def _default_state() -> dict:
    return {
        "game": ACTIVE_GAME,
        "status": "idle",            # idle / researching / ensure / playing / done / error
        "last_played": None,
        "last_rounds": 0,
        "last_report": "",
        "brief": None,               # v1.0 开玩前的游戏了解答案 {key: 回答}
        "started_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }


def load_state() -> dict:
    """读取会话状态；不存在或损坏返回默认，并补齐新字段。"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        d = _default_state()
        d.update(st)
        return d
    except Exception:
        return _default_state()


def save_state(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[状态] 保存失败: {e}")


# ---------------------------------------------------------------------------
# 开玩前了解（v1.0 适应项）
# ---------------------------------------------------------------------------
def _collect_brief(answers: dict = None) -> dict:
    """
    交互式问你几个问题，返回 {key: 回答} 存档。
    answers 为空时逐条提问；已存在时补问缺的。
    关键：只在真正终端里提问；被管道调用时用环境变量/已有答案兜底。
    """
    brief = dict(answers or {})
    for key, prompt in BRIEF_QUESTIONS:
        if key in brief and brief[key]:
            continue
        try:
            val = input(dim(f"  ? {prompt} ") + green("> ")).strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        brief[key] = val
    return brief


def _format_brief(brief: dict) -> str:
    if not brief:
        return chip("尚未做过游戏了解(brief)，输入 brief 可查看，play 前会自动引导一次", "info")
    return "\n".join(
        f"  {green(bold(k)):<26} {v or '(未填写)'}" for k, v in brief.items()
    )


# ---------------------------------------------------------------------------
# 能力清单 / 组件
# ---------------------------------------------------------------------------
def _configured_connectors() -> list:
    try:
        import yaml
        with open(os.path.join(BASE_DIR, "mcp_connectors.yaml"), "r",
                  encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [str(c.get("name")) for c in data.get("connectors", []) if c.get("name")]
    except Exception:
        return []


def _inspected_components() -> list:
    parts = [f"游戏档案: {ACTIVE_GAME}"]
    parts.append("MCP Server(对外提供工具): mcp_server.py")
    ext = _configured_connectors()
    parts.append(f"外部 MCP(可主动连接): {', '.join(ext) if ext else '暂无(见 mcp_connectors.yaml)'}")
    return parts


def describe_capabilities() -> str:
    lines = [
        "生命周期(命令):",
        "  detect   —— 确认/切换当前游戏",
        "  brief    —— 开玩前了解游戏(问答)",
        "  research —— 按 brief 去查该游戏资料",
        "  ensure   —— 确认能力足够再开玩",
        "  play     —— 进入游戏主循环(自动打/跑/追/复盘)",
        "  report   —— 汇报进度与最近战况",
        "",
        "其他: capabilities / state / skills / load / unload / run_skill / help / quit",
    ]
    lines = [f"  {x}" for x in lines]
    lines.append("")
    lines += [f"  · {x}" for x in _inspected_components()]
    return panel("FlorrVLM-Agent 能力清单(可随时输入 capabilities 查看)", lines)


HELP_LINES = [
    ("detect <游戏>", "确认/切换游戏(默认 florr)"),
    ("brief",        "开玩前了解游戏，问答后存档"),
    ("reset_brief",  "重新做一次问答"),
    ("research <词>", "去查该游戏资料(依赖外部 MCP/Skill)"),
    ("ensure",       "确认能否开玩"),
    ("play [回合]",   "进入主循环(0=无限；未了解过会先引导问答)"),
    ("report",       "汇报进度/战况"),
    ("notify",       "生成并推送一份报告(本地文件/Webhook)"),
    ("session",      "查看会话记忆(场次/回合/死亡/技能，v1.4)"),
    ("resume",       "查看待续玩的上次进度"),
    ("stats",        "多局战绩汇总与最近战绩(v1.5)"),
    ("validate <游戏>", "游戏档案自检(投bo前用，v1.8)"),
    ("skills",       "列出可用 Skill"),
    ("load/unload/run_skill", "加载/卸载/运行 Skill"),
    ("auto [游戏]",   "全链路自动：detect→brief→research→ensure→play"),
    ("quit/exit/q",  "退出"),
]


# ---------------------------------------------------------------------------
# 各命令动作
# ---------------------------------------------------------------------------
def _cmd_detect(game: str) -> str:
    st = load_state()
    st["game"] = game.strip().lower() or ACTIVE_GAME
    st["status"] = "idle"
    save_state(st)
    return chip(f"当前游戏已设为: {bold(st['game'])}", "ok")


def _cmd_brief() -> str:
    st = load_state()
    brief = _collect_brief(st.get("brief"))
    st["brief"] = brief
    st["status"] = "researching"
    save_state(st)
    return panel("游戏了解(brief)——已归档", _format_brief(brief))


def _cmd_research(query: str = None) -> str:
    st = load_state()
    if not query:
        focus = (st.get("brief") or {}).get("focus", "")
        query = focus or f"{st['game']} 玩法重点"
    st["status"] = "researching"
    save_state(st)
    try:
        from mcp_connector import ExternalConnector

        async def _q():
            ec = await ExternalConnector.create()
            try:
                tools = ec.tool_catalog()
                if not tools:
                    return (chip(f"未连接外部 MCP，无法联网查询「{query}」。", "warn") + "\n"
                            + dim("  提示: 先在 mcp_connectors.yaml 配置外部 MCP 即可联网查资料"))
                return panel(f"已连接外部工具（“{query}”由 LLM 决策层调用对应工具查询）",
                             [f"· {t}" for t in tools])
            finally:
                await ec.close()

        return asyncio.run(_q())
    except Exception as e:
        return chip(f"research 不可用: {e}", "err")


def _cmd_ensure() -> str:
    st = load_state()
    es = os.path.exists(os.path.join(BASE_DIR, "perception_server.py"))
    ms = os.path.exists(os.path.join(BASE_DIR, "mcp_server.py"))
    brief_ok = bool(st.get("brief"))
    ok = es and ms
    lines = [f"感知服务: {'✓ 存在' if es else '✗ 缺失'}",
             f"MCP Server: {'✓ 存在' if ms else '✗ 缺失'}",
             f"游戏了解(brief): {'✓ 已完成' if brief_ok else '⚠ 未做(play 前会自动引导)'}"]
    st["status"] = "done" if ok else "idle"
    save_state(st)
    lines.append("可执行: play 进入主循环" if ok else "先补全缺失组件再 ensure")
    return panel("开玩前检查(ensure)", lines)


def _cmd_play(max_rounds: int = 0) -> str:
    st = load_state()
    # v1.0 适应项：play 前必须做过 brief
    if not st.get("brief"):
        st["brief"] = _collect_brief(st.get("brief"))
        st["status"] = "researching"
        save_state(st)
        print(panel("检测到还没了解该游戏，已先引导你回答下列问题", _format_brief(st["brief"])))
    try:
        import agent_main
    except ImportError as e:
        st["status"] = "error"; save_state(st)
        return chip(f"无法导入 agent_main: {e}", "err")
    # v1.4 断点续玩：开玩前记下"从哪续"，检测到上次进度就提示并汇报续玩
    skills = SKILLS.loaded()
    if session.record_start(st["game"], skills):
        info = session.resume_info()
        if info:
            print(panel("断点续玩（会话记忆）", [info]))
        session.mark_resumed()
    st["status"] = "playing"
    st["last_played"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    save_state(st)
    asyncio.run(agent_main.run_agent(max_rounds=max_rounds))
    # v1.4 结束后：真实回合/死亡取自主监控快照，并累加场次/技能
    rounds, deaths = session.snapshot_rounds_deaths()
    if max_rounds and rounds < max_rounds:
        rounds = max_rounds  # 自定义轮回合以用户设定为准
    st = load_state(); st["status"] = "done"; save_state(st)
    # v1.2 每局结束自动汇报
    try:
        acts = notify()
        session.record_end(st["game"], rounds, deaths, skills, report="\n".join(acts))
        return chip("游戏主循环已结束", "ok") + "\n" + "\n".join(dim(a) for a in acts)
    except Exception as e:
        session.record_end(st["game"], rounds, deaths, skills, report=f"汇报失败: {e}")
        return chip(f"游戏主循环已结束（自动汇报失败: {e}）", "ok")


def _cmd_notify() -> str:
    """v1.2 手动触发一次报告。"""
    try:
        acts = notify()
        return "\n".join(acts)
    except Exception as e:
        return chip(f"汇报失败: {e}", "err")


def _cmd_report() -> str:
    st = load_state()
    lines = [f"当前游戏: {green(bold(st['game']))}",
             f"状态: {yellow(st['status'])}",
             f"上次游玩: {st['last_played'] or '从未'}",
             f"上次回合数: {st['last_rounds']}",
             "",
             "游戏了解(brief):"]
    lines += list(_format_brief(st.get("brief")).split("\n"))
    today = __import__("datetime").datetime.now().strftime("%Y%m%d")
    log_dir = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
    cand = os.path.join(log_dir, f"agent_{today}.log")
    if os.path.exists(cand):
        try:
            with open(cand, "r", encoding="utf-8") as f:
                tail = f.read().splitlines()[-15:]
            lines.append("最近日志(尾部):")
            lines += [dim("  " + x) for x in tail]
        except OSError:
            lines.append("日志读取失败")
    else:
        lines.append("暂无运行日志")
    return panel("汇报(report)", lines)


def _cmd_validate(game: str) -> str:
    """v1.8 游戏档案自检。"""
    try:
        import game_profile_check
        name = (game or "").strip() or None
        if name is None:
            name = ACTIVE_GAME
        ok, problems = game_profile_check.check_one(name)
        lines = [f"[{'✅' if ok else '❌'}] 档案自检: {name}"] + \
                [f"  - {p}" for p in problems]
        lines.append("  ✓ 档案完整，可以 play" if ok
                     else "  ✗ 请先修复或用 tools/add_game.py 重新登记")
        return "\n".join(lines)
    except Exception as e:
        return chip(f"自检不可用: {e}", "err")


def _run_auto(game: str) -> str:
    """全链路自动：detect → brief(若无) → research → ensure。"""
    st = load_state()
    parts = [_cmd_detect(game)]
    if not st.get("brief"):
        st["brief"] = _collect_brief(st.get("brief"))
        st["status"] = "researching"
        save_state(st)
        parts.append(panel("已按引导完成游戏了解(brief)", _format_brief(st["brief"])))
    parts.append(_cmd_research())
    parts.append(_cmd_ensure())
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 交互主循环
# ---------------------------------------------------------------------------
def _prompt_text() -> str:
    st = load_state()
    flag = cyan("●") if st.get("brief") else yellow("○")  # 是否已了解游戏
    return f"[{cyan(st['game'])}]{flag}> "


def interactive():
    import readline  # 终端方向键/历史（仅 Linux/macOS）
    print(banner())
    print(cyan("命令提示: 输入 help 查看全部命令；回答要换游戏前先 detect。"))
    print()
    # 首次进入在交互前展示能力清单
    print(describe_capabilities())
    print(panel("可用命令", [f"  {green(bold(c)):<22} {d}" for c, d in HELP_LINES]))
    while True:
        try:
            raw = input(_prompt_text()).strip()
        except (EOFError, KeyboardInterrupt):
            print(dim("\n再见 👋"))
            break
        if not raw:
            continue
        cmd, _, arg = raw.partition(" ")
        arg = arg.strip()

        if cmd in ("quit", "exit", "q"):
            print(dim("再见 👋"))
            break
        elif cmd in ("help", "h", "?"):
            print(panel("可用命令", [f"  {green(bold(c)):<22} {d}" for c, d in HELP_LINES]))
        elif cmd == "capabilities":
            print(describe_capabilities())
        elif cmd == "state":
            print(json.dumps(load_state(), ensure_ascii=False, indent=2))
        elif cmd == "detect":
            print(_cmd_detect(arg or "florr"))
        elif cmd == "brief":
            print(_cmd_brief())
        elif cmd == "reset_brief":
            st = load_state(); st["brief"] = _collect_brief(None); save_state(st)
            print(panel("已重新了解(brief)", _format_brief(st["brief"])))
        elif cmd == "research":
            print(_cmd_research(arg))
        elif cmd == "ensure":
            print(_cmd_ensure())
        elif cmd == "play":
            print(_cmd_play(int(arg) if arg.isdigit() else 0))
        elif cmd == "report":
            print(_cmd_report())
        elif cmd == "notify":
            print(_cmd_notify())
        elif cmd == "session":
            print(panel("会话记忆(session)", session.describe().split("\n")))
        elif cmd == "resume":
            info = session.resume_info()
            print(panel("上次进度(可续玩)", [info]) if info else chip("无待续玩进度", "info"))
        elif cmd == "stats":
            print(panel("多局战绩统计(stats)", session.stats_text().split("\n")))
        elif cmd == "validate":
            print(_cmd_validate(arg))
        elif cmd == "skills":
            print(SKILLS.summary())
        elif cmd == "load":
            print(SKILLS.load(arg))
        elif cmd == "unload":
            print(SKILLS.unload(arg))
        elif cmd == "run_skill":
            print(SKILLS.call(arg))
        elif cmd == "auto":
            print(_run_auto(arg or "florr"))
            print(_cmd_play(0))
        else:
            print(red(f"未知命令: {cmd}（输入 help 查看）"))
        # 循环内不做事件，交给用户


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 交互式入口")
    parser.add_argument("-c", "--command", help="执行单条命令后退出(如 report / skills)")
    args = parser.parse_args()

    if args.command:
        cmd, _, arg = args.command.partition(" ")
        arg = arg.strip()
        fns = {
            "capabilities": lambda: describe_capabilities(),
            "state": lambda: json.dumps(load_state(), ensure_ascii=False, indent=2),
            "detect": lambda: _cmd_detect(arg or "florr"),
            "brief": lambda: _cmd_brief(),
            "reset_brief": lambda: (s := load_state(), s.update(brief=_collect_brief(None)), save_state(s)) and _format_brief(s["brief"]),
            "research": lambda: _cmd_research(arg),
            "ensure": lambda: _cmd_ensure(),
            "report": lambda: _cmd_report(),
            "notify": lambda: _cmd_notify(),
            "session": lambda: session.describe(),
            "resume": lambda: session.resume_info() or "无待续玩进度",
            "stats": lambda: session.stats_text(),
            "validate": lambda: _cmd_validate(arg),
            "skills": lambda: SKILLS.summary(),
            "load": lambda: SKILLS.load(arg),
            "unload": lambda: SKILLS.unload(arg),
            "run_skill": lambda: SKILLS.call(arg),
        }
        fn = fns.get(cmd)
        print(fn() if fn else f"未知命令: {cmd}")
        return

    try:
        interactive()
    except KeyboardInterrupt:
        print(dim("\n再见 👋"))


if __name__ == "__main__":
    main()