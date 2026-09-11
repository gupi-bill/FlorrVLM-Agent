#!/usr/bin/env python3
"""
FlorrVLM-Agent 会话记忆 & 断点续玩  session.py  (v1.4)
======================================================
把"上次玩到哪、死了几次、加载了哪些技能、什么游戏"记在 agent_state.json。
下次启动自动读出并汇报"续玩"，进度不丢。

主要接口（都只用标准库，零依赖）：
  load() / save(state)                读/写会话档案(agent_state.json)
  record_start(game, skills)          开玩前：记下"从哪续"并返回是否可续玩
  record_end(game, rounds, deaths,    结束后：累加回合/死亡/场次，存技能与汇报
             skills, report)
  resume_info()                       返回本次"续玩说明"文本（无则空串）
  describe()                          “session”命令看到的记忆摘要
"""
import os
import json
from datetime import datetime

import config  # 读取 paths.run_logs，取监控快照里的真实回合/死亡

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "agent_state.json")
SNAP_PATH = os.path.join(
    BASE_DIR,
    config.get("paths.run_logs", "run_logs"),
    "agent_snapshot.json",
)


# ---------------------------------------------------------------------------
# 读写会话档案
# ---------------------------------------------------------------------------
def _default() -> dict:
    return {
        "game": os.getenv("AGENT_GAME", "florr"),
        "status": "idle",
        "last_played": None,
        "last_rounds": 0,
        "last_report": "",
        "brief": None,
        # v1.4 新增字段
        "sessions": 0,          # 累计开玩场次
        "total_deaths": 0,      # 累计死亡数(跨重启累加)
        "skills_last": [],      # 上次退出时加载的技能
        "resumed": False,       # 本次启动是否已做过"续玩"标记
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }


def load() -> dict:
    """读会话档案；不存在或损坏 → 全新默认档案，并补齐新字段。"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        d = _default()
        d.update(st or {})
        return d
    except Exception:
        return _default()


def save(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise RuntimeError(f"会话档案保存失败: {e}") from e


# ---------------------------------------------------------------------------
# 监控快照里的真实回合 / 死亡（agent_main 每 N 回合写一次）
# ---------------------------------------------------------------------------
def snapshot_rounds_deaths() -> tuple:
    """返回 (round, deaths)；读不到快照返回 (0, 0)，不影响主流程。"""
    if not os.path.exists(SNAP_PATH):
        return 0, 0
    try:
        with open(SNAP_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f) or {}
        return int(snap.get("round", 0) or 0), int(snap.get("deaths", 0) or 0)
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# 开玩前 / 结束后 记账
# ---------------------------------------------------------------------------
def record_start(game: str, skills: list) -> bool:
    """
    进入主循环前调用。
    若上次玩过(有 last_played)，把进度作为"续玩点"记下，返回 True 表示可续玩。
    返回 True 时调用方能据此提示"续玩"并汇报要接着上次的进度打。
    """
    st = load()
    prev_rounds = int(st.get("last_rounds", 0) or 0)
    prev_played = bool(st.get("last_played"))
    resumable = prev_played or prev_rounds > 0
    if resumable:
        # 记下"从哪续"，供后面 resume_info 使用
        st["resume_point"] = {
            "game": game,
            "at": datetime.now().isoformat(timespec="seconds"),
            "from_rounds": prev_rounds,
            "total_deaths_so_far": int(st.get("total_deaths", 0) or 0),
            "skills": list(skills),
        }
    else:
        st["resume_point"] = None
    save(st)
    return resumable


def record_end(game: str, rounds: int, deaths: int, skills: list, report: str = ""):
    """主循环结束后调用：累加场次/死亡，存真实回合、技能与本次汇报。"""
    st = load()
    st["game"] = game
    st["status"] = "done"
    st["last_played"] = datetime.now().isoformat(timespec="seconds")
    st["last_rounds"] = rounds
    st["last_report"] = report
    st["sessions"] = int(st.get("sessions", 0) or 0) + 1
    # 死亡按"本次新增死亡"累加；真实死亡以主循环统计为准
    st["total_deaths"] = int(st.get("total_deaths", 0) or 0) + max(0, int(deaths or 0))
    st["skills_last"] = sorted(set(skills))
    st["resumed"] = False          # 本轮已结束，"续玩"标记复位
    st["resume_point"] = None
    save(st)


def mark_resumed():
    """把 resumed 置 True，避免同一次启动反复提示续玩。"""
    st = load()
    st["resumed"] = True
    save(st)


# ---------------------------------------------------------------------------
# 展示用文案
# ---------------------------------------------------------------------------
def resume_info() -> str:
    """
    返回本次启动的"续玩说明"，无续玩点则返回空串。
    通过 record_start 写入的 resume_point 生成。
    """
    st = load()
    rp = st.get("resume_point")
    if not rp:
        return ""
    if st.get("resumed"):
        # 已提示过：换成"正在继续上次进度"的短说明
        return (f"  继续上次进度: 游戏 {rp['game']} · "
                f"已到回合 {rp['from_rounds']} · 累计死亡 {rp['total_deaths_so_far']} · "
                f"技能: {', '.join(rp['skills']) if rp['skills'] else '无'}")
    prev_rounds = rp["from_rounds"]
    total_d = rp["total_deaths_so_far"]
    got = ["续玩: 检测到上次会话进度"]
    if prev_rounds:
        got.append(f"已到回合 {prev_rounds}")
    if total_d:
        got.append(f"累计死亡 {total_d}")
    if rp.get("skills"):
        got.append(f"加载技能 {', '.join(rp['skills'])}")
    return " · ".join(got)


def describe() -> str:
    """'session' 命令看到的会话记忆摘要。"""
    st = load()
    lines = [f"当前游戏   : {st['game']}",
             f"累计场次   : {st['sessions']}",
             f"累计回合   : {st['last_rounds']}(最近一次)",
             f"累计死亡   : {st['total_deaths']}",
             f"上次游玩   : {st['last_played'] or '从未'}",
             f"最近技能   : {', '.join(st['skills_last']) if st['skills_last'] else '无'}",
             f"最近汇报   : {st['last_report'][:80] if st['last_report'] else '无'}"]
    if st.get("resume_point"):
        lines.append(f"待续玩进度 : {resume_info()}")
    return "\n".join(lines)


def __main__():
    """手动测试：python session.py"""
    print("record_start →", record_start("florr", ["report"]))
    print("resume_info  →", resume_info() or "(无)")
    print(describe())


if __name__ == "__main__":
    __main__()