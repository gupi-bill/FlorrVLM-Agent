#!/usr/bin/env python3
"""
Universal-Game-Framework 可视化监控大盘 admin_panel.py  (v2.0 / S11：主 UI)
=====================================================
浏览器打开 http://127.0.0.1:5002 即可实时查看：
- 指标卡片：当前游戏 / 会话状态 / 本局回合数 / 累计死亡 / 知识库规模 / 时间
- BOSS 威胁面板：最近一次预判出的威胁实体(来自 run_logs/agent_snapshot.json)
- 决策信息：当前 decision / mindset / 推荐套装
- 日志面板：run_logs/ 当天尾部(倒序自动滚动)
- 资源占用：进程 CPU / 内存（有 psutil 用 psutil，否则回退 /proc）
- 运行模式：在线 / dry-run + 感知后端（auto/mock/http），离线模式标黄（v2.0 S11）
- 感知依赖：读不到快照时页面显示红色告警，而不是空白

只读，不修改任何文件。纯标准库（psutil 可选）。
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import config
import session  # v1.6 会话记忆 & 多局战绩

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
KB_DIR = os.path.join(BASE_DIR, config.get("paths.knowledge_md", "knowledge_md"))
SNAP_PATH = os.path.join(LOG_DIR, "agent_snapshot.json")
STATE_PATH = os.path.join(BASE_DIR, "agent_state.json")
PANEL_PORT = config.get("server.panel_port", 5002)
PROC = None
try:
    import psutil
    PROC = psutil.Process(os.getpid())
except Exception:
    PROC = None


def _snapshot() -> dict:
    """读 agent_main 写的最新快照；无则返回空。"""
    if not os.path.exists(SNAP_PATH):
        return {}
    try:
        with open(SNAP_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _late_log(n: int = 40) -> list:
    """当天日志尾部 n 行（倒序，最新在前）。"""
    today = datetime.now().strftime("%Y%m%d")
    fpath = os.path.join(LOG_DIR, f"agent_{today}.log")
    if not os.path.exists(fpath):
        return []
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    return lines[-n:][::-1]


def _kb_info() -> dict:
    if not os.path.isdir(KB_DIR):
        return {"count": 0, "bytes": 0}
    count = 0
    total = 0
    for root, _, files in os.walk(KB_DIR):
        for fn in files:
            if fn.endswith(".md"):
                count += 1
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
    return {"count": count, "bytes": total}


def _resources() -> dict:
    """进程 CPU(%) 与内存(MB)。没有 psutil 则只给占用字节。"""
    if PROC is not None:
        try:
            return {"cpu": round(PROC.cpu_percent(interval=0.1), 1),
                    "mem_mb": round(PROC.memory_info().rss / 1048576, 1)}
        except Exception:
            return {"cpu": -1, "mem_mb": -1}
    try:
        with open(f"/proc/{os.getpid()}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return {"cpu": -1, "mem_mb": round(int(line.split()[1]) / 1024, 1)}
    except Exception:
        pass
    return {"cpu": -1, "mem_mb": -1}


def _mode() -> dict:
    """S11：当前运行模式（在线 / dry-run、真实感知 / mock 感知）。

    大盘只做展示，不替用户决定模式；模式由 launcher.py 的 --dry-run / --mock
    或环境变量 UGF_DRY_RUN / UGF_PERCEPTION_BACKEND 决定。
    """
    # v2.0 S21：模式判定此前在本函数里重写了一遍环境变量解析，与 config / agent_main
    # 各有一套口径，容易"大盘显示 mock、实际在等真机"。改为统一读 config.runtime_mode()，
    # 本函数只负责 auto 的可用性探测与展示文案。
    m = config.runtime_mode()
    dry = m["dry_run"]
    backend = m["perception_backend"]
    if backend == "auto":
        # auto 的实际结果取决于本机有没有截图工具 + YOLO，这里按依赖可探测性给个提示
        try:
            import perception_server  # noqa: F401
            backend_label = "auto"
        except Exception:
            backend_label = "auto(不可用)"
    else:
        backend_label = backend
    return {
        "run": "dry-run（不碰真实键鼠）" if dry else "在线（真实操作）",
        "perception": backend_label,
        "label": ("dry-run" if dry else "在线") + " / "
                 + ("mock" if backend_label == "mock" else backend_label),
        "offline": dry or backend_label == "mock",
        # S21 新增：LLM / VLM / 激活游戏，避免只看得到模式看不到能力开关
        "llm": m["llm"],
        "vlm": m["vlm"],
        "game": m["game"],
        "summary": config.runtime_mode_text(),
    }


def _status() -> dict:
    snap = _snapshot()
    st = _state()
    kb = _kb_info()
    res = _resources()
    sts = session.stats()  # v1.6 多局战绩汇总
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "has_snap": bool(snap),
        "game": snap.get("game") or st.get("game") or "florr",
        "status": st.get("status", "idle"),
        "round": snap.get("round", 0),
        "deaths": snap.get("deaths", 0),
        "hp": snap.get("hp"),
        "max_hp": snap.get("max_hp"),
        "decision": snap.get("decision"),
        "mindset": snap.get("mindset"),
        "set": snap.get("set"),
        "threats": snap.get("threats", []),
        "kb_count": kb["count"],
        "kb_mb": round(kb["bytes"] / 1048576, 2),
        "cpu": res["cpu"],
        "mem_mb": res["mem_mb"],
        "log": _late_log(),
        # v1.6 会话记忆 & 战绩
        "sess_total": st.get("total_deaths", 0),   # 累计死亡(跨重启)
        "session_count": sts["sessions"],
        "total_rounds": sts["total_rounds"],
        "avg_rounds": sts["avg_rounds"],
        "best_rounds": sts["best_rounds"],
        "recent": sts["recent"],
        # v2.0 S11：运行模式（在线/dry-run + 感知后端）
        "mode": _mode(),
    }


PAGE = """<!DOCTYPE html><html lang="zh"><meta charset="utf-8">
<title>Universal-Game-Framework 监控大盘</title>
<style>
 :root{--bg:#0b101d;--card:#141b2c;--line:#26314a;--tx:#e6e8ee;--mut:#8b96ad;
       --ok:#34d399;--warn:#fbbf24;--err:#f87171;--acc:#60a5fa}
 *{box-sizing:border-box}
 body{font-family:ui-sans-serif,system-ui;background:var(--bg);color:var(--tx);
      margin:0;padding:18px}
 h1{font-size:17px;margin:0 0 2px}
 .sub{color:var(--mut);font-size:12px;margin-bottom:14px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
 .card .lab{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
 .card .val{font-size:22px;font-weight:600;margin-top:4px}
 .row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
 .box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
 .box h2{font-size:12px;color:var(--acc);margin:0 0 8px;text-transform:uppercase;letter-spacing:.5px}
 .thr{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed #223}
 .thr:last-child{border:0}
 .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
 .c-boss{background:#f472b6}.c-elite{background:#fbbf24}.c-normal{background:#34d399}.c-player{background:#60a5fa}
 .logline{border-bottom:1px solid #1c2336;padding:2px 0;font-size:12px}
 .muted{color:var(--mut)}.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
 .banner{background:var(--err);color:#fff;padding:8px 10px;border-radius:8px;margin-bottom:10px;display:none}
 .nav{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
 .btn{display:inline-block;background:var(--card);border:1px solid var(--line);color:var(--tx);
      text-decoration:none;padding:7px 12px;border-radius:9px;font-size:13px}
 .btn:hover{border-color:var(--acc)}
 .btn.primary{background:var(--acc);border-color:var(--acc);color:#0b101d;font-weight:600}
 .btn.danger{background:#3a1d24;border-color:#7f2d3a;color:#fca5a5}
 .gm-hero{background:linear-gradient(135deg,#16233d,#1b2b4a);border:1px solid var(--line);
          border-radius:14px;padding:14px;margin-bottom:12px}
 .gm-hero h2{margin:0 0 6px;font-size:16px}
 .kv{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:12px;color:var(--mut)}
 @media(max-width:700px){.row{grid-template-columns:1fr}}
</style>
<h1>Universal-Game-Framework 监控大盘</h1>
<div class="sub" id="time">加载中…</div>
<div class="nav">
  <a class="btn" href="/settings">⚙ 设置</a>
  <a class="btn primary" href="/game">🎮 打开游戏模式</a>
</div>
<div class="banner" id="banner">⚠ 未检测到 Agent 运行快照（可能还没 `play`，或感知服务未启动）</div>
<div class="grid">
  <div class="card"><div class="lab">游戏</div><div class="val" id="game">—</div></div>
  <div class="card"><div class="lab">状态</div><div class="val" id="status">—</div></div>
  <div class="card"><div class="lab">回合数</div><div class="val ok" id="round">—</div></div>
  <div class="card"><div class="lab">累计死亡</div><div class="val warn" id="deaths">—</div></div>
  <div class="card"><div class="lab">知识库</div><div class="val" id="kb">—</div></div>
  <div class="card"><div class="lab">CPU / 内存</div><div class="val" id="res">—</div></div>
  <div class="card"><div class="lab">运行模式</div><div class="val" id="mode">—</div></div>
  <div class="card"><div class="lab">累计场次 / 回合(v1.5)</div><div class="val" id="sess">—</div></div>
</div>
<div class="row">
  <div class="box">
    <h2>近期威胁预判（前 6）</h2>
    <div id="threats"><div class="muted">等待数据…</div></div>
    <h2 style="margin-top:12px">当前决策</h2>
    <div id="decision" class="muted">—</div>
  </div>
  <div class="box">
    <h2>运行日志（最新在前）</h2>
    <div id="log"></div>
  </div>
</div>
<div class="box">
  <h2>多局战绩（最多 5 局，新→旧）</h2>
  <div id="hist"><div class="muted">暂无战绩</div></div>
</div>
<script>
const CAT={'highest_boss':'c-boss','boss':'c-boss','elite':'c-elite','normal':'c-normal','player':'c-player'};
async function refresh(){
  const r=await fetch('/api/status');const d=await r.json();
  document.getElementById('time').textContent='更新时间: '+d.time+'　|　HP '+d.hp+'/'+d.max_hp+'　|　决策 '+d.decision+'/'+d.mindset;
  document.getElementById('banner').style.display=d.has_snap?'none':'block';
  document.getElementById('game').textContent=d.game;
  const s=document.getElementById('status');s.textContent=d.status;
  s.className=d.has_snap?'val ok':'val'; 
  document.getElementById('round').textContent=d.round;
  document.getElementById('deaths').textContent=d.deaths;
  document.getElementById('kb').textContent=d.kb_count+' 篇 / '+d.kb_mb+' MB';
  document.getElementById('res').textContent=(d.cpu>=0?d.cpu+'%':'—')+' / '+d.mem_mb+'MB';
  const m=document.getElementById('mode');m.textContent=d.mode.label;
  m.className=d.mode.offline?'val warn':'val ok';
  m.title='运行: '+d.mode.run+' ｜ 感知: '+d.mode.perception
        +' ｜ LLM: '+d.mode.llm+' ｜ VLM: '+d.mode.vlm;
  document.getElementById('sess').textContent=d.session_count+' 场 / '+d.total_rounds+' 回(均 '+d.avg_rounds+' · 最高 '+d.best_rounds+')';
  document.getElementById('hist').innerHTML=d.recent.map(h=>
    '<div class="thr"><span>'+(h.at||'')+'</span>'
    +'<span class="muted">'+h.game+' · 回合 '+h.rounds+' · 死亡 '+h.deaths+'</span></div>'
  ).join('')||'<div class="muted">暂无战绩</div>';
  document.getElementById('threats').innerHTML=d.threats.map(t=>
    '<div class="thr"><span><span class="dot '+ (CAT[t.cat]||'c-normal') +'"></span>'
    +(t.name||t.cat)+'</span><span class="muted">威胁 '+t.threat+'　('+t.x+', '+t.y+')</span></div>'
  ).join('')||'<div class="muted">暂无威胁数据</div>';
  document.getElementById('decision').innerHTML=(d.decision?'决策 <b>'+d.decision+'</b> · 心态 '+d.mindset+' · 推荐套装 '+d.set:'<span class="muted">—</span>');
  document.getElementById('log').innerHTML=d.log.map(l=>'<div class="logline">'+l+'</div>').join('')||'<div class="muted">暂无日志</div>';
}
refresh();setInterval(refresh,3000);
</script></html>"""


# ---------------------------------------------------------------------------
# 设置页 / 游戏模式（主界面入口）
# ---------------------------------------------------------------------------
GAME_PROC = {"popen": None, "mode": None, "started": None, "last": ""}


def _local_only(handler) -> bool:
    """控制类接口只允许本机访问（面板监听 0.0.0.0，不能让局域网谁都能起停进程）。"""
    return handler.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def _profiles() -> list:
    d = os.path.join(BASE_DIR, "game_profiles")
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d)
                  if f.endswith(".yaml") and not f.startswith("_"))


def _switch_game(name: str) -> str:
    path = os.path.join(BASE_DIR, "config.yaml")
    if not os.path.exists(path):
        return "config.yaml 不存在"
    if name not in _profiles():
        return f"档案不存在: {name}"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r"(?m)^(\s*game:\s*)([\w.-]+)",
                 lambda m: f"{m.group(1)}{name}", text, count=1)
    if new == text:
        return "未找到可切换的 game: 行"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return f"已切换当前游戏 → {name}（下轮生效）"


def _start_game(rounds: int = 0, dry: bool = True) -> str:
    p = GAME_PROC.get("popen")
    if p is not None and p.poll() is None:
        return "Agent 已在运行中，无需重复启动"
    env = dict(os.environ)
    env["UGF_DRY_RUN"] = "1" if dry else "0"
    cmd = [sys.executable, "agent_main.py"]
    if rounds:
        cmd += ["--rounds", str(rounds)]
    try:
        GAME_PROC["popen"] = subprocess.Popen(
            cmd, cwd=BASE_DIR, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except Exception as e:
        return f"启动失败: {e}"
    GAME_PROC["mode"] = "dry-run" if dry else "online"
    GAME_PROC["started"] = datetime.now().strftime("%H:%M:%S")
    return "已启动（%s，%s）" % (GAME_PROC["mode"],
                              "无限轮" if not rounds else f"{rounds} 轮")


def _stop_game() -> str:
    p = GAME_PROC.get("popen")
    if p is None or p.poll() is not None:
        GAME_PROC["popen"] = None
        return "当前没有运行中的 Agent"
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()
    GAME_PROC["popen"] = None
    return "已停止"


def _game_running() -> bool:
    p = GAME_PROC.get("popen")
    return p is not None and p.poll() is None


SHARED_CSS = """
:root{--bg:#0b101d;--card:#141b2c;--line:#26314a;--tx:#e6e8ee;--mut:#8b96ad;
      --ok:#34d399;--warn:#fbbf24;--err:#f87171;--acc:#60a5fa}
*{box-sizing:border-box}
body{font-family:ui-sans-serif,system-ui;background:var(--bg);color:var(--tx);margin:0;padding:18px}
h1{font-size:17px;margin:0 0 8px}
h2{font-size:12px;color:var(--acc);margin:0 0 8px;text-transform:uppercase;letter-spacing:.5px}
.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:12px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.card .lab{color:var(--mut);font-size:11px;text-transform:uppercase}
.card .val{font-size:22px;font-weight:600;margin-top:4px}
.nav{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}
.btn{display:inline-block;background:var(--card);border:1px solid var(--line);color:var(--tx);
     text-decoration:none;padding:7px 12px;border-radius:9px;font-size:13px;cursor:pointer;font-family:inherit}
.btn:hover{border-color:var(--acc)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#0b101d;font-weight:600}
.btn.danger{background:#3a1d24;border-color:#7f2d3a;color:#fca5a5}
.gm-hero{background:linear-gradient(135deg,#16233d,#1b2b4a);border:1px solid var(--line);
         border-radius:14px;padding:14px;margin-bottom:12px}
.gm-hero h2{margin:0 0 6px;font-size:16px}
.kv{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:12px;color:var(--mut)}
.thr{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed #223}
.thr:last-child{border:0}
.logline{border-bottom:1px solid #1c2336;padding:2px 0;font-size:12px}
.muted{color:var(--mut)}.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
@media(max-width:700px){.row{grid-template-columns:1fr}}
"""

SETTINGS_PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>设置 · Universal-Game-Framework</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static">
<h1>⚙ 设置</h1>
<div class="nav">
  <a class="btn" href="/">← 返回监控大盘</a>
  <a class="btn primary" href="/game">🎮 打开游戏模式</a>
</div>
<div class="box">
  <h2>运行模式</h2>
  <div id="mode" class="muted">读取中…</div>
</div>
<div class="box" style="margin-top:12px">
  <h2>游戏档案</h2>
  <div class="muted" style="margin-bottom:8px">当前：<b id="cur">—</b></div>
  <select id="prof" class="btn"></select>
  <button class="btn" onclick="sw()">切换</button>
  <div id="swmsg" class="muted" style="margin-top:8px"></div>
</div>
<div class="box" style="margin-top:12px">
  <h2>MCP 服务</h2>
  <div class="muted">以 stdio 形式对外暴露 16 个工具（kb_* / perceive_game / predict_all_entities / game_action …）。
  已在 <code>~/.workbuddy/mcp.json</code> 注册为 <code>ugf</code>，在连接器里信任后即可被其他 Agent 调用。</div>
</div>
<script>
async function load(){
  const r=await fetch('/api/game/state');const d=await r.json();
  document.getElementById('mode').innerHTML='<b>'+d.mode_text+'</b>';
  document.getElementById('cur').textContent=d.game;
  const s=document.getElementById('prof');
  s.innerHTML=d.profiles.map(p=>'<option value="'+p+'"'+(p===d.game?' selected':'')+'>'+p+'</option>').join('');
}
async function sw(){
  const v=document.getElementById('prof').value;
  const r=await fetch('/api/game/switch?name='+encodeURIComponent(v));
  document.getElementById('swmsg').textContent=(await r.json()).msg;
  load();
}
load();
</script>
"""

GAME_PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>游戏模式 · Universal-Game-Framework</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static">
<div class="gm-hero">
  <h2>🎮 游戏模式</h2>
  <div class="kv">
    <span>状态：<b id="run">—</b></span>
    <span>模式：<b id="mode">—</b></span>
    <span>档案：<b id="game">—</b></span>
    <span>启动于：<span id="at">—</span></span>
  </div>
</div>
<div class="nav">
  <button class="btn primary" onclick="act('/api/game/start?dry=1&rounds=20')">▶ 试跑 20 轮（dry-run）</button>
  <button class="btn" onclick="act('/api/game/start?dry=1')">▶ 持续试跑</button>
  <button class="btn danger" onclick="act('/api/game/stop')">■ 停止</button>
  <a class="btn" href="/settings">⚙ 设置</a>
  <a class="btn" href="/">← 监控大盘</a>
</div>
<div class="grid">
  <div class="card"><div class="lab">回合数</div><div class="val ok" id="round">—</div></div>
  <div class="card"><div class="lab">累计死亡</div><div class="val warn" id="deaths">—</div></div>
  <div class="card"><div class="lab">当前决策</div><div class="val" id="decision" style="font-size:16px">—</div></div>
  <div class="card"><div class="lab">知识库</div><div class="val" id="kb">—</div></div>
</div>
<div class="row">
  <div class="box"><h2>威胁预判（前 6）</h2><div id="threats" class="muted">等待数据…</div></div>
  <div class="box"><h2>运行日志</h2><div id="log"></div></div>
</div>
<div id="msg" class="muted"></div>
<script>
async function act(u){
  const r=await fetch(u);const d=await r.json();
  document.getElementById('msg').textContent=(d.msg||'')+(d.note?' ｜ '+d.note:'');
  st();
}
async function st(){
  const r=await fetch('/api/game/state');const d=await r.json();
  const run=document.getElementById('run');
  run.textContent=d.running?'运行中':'已停止';
  run.className=d.running?'ok':'muted';
  document.getElementById('mode').textContent=d.mode_text;
  document.getElementById('game').textContent=d.game;
  document.getElementById('at').textContent=d.started||'—';
  const s=await fetch('/api/status');const x=await s.json();
  document.getElementById('round').textContent=x.round;
  document.getElementById('deaths').textContent=x.deaths;
  document.getElementById('decision').textContent=x.decision+' / '+x.mindset;
  document.getElementById('kb').textContent=x.kb_count+' 篇';
  document.getElementById('threats').innerHTML=x.threats.map(t=>
    '<div class="thr"><span>'+(t.name||t.cat)+'</span><span class="muted">威胁 '+t.threat+'</span></div>'
  ).join('')||'<div class="muted">暂无数据</div>';
  document.getElementById('log').innerHTML=x.log.slice(0,12).map(l=>'<div class="logline">'+l+'</div>').join('')
    ||'<div class="muted">暂无日志</div>';
}
st();setInterval(st,3000);
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)

        if path == "/api/status":
            return self._json(_status())

        if path == "/api/game/state":
            return self._json({
                "running": _game_running(),
                "mode": GAME_PROC.get("mode"),
                "started": GAME_PROC.get("started"),
                "game": config.get("agent.game", "florr"),
                "profiles": _profiles(),
                "mode_text": (config.runtime_mode_text()
                              if hasattr(config, "runtime_mode_text") else "-"),
            })

        if path == "/static":
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.end_headers()
            return self.wfile.write(SHARED_CSS.encode("utf-8"))

        if path in ("/api/game/start", "/api/game/stop", "/api/game/switch"):
            if not _local_only(self):
                return self._json({"msg": "仅允许本机访问控制接口"}, 403)
            if path == "/api/game/start":
                try:
                    rounds = int((q.get("rounds") or ["0"])[0])
                except ValueError:
                    rounds = 0
                dry = (q.get("dry") or ["1"])[0] not in ("0", "false", "no")
                msg = _start_game(rounds=rounds, dry=dry)
            elif path == "/api/game/stop":
                msg = _stop_game()
            else:
                msg = _switch_game((q.get("name") or [""])[0])
            return self._json({"msg": msg, "note": "dry-run 不做真实键鼠操作"})

        if path == "/game":
            return self._html(GAME_PAGE)
        if path == "/settings":
            return self._html(SETTINGS_PAGE)
        return self._html(PAGE)

    def log_message(self, *a):
        pass  # 不打印每次访问，保持日志干净


if __name__ == "__main__":
    print(f"✅ 监控大盘: http://127.0.0.1:{PANEL_PORT}  (Ctrl+C 退出)")
    ThreadingHTTPServer(("0.0.0.0", PANEL_PORT), Handler).serve_forever()