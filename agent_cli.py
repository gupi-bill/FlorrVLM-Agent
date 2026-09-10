#!/usr/bin/env python3
"""
FlorrVLM-Agent 交互式入口 agent_cli.py
=======================================
v0.6 —— 让 Agent 从"后台脚本"变成"能对话、能汇报、能编排"的 Agent。

核心概念：
- 统一生命周期：detect(这是什么游戏) → research(去查) → ensure(确认能玩)
                 → play(执行) → report(汇报)
- 每个阶段是一个命令，既可由你对话触发，也可整条链路自动跑
- 会话状态持久化到 agent_state.json，重启不丢上下文
- describe_capabilities：随时问"你能做什么"

v0.7(v0.8) 之后：capabilities() 会自动追加"已连接的外部 MCP 工具"
和"已加载的 Skill"，让这份能力清单越来越满。
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

import config

from skill_manager import SkillManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "agent_state.json")

# 全局技能管理器（v0.8）
SKILLS = SkillManager()

# 当前激活的游戏（v0.9 之后改为从 game_profiles/ 读取）
ACTIVE_GAME = os.getenv("AGENT_GAME", "florr")


# ---------------------------------------------------------------------------
# 会话状态（持久化）
# ---------------------------------------------------------------------------
def _default_state() -> dict:
    return {
        "game": ACTIVE_GAME,
        "status": "idle",            # idle / researching / playing / done / error
        "last_played": None,         # 上次游玩时间
        "last_rounds": 0,            # 上次运行回合数
        "last_report": "",           # 上次汇报内容
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_state() -> dict:
    """读取会话状态；不存在或损坏则返回默认。"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
            # 补齐新字段
            d = _default_state()
            d.update(st)
            return d
    except Exception:
        return _default_state()


