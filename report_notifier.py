#!/usr/bin/env python3
"""
FlorrVLM-Agent 自动汇报 & 多渠道通知 report_notifier.py  (v1.2)
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
    today = datetime.now().strftime("%Y%m%d")
    fpath = os.path.join(LOG_DIR, f"agent_{today}.log")
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


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
    lines.append("# FlorrVLM-Agent 对局报告")
    lines.append("")
    lines.append(f"- 生成时间：{now}")
    lines.append(f"- 当前游戏：{snap.get('game') or st.get('game') or 'florr'}")
    lines.append(f"- 会话状态：{st.get('status', 'idle')}")
    lines.append(f"- 本局回合数：{snap.get('round', 0)}")
    lines.append(f"- 累计死亡：{snap.get('deaths', 0)}")
    lines.append(f"- HP：{snap.get('hp')}/{snap.get('max_hp')}")
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


def write_report_file(text: str) -> str:
    """写一份 report_YYYYMMDD_HHMMSS.md 到 run_logs/，返回路径。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    fname = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path = os.path.join(LOG_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def push_webhook(text: str) -> bool:
    """把报告 POST 到配置的 webhook；HTTP 2xx 视为成功。"""
    url = _webhook_url()
    if not url:
        return False
    try:
        import requests
        r = requests.post(url, json={"text": text}, timeout=5)
        return 200 <= r.status_code < 300
    except Exception:
        return False


def notify() -> list:
    """生成报告 + 落地文件 + 可选 webhook。返回动作清单。"""
    text = generate_report()
    actions = []
    try:
        path = write_report_file(text)
        actions.append(f"已写报告: {path}")
    except OSError as e:
        actions.append(f"写报告失败: {e}")
    if _webhook_url():
        if push_webhook(text):
            actions.append("已推送到 Webhook")
        else:
            actions.append("Webhook 推送失败(检查 URL)")
    else:
        actions.append("未配置 Webhook(仅本地文件)")
    return actions


if __name__ == "__main__":
    print(generate_report())
    print("---")
    for a in notify():
        print(a)