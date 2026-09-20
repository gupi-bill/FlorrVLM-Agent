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
import json
import math
import os
from datetime import datetime

import config  # 读取 paths.run_logs，取监控快照里的真实回合/死亡

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "agent_state.json")
HISTORY_FILE = os.path.join(BASE_DIR, "session_history.json")  # v1.5 多局战绩历史
SNAP_PATH = os.path.join(
    BASE_DIR,
    config.get("paths.run_logs", "run_logs"),
    "agent_snapshot.json",
)


def safe_int(v, default: int = 0) -> int:
    """
    v2.0：把任意脏值收敛成 int。

    历史 bug：主循环/快照/历史文件里的 round / deaths 若为 None、空串、
    非数字字符串或 NaN，原实现 `int(x or 0)` 会抛 ValueError / TypeError，
    直接把 `agent_cli._cmd_play` 的收尾记账炸掉（一局白打）。
    """
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, float):
        # int(inf) / int(nan) 直接抛 OverflowError / ValueError
        return int(v) if math.isfinite(v) else default
    try:
        return int(v)
    except (TypeError, ValueError):
        pass
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return int(f) if math.isfinite(f) else default


def _history_max() -> int:
    """v2.0：运行时取值，避免 config 热加载后上限不生效（原先 import 时绑定）。"""
    return max(1, safe_int(config.get("session.history_max", 100), 100))


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
    except Exception:
        return _default()
    # v2.0：档案被写坏成 list / 字符串 / 数字时，原实现 `d.update(st)` 会抛
    # "cannot convert dictionary update sequence"，整个 session 命令不可用。
    if not isinstance(st, dict):
        return _default()
    d = _default()
    d.update(st)
    return d


def save(state: dict):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError) as e:
        # v2.0：TypeError = 含不可序列化对象（set / datetime 等），给可读错误
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
        if not isinstance(snap, dict):
            return 0, 0
        return safe_int(snap.get("round")), safe_int(snap.get("deaths"))
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
    prev_rounds = safe_int(st.get("last_rounds"))
    prev_played = bool(st.get("last_played"))
    resumable = prev_played or prev_rounds > 0
    if resumable:
        # 记下"从哪续"，供后面 resume_info 使用
        st["resume_point"] = {
            "game": game,
            "at": datetime.now().isoformat(timespec="seconds"),
            "from_rounds": prev_rounds,
            "total_deaths_so_far": safe_int(st.get("total_deaths")),
            "skills": list(skills or []),
        }
    else:
        st["resume_point"] = None
    save(st)
    return resumable


def record_end(game: str, rounds: int, deaths: int, skills: list, report: str = ""):
    """主循环结束后调用：累加场次/死亡，存真实回合、技能与本次汇报，并写入战绩历史。"""
    st = load()
    rounds = safe_int(rounds)
    deaths = safe_int(deaths)
    skills = sorted({str(s) for s in (skills or [])})
    st["game"] = game
    st["status"] = "done"
    st["last_played"] = datetime.now().isoformat(timespec="seconds")
    st["last_rounds"] = rounds
    st["last_report"] = report or ""
    st["sessions"] = safe_int(st.get("sessions")) + 1
    # 死亡按"本次新增死亡"累加；真实死亡以主循环统计为准（负数不倒扣）
    st["total_deaths"] = safe_int(st.get("total_deaths")) + max(0, deaths)
    st["skills_last"] = skills
    st["resumed"] = False          # 本轮已结束，"续玩"标记复位
    st["resume_point"] = None
    save(st)
    _append_history({
        "at": st["last_played"],
        "game": game,
        "rounds": rounds,
        "deaths": deaths,
        "skills": skills,
    })


def mark_resumed():
    """把 resumed 置 True，避免同一次启动反复提示续玩。"""
    st = load()
    st["resumed"] = True
    save(st)


# ---------------------------------------------------------------------------
# v1.5 多局战绩历史 & 汇总统计
# ---------------------------------------------------------------------------
def _append_history(record: dict):
    """把一局的战绩追加进 session_history.json，超出上限删最早。"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                h = json.load(f)
            if not isinstance(h, list):
                h = []
        else:
            h = []
        if not all(isinstance(r, dict) for r in h):
            h = [r for r in h if isinstance(r, dict)]
        h.append(record)
        limit = _history_max()
        if len(h) > limit:
            h = h[-limit:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError):
        pass


def history() -> list:
    """读战绩历史（旧→新，与文件内顺序一致；stats() 内自行倒序展示）。"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            h = json.load(f)
        if not isinstance(h, list):
            return []
        return [r for r in h if isinstance(r, dict)]
    except Exception:
        return []