def save_state(state: dict):
    """写回会话状态。"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[状态] 保存失败: {e}")


# ---------------------------------------------------------------------------
# 能力清单
# ---------------------------------------------------------------------------
def _configured_connectors() -> list:
    """读取 mcp_connectors.yaml 里已配置的外部 MCP 名称（仅展示，不实际连接）。"""
    try:
        import yaml
        with open(os.path.join(BASE_DIR, "mcp_connectors.yaml"), "r",
                  encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [str(c.get("name")) for c in data.get("connectors", []) if c.get("name")]
    except Exception:
        return []


def _inspected_components() -> list:
    """检测当前已具备的组件。"""
    parts = [f"游戏档案: {ACTIVE_GAME}"]
    parts.append("MCP Server(对外提供工具): mcp_server.py")
    ext = _configured_connectors()
    if ext:
        parts.append(f"外部 MCP(可主动连接): {', '.join(ext)}")
    else:
        parts.append("外部 MCP(可主动连接): 暂无(见 mcp_connectors.yaml)")
    # v0.8：在此追加已加载的 Skill
    return parts


def describe_capabilities() -> str:
    """输出"我会干什么"，供对话或 LLM 随时查询。"""
    lines = [
        f"{'=' * 44}",
        "FlorrVLM-Agent 能力清单",
        f"{'=' * 44}",
        "生命周期阶段(可用命令):",
        "  detect   —— 确认/切换当前游戏",
        "  research —— 去查该游戏资料(依赖外部 MCP/Skill)",
        "  ensure   —— 确认能力足够再开玩",
        "  play     —— 进入游戏主循环(自动打/跑/追/复盘)",
        "  report   —— 汇报当前进度与最近战况",
        "其他命令: capabilities / state / help / quit",
        "",
        "已具备组件:",
    ]
    lines += [f"  - {x}" for x in _inspected_components()]
    lines.append("")
    lines.append(SKILLS.summary())
    lines.append("=" * 44)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 生命周期阶段对应动作
# ---------------------------------------------------------------------------
def _cmd_detect(game: str) -> str:
    """切换并确认当前游戏。"""
    st = load_state()
    st["game"] = game.strip().lower() or ACTIVE_GAME
    st["status"] = "idle"
    save_state(st)
    return f"[detect] 当前游戏已设为: {st['game']}"


def _cmd_research(query: str) -> str:
    """
    查资料。优先用已连接的外部 MCP 工具去查；没有可用的外部连接时，
    诚实占位：能借用本地视频学习时用之，否则明确告知。
    """
    st = load_state()
    if query:
        st["status"] = "researching"
        save_state(st)

    if not query:
        return "[research] 请给出要查的关键词，例如: research florr.io 最强花瓣套"
    # 1) 尝试通过外部 MCP 查询
    try:
        from mcp_connector import ExternalConnector

        async def _query():
            ec = await ExternalConnector.create()
            try:
                tools = ec.tool_catalog()
                if not tools:
                    return (f"未连接外部 MCP，无法联网查询「{query}」\n"
                             f"  (在 mcp_connectors.yaml 配置外部 MCP 后即可用)")
                return f"已连接外部工具: {', '.join(tools)}\n查询「{query}」请由 LLM 决策层调用对应工具。"
            finally:
                await ec.close()

        return asyncio.run(_query())
    except Exception as e:
        return f"[research] 外部 MCP 查询不可用: {e}"


def _cmd_ensure() -> str:
    """确认能力是否足够开玩。"""
    st = load_state()
    es = os.path.exists(os.path.join(BASE_DIR, "perception_server.py"))
    ms = os.path.exists(os.path.join(BASE_DIR, "mcp_server.py"))
    if es and ms:
        st["status"] = "done"
        save_state(st)
        return ("[ensure] 检测到 感知服务 与 MCP Server 均存在，具备开玩条件 ✓\n"
                "  可执行: play 进入游戏主循环（需先手动启动各服务，见 README）")
    return ("[ensure] 组件不完整：缺少 perception_server.py 或 mcp_server.py，"
            "无法开玩 ✗")


def _cmd_play(max_rounds: int = 0) -> str:
    """进入游戏主循环（复用 agent_main.run_agent）。"""
    try:
        import agent_main
    except ImportError as e:
        st = load_state(); st["status"] = "error"; save_state(st)
        return f"[play] 无法导入 agent_main: {e}"
    st = load_state()
    st["status"] = "playing"
    st["last_played"] = datetime.now().isoformat(timespec="seconds")
    save_state(st)
    # 复用主循环；Ctrl+C 后返回，再补齐批次信息
    asyncio.run(agent_main.run_agent(max_rounds=max_rounds))
    st = load_state()
    st["status"] = "done"
    save_state(st)
    return "[play] 游戏主循环已结束"


def _cmd_report() -> str:
    """汇报当前进度与最近战况。"""
    st = load_state()
    lines = [
        f"[report] 当前游戏: {st['game']}",
        f"  状态: {st['status']}",
        f"  上次游玩: {st['last_played'] or '从未'}",
        f"  上次回合数: {st['last_rounds']}",
    ]
    # 读当天日志尾部，作为战况摘要
    import glob
    today = datetime.now().strftime("%Y%m%d")
    log_dir = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
    cand = os.path.join(log_dir, f"agent_{today}.log")
    if os.path.exists(cand):
        try:
            with open(cand, "r", encoding="utf-8") as f:
                tail = f.read().splitlines()[-15:]
            lines.append("  最近日志(尾部):")
            lines += [f"    {x}" for x in tail]
        except OSError:
            lines.append("  日志读取失败")
    else:
        lines.append("  暂无运行日志")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 对话主循环
# ---------------------------------------------------------------------------
HELP_TEXT = """可用命令:
  detect <游戏名>     切换/确认当前游戏
  research <关键词>   去查游戏资料
  ensure              确认能否开玩
  play [回合数]       进入游戏主循环(0=无限)
  report              汇报当前进度与最近战况
  capabilities        查看能力清单
  state               查看会话状态
  skills              查看可用 Skill
  load <技能名>       加载一个 Skill
  unload <技能名>     卸载一个 Skill
  run_skill <技能名>  运行一个已加载的 Skill
  auto                自动跑完整条链路: detect→research→ensure→play
  help                显示本帮助
  quit / exit         退出"""


def _run_auto(game: str) -> str:
    """整条生命周期自动执行（Flow）。"""
    parts = [_cmd_detect(game), _cmd_research(game)]
    parts.append(_cmd_ensure())
    return "\n".join(parts)


def interactive():
    """交互式对话。传入 -c 命令则只执行一次后退出。"""
    import readline  # 启用终端方向键/历史（仅 Linux/macOS 生效）
    print(describe_capabilities())
    print(HELP_TEXT)
    st = load_state()
    while True:
        try:
            raw = input(f"[{st['game']}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 👋")
            break
        if not raw:
            continue
        cmd, _, arg = raw.partition(" ")
        arg = arg.strip()

        if cmd in ("quit", "exit", "q"):
            print("再见 👋")
            break
        elif cmd in ("help", "h", "?"):
            print(HELP_TEXT)
        elif cmd == "capabilities":
            print(describe_capabilities())
        elif cmd == "state":
            print(json.dumps(load_state(), ensure_ascii=False, indent=2))
        elif cmd == "detect":
            print(_cmd_detect(arg or "florr"))
        elif cmd == "research":
            print(_cmd_research(arg))
        elif cmd == "ensure":
            print(_cmd_ensure())
        elif cmd == "play":
            print(_cmd_play(int(arg) if arg.isdigit() else 0))
        elif cmd == "report":
            print(_cmd_report())
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
            print(f"未知命令: {cmd}（输入 help 查看）")
        st = load_state()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 交互式入口")
    parser.add_argument("-c", "--command", help="执行单条命令后退出(如 report / capabilities)")
    args = parser.parse_args()

    if args.command:
        cmd, _, arg = args.command.partition(" ")
        arg = arg.strip()
        fn = {
            "capabilities": lambda: describe_capabilities(),
            "state": lambda: json.dumps(load_state(), ensure_ascii=False, indent=2),
            "detect": lambda: _cmd_detect(arg or "florr"),
            "research": lambda: _cmd_research(arg),
            "ensure": lambda: _cmd_ensure(),
            "report": lambda: _cmd_report(),
            "skills": lambda: SKILLS.summary(),
            "load": lambda: SKILLS.load(arg),
            "unload": lambda: SKILLS.unload(arg),
            "run_skill": lambda: SKILLS.call(arg),
        }.get(cmd)
        print(fn() if fn else f"未知命令: {cmd}")
        return

    try:
        interactive()
    except KeyboardInterrupt:
        print("\n再见 👋")


if __name__ == "__main__":
    main()