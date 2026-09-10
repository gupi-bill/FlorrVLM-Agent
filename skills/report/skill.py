#!/usr/bin/env python3
"""exampleskill 汇报(report) 的实现文件。"""

def report_run(game: str = "unknown", note: str = "") -> str:
    """返回一段结构化汇报。这是 skill.py 里的入口函数，名与 SKILL.md 的 entry 一致。"""
    return (f"[skill:report] 当前游戏: {game}\n"
            f"  状态: 汇报技能演示\n"
            f"  备注: {note}\n"
            + "  —— 这是一个用 Skill 机制附加到 Agent 的能力！")