def stats() -> dict:
    """汇总战绩：总场次/总回合/死亡/均值/最佳，供 stats 命令与大盘用。"""
    h = history()
    if not h:
        return {"sessions": 0, "total_rounds": 0, "total_deaths": 0,
                "avg_rounds": 0, "best_rounds": 0, "recent": []}
    records = [r for r in h if isinstance(r, dict)]
    if not records:
        return {"sessions": 0, "total_rounds": 0, "total_deaths": 0,
                "avg_rounds": 0, "best_rounds": 0, "recent": []}
    total_rounds = sum(safe_int(r.get("rounds")) for r in records)
    total_deaths = sum(safe_int(r.get("deaths")) for r in records)
    best_rounds = max(safe_int(r.get("rounds")) for r in records)
    return {
        "sessions": len(records),
        "total_rounds": total_rounds,
        "total_deaths": total_deaths,
        "avg_rounds": round(total_rounds / len(records), 1),
        "best_rounds": best_rounds,
        "recent": records[-5:][::-1],
    }


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
    if not isinstance(rp, dict):
        return ""
    skills = [str(s) for s in (rp.get("skills") or [])]
    prev_rounds = safe_int(rp.get("from_rounds"))
    total_d = safe_int(rp.get("total_deaths_so_far"))
    if st.get("resumed"):
        # 已提示过：换成"正在继续上次进度"的短说明
        return (f"  继续上次进度: 游戏 {rp.get('game') or '未知'} · "
                f"已到回合 {prev_rounds} · 累计死亡 {total_d} · "
                f"技能: {', '.join(skills) if skills else '无'}")
    got = ["续玩: 检测到上次会话进度"]
    if prev_rounds:
        got.append(f"已到回合 {prev_rounds}")
    if total_d:
        got.append(f"累计死亡 {total_d}")
    if skills:
        got.append(f"加载技能 {', '.join(skills)}")
    return " · ".join(got)


def describe() -> str:
    """'session' 命令看到的会话记忆摘要。"""
    st = load()
    # v2.0：档案里 last_report 可能是 JSON null（原 `None[:80]` 会 TypeError）
    # 或 dict/list（切片会 KeyError / TypeError），统一收敛成字符串
    raw_report = st.get("last_report") or ""
    report = raw_report if isinstance(raw_report, str) else str(raw_report)
    skills = [str(s) for s in (st.get("skills_last") or [])]
    lines = [f"当前游戏   : {st.get('game', 'florr')}",
             f"累计场次   : {safe_int(st.get('sessions'))}",
             f"累计回合   : {safe_int(st.get('last_rounds'))}(最近一次)",
             f"累计死亡   : {safe_int(st.get('total_deaths'))}",
             f"上次游玩   : {st.get('last_played') or '从未'}",
             f"最近技能   : {', '.join(skills) if skills else '无'}",
             f"最近汇报   : {report[:80] if report else '无'}"]
    if st.get("resume_point"):
        lines.append(f"待续玩进度 : {resume_info()}")
    return "\n".join(lines)


def stats_text() -> str:
    """'stats' 命令看到的汇总统计文本。"""
    s = stats()
    head = [f"累计场次   : {s['sessions']}",
            f"累计回合   : {s['total_rounds']}",
            f"累计死亡   : {s['total_deaths']}",
            f"场均回合   : {s['avg_rounds']}",
            f"单局最高回合: {s['best_rounds']}"]
    if s["recent"]:
        head.append("最近战绩(新→旧):")
        head += [f"  {str(r.get('at') or '未知')[:16]} · {r.get('game') or '未知'} · "
                 f"回合 {safe_int(r.get('rounds'))} · 死亡 {safe_int(r.get('deaths'))}"
                 for r in s["recent"]]
    else:
        head.append("暂无战绩(打完 play 后自动记录)")
    return "\n".join(head)


def __main__():
    """手动测试：python session.py"""
    print("record_start →", record_start("florr", ["report"]))
    print("resume_info  →", resume_info() or "(无)")
    print(describe())
    print()
    print("stats_text:")
    print(stats_text())


if __name__ == "__main__":
    __main__()