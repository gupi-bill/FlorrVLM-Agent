#!/usr/bin/env python3
"""
Universal-Game-Framework 自动汇报 & 多渠道通知 report_notifier.py  (v1.2)
===============================================================
打完一局/被手动触发时，自动生成一份 markdown 报告，并可推送到本地文件 / Webhook。

能力：
  generate_report()  -> 组装报告文本（读 agent_state.json + agent_snapshot.json + 调参状态）
  notify()           -> 生成报告，按配置落地到文件，可选 POST 到 webhook
  hook_after_play()  -> 供 agent_cli 在 play 结束后自动调用

配置（config.yaml，可选项，默认本地文件）：
  agent.webhook_url  推送到该 URL（留空则只写本地文件）
"""
import json
import os
from datetime import datetime

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "agent_state.json")
SNAP_PATH = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"), "agent_snapshot.json")
LOG_DIR = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _tail_log(n: int = 8) -> list:
    # v2.0：`lines[-0:]` 等价于 `lines[0:]`，n=0 时会把整份日志塞进报告
    if n <= 0:
        return []
    today = datetime.now().strftime("%Y%m%d")
    fpath = os.path.join(LOG_DIR, f"agent_{today}.log")
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def _offline_note() -> str:
    """v2.0：无密钥/无网络环境下的显式标注，避免报告看起来像真实数据。"""
    return "> 本报告由离线/dry-run 通路生成（无 LLM / VLM 密钥，数值来自本地快照）"


def generate_report() -> str:
    st = _read_json(STATE_PATH)
    snap = _read_json(SNAP_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        import auto_tuner
        tune = auto_tuner.status()
    except Exception:
        tune = "（调参模块不可用）"

    brief = st.get("brief") or {}
    lines = []
    lines.append("# Universal-Game-Framework 对局报告")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 当前游戏：{snap.get('game') or st.get('game') or 'florr'}")
    lines.append(f"- 会话状态：{st.get('status', 'idle')}")
    lines.append(f"- 本局回合数：{snap.get('round', 0) or 0}")
    lines.append(f"- 累计死亡：{snap.get('deaths', 0) or 0}")
    # v2.0：无快照时原样打出 "None/None"，读者无法区分"没数据"和"血量为空"
    hp, max_hp = snap.get("hp"), snap.get("max_hp")
    lines.append(f"- HP：{hp}/{max_hp}" if (hp is not None or max_hp is not None)
                 else "- HP：未知（无快照）")
    lines.append("")
    lines.append(_offline_note())
    lines.append("")
    lines.append("## 游戏了解（brief）")
    if brief:
        for k, v in brief.items():
            lines.append(f"- {k}：{v or '(未填写)'}")
    else:
        lines.append("- 尚未做过 brief")
    lines.append("")
    lines.append("## 最新战斗")
    if snap.get("decision"):
        lines.append(f"- 决策：{snap['decision']} / 心态：{snap.get('mindset')} / 推荐套装：{snap.get('set')}")
    threats = snap.get("threats", [])
    if threats:
        lines.append("- 近期威胁预判：")
        for t in threats[:5]:
            lines.append(f"  - {t.get('name') or t.get('cat')}：威胁 {t.get('threat')} @({t.get('x')}, {t.get('y')})")
    else:
        lines.append("- 暂无威胁数据")
    lines.append("")
    lines.append(f"## 调参状态\n{tune}")
    lines.append("")
    tl = _tail_log()
    if tl:
        lines.append("## 最近日志")
        lines += [f"- {x}" for x in tl]
    return "\n".join(lines)


_DEFAULT_WEBHOOK = ""


def _webhook_url() -> str:
    return config.get("agent.webhook_url", _DEFAULT_WEBHOOK) or ""


def write_report_file(text: str, suffix: str = "") -> str:
    """写一份 report_YYYYMMDD_HHMMSS[_suffix].md 到 run_logs/，返回路径。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    fname = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}.md"
    path = os.path.join(LOG_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def push_webhook(text: str) -> tuple:
    """
    把报告 POST 到配置的 webhook。

    v2.0：返回值由 bool 改为 `(ok, 原因)`。原先只有 True/False，
    调用方无法区分「没配 URL」「requests 缺失」「网络失败」「HTTP 非 2xx」，
    排障时只能看到一句"推送失败"。
    """
    url = _webhook_url()
    if not url:
        return False, "未配置 Webhook"
    try:
        import requests
    except ImportError:
        return False, "requests 未安装（离线环境）"
    try:
        r = requests.post(url, json={"text": text}, timeout=5)
    except Exception as e:
        return False, f"请求异常: {type(e).__name__}"
    if 200 <= getattr(r, "status_code", 0) < 300:
        return True, f"HTTP {r.status_code}"
    return False, f"HTTP {getattr(r, 'status_code', '?')}"


def notify() -> list:
    """生成报告 + 落地文件 + 可选 webhook。返回动作清单。"""
    text = generate_report()
    actions = []
    try:
        path = write_report_file(text)
        actions.append(f"已写报告: {path}")
    except (OSError, TypeError, ValueError) as e:
        actions.append(f"写报告失败: {e}")
    ok, why = push_webhook(text)
    if _webhook_url():
        actions.append(f"已推送到 Webhook（{why}）" if ok else f"Webhook 推送失败: {why}")
    else:
        actions.append("未配置 Webhook(仅本地文件)")
    return actions


# ---------------------------------------------------------------------------
# v1.7 局中定时汇报：轻量进度，不叠加报告文件，只覆盖单文件 + 可选 Webhook
# ---------------------------------------------------------------------------
def notify_progress(rounds: int, deaths: int, game: str = "florr") -> list:
    """
    主循环里按 report_every 轮间隔调用。
    生成一段简短的实时进度文本，写入 run_logs/progress_report.md（覆盖），
    并在配置了 webhook 时 POST。返回动作清单（供日志/测试）。
    """
    text = _progress_text(rounds, deaths, game)
    actions = []
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, "progress_report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        actions.append(f"进度已更新: {path}")
    except (OSError, TypeError) as e:
        actions.append(f"写进度失败: {e}")
    if _webhook_url():
        ok, why = push_webhook(text)
        actions.append(f"已推送 Webhook（{why}）" if ok else f"Webhook 推送失败: {why}")
    return actions


def _progress_text(rounds: int, deaths: int, game: str = "florr") -> str:
    snap = _read_json(SNAP_PATH)
    return (
        f"# Universal-Game-Framework 局中进度\n\n"
        f"- 更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- 游戏：{game}\n"
        f"- 回合：{rounds}\n"
        f"- 死亡：{deaths}\n"
        f"- HP：{snap.get('hp')}/{snap.get('max_hp')}\n"
        f"- 决策：{snap.get('decision')} / 心态：{snap.get('mindset')} / 套装：{snap.get('set')}\n"
    )


if __name__ == "__main__":
    print(generate_report())
    print("---")
    for a in notify():
        print(a)