#!/usr/bin/env python3
"""
技能包 report 的实现文件（v2.0 实装）。

v0.8 时期这里只有 9 行演示桩，输出恒为"汇报技能演示"，
`agent_cli run_skill report` 拿到的是一串占位文字，没有任何真实信息。

v2.0 改为读取真实会话档案（agent_state.json）与主循环快照
（run_logs/agent_snapshot.json），输出可直接进报告的结构化进度；
读不到时走离线降级分支并显式标注，绝不抛异常炸穿调用方。

入口名 `report_run` 与 SKILL.md 的 `entry:` 保持一致。
"""
import json
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_SKILL_DIR))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OFFLINE_NOTE = "（离线/dry-run：无 LLM/VLM 密钥，数值取自本地快照）"


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _snapshot():
    try:
        import session
        return _read_json(session.SNAP_PATH)
    except Exception:
        return {}


def _state():
    try:
        import session
        return session.load()
    except Exception:
        return {}


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            f = float(v)
            return int(f) if f == f and abs(f) != float("inf") else default
        except (TypeError, ValueError):
            return default


def report_run(game: str = None, note: str = "", **kw) -> str:
    """
    返回一段结构化汇报。

    参数：
      game -- 游戏档案名；None 时取快照/会话档案里的当前游戏
      note -- 调用方附加说明（原样附在末尾）
    """
    st = _state()
    snap = _snapshot()
    game = game or snap.get("game") or st.get("game") or "unknown"

    hp = snap.get("hp")
    max_hp = snap.get("max_hp")
    hp_text = f"{hp}/{max_hp}" if (hp is not None or max_hp is not None) else "未知"

    threats = snap.get("threats") or []
    if isinstance(threats, list) and threats and isinstance(threats[0], dict):
        top = threats[0]
        threat_text = (f"最高威胁 {top.get('name') or top.get('cat') or '未知'}"
                       f"（威胁分 {top.get('threat', '?')}）")
    else:
        threat_text = "暂无威胁数据"

    skills = st.get("skills_last") or []
    lines = [
        f"[skill:report] 当前游戏: {game}",
        f"  会话状态 : {st.get('status', 'idle')}",
        f"  累计场次 : {_int(st.get('sessions'))}",
        f"  最近回合 : {_int(snap.get('round', st.get('last_rounds')))}",
        f"  累计死亡 : {_int(snap.get('deaths', st.get('total_deaths')))}",
        f"  HP       : {hp_text}",
        f"  战斗决策 : {snap.get('decision') or '未决策'} / 心态 {snap.get('mindset') or '-'}"
        f" / 套装 {snap.get('set') or '-'}",
        f"  威胁预判 : {threat_text}",
        f"  已装技能 : {', '.join(str(s) for s in skills) if skills else '无'}",
    ]
    if note:
        lines.append(f"  备注     : {note}")
    lines.append(f"  {OFFLINE_NOTE}")
    return "\n".join(lines)
