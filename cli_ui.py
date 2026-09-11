#!/usr/bin/env python3
"""
FlorrVLM-Agent 终端界面工具 cli_ui.py
======================================
v1.0 —— 把原来的纯文本命令行变成"好看"的彩色面板界面。

只负责"渲染"，不含业务逻辑。核心特性：
- 自动判断是否终端(tty)；非终端或设了 NO_COLOR 时自动降级为纯文本，不花屏
- banner()      —— 启动横幅
- panel(...)    —— 带边框的标题面板（帮助/状态/清单都用它）
- chip(tag,..)  —— 状态小标签（✅ 已就绪 / ⚠ 提醒 / ✗ 失败）
- dim()         —— 弱化灰字（说明性文字）
"""
import os
import sys

# ANSI 颜色码
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

# 非终端(管道/脚本)或设置 NO_COLOR 时不用颜色，避免输出乱码
_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if _COLOR else str(text)


def cyan(t):    return _c(CYAN, t)
def green(t):   return _c(GREEN, t)
def yellow(t):  return _c(YELLOW, t)
def red(t):     return _c(RED, t)
def magenta(t): return _c(MAGENTA, t)
def blue(t):    return _c(BLUE, t)
def bold(t):    return _c(BOLD, t)
def dim(t):     return _c(DIM, t)


def banner(title: str = "FlorrVLM-Agent", subtitle: str = "通用游戏操作引擎 v1.0",
           width: int = 46) -> str:
    """居中的彩色横幅。"""
    half = title.center(width - 4)
    sub = subtitle.center(width - 4)
    top = "╔" + "═" * (width - 2) + "╗"
    mid = "║" + " " * (width - 2) + "║"
    bot = "╚" + "═" * (width - 2) + "╝"
    return "\n".join([
        cyan(top),
        cyan("║") + " " * (width - 2) + cyan("║"),
        cyan("║") + bold(magenta(half)) + cyan("║"),
        cyan("║") + dim(sub) + cyan("║"),
        cyan(mid),
        cyan(bot),
    ])


def panel(title: str, lines, width: int = 78) -> str:
    """带标题的边框面板。lines 可以是字符串或字符串列表。"""
    if isinstance(lines, str):
        lines = lines.split("\n")
    title_len = len(title) + 2  # 左右各一个空格
    inner = max(0, width - 4 - title_len)
    top = f"{cyan('┌─')} {bold(title)} {cyan('─' * inner + '┐')}"
    rows = [f"{cyan('│')} {x:<{width - 4}}{cyan('│')}" for x in lines]
    bot = f"{cyan('└' + '─' * (width - 2) + '┘')}"
    return "\n".join([top] + rows + [bot])


def chip(text: str, kind: str = "ok") -> str:
    """状态小标签。kind: ok / warn / err / info"""
    map_kind = {
        "ok": (GREEN, "OK"),
        "warn": (YELLOW, "!"),
        "err": (RED, "✗"),
        "info": (CYAN, "i"),
    }
    code, mark = map_kind.get(kind, (CYAN, "info"))
    return _c(code, f"[{mark}] {text}")