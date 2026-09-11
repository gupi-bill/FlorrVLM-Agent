#!/usr/bin/env python3
"""
FlorrVLM-Agent 可视化监控大盘 admin_panel.py  (v1.1)
=====================================================
浏览器打开 http://127.0.0.1:5002 即可实时查看：
- 指标卡片：当前游戏 / 会话状态 / 本局回合数 / 累计死亡 / 知识库规模 / 时间
- BOSS 威胁面板：最近一次预判出的威胁实体(来自 run_logs/agent_snapshot.json)
- 决策信息：当前 decision / mindset / 推荐套装
- 日志面板：run_logs/ 当天尾部(倒序自动滚动)
- 资源占用：进程 CPU / 内存（有 psutil 用 psutil，否则回退 /proc）
- 感知依赖：读不到快照时页面显示红色告警，而不是空白

只读，不修改任何文件。纯标准库（psutil 可选）。
"""
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config

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


def _status() -> dict:
    snap = _snapshot()
    st = _state()
    kb = _kb_info()
    res = _resources()
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
    }


PAGE = """<!DOCTYPE html><html lang="zh"><meta charset="utf-8">
<title>FlorrVLM-Agent 监控大盘</title>
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
 @media(max-width:700px){.row{grid-template-columns:1fr}}
</style>
<h1>FlorrVLM-Agent 监控大盘</h1>
<div class="sub" id="time">加载中…</div>
<div class="banner" id="banner">⚠ 未检测到 Agent 运行快照（可能还没 `play`，或感知服务未启动）</div>
<div class="grid">
  <div class="card"><div class="lab">游戏</div><div class="val" id="game">—</div></div>
  <div class="card"><div class="lab">状态</div><div class="val" id="status">—</div></div>
  <div class="card"><div class="lab">回合数</div><div class="val ok" id="round">—</div></div>
  <div class="card"><div class="lab">累计死亡</div><div class="val warn" id="deaths">—</div></div>
  <div class="card"><div class="lab">知识库</div><div class="val" id="kb">—</div></div>
  <div class="card"><div class="lab">CPU / 内存</div><div class="val" id="res">—</div></div>
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
  document.getElementById('threats').innerHTML=d.threats.map(t=>
    '<div class="thr"><span><span class="dot '+ (CAT[t.cat]||'c-normal') +'"></span>'
    +(t.name||t.cat)+'</span><span class="muted">威胁 '+t.threat+'　('+t.x+', '+t.y+')</span></div>'
  ).join('')||'<div class="muted">暂无威胁数据</div>';
  document.getElementById('decision').innerHTML=(d.decision?'决策 <b>'+d.decision+'</b> · 心态 '+d.mindset+' · 推荐套装 '+d.set:'<span class="muted">—</span>');
  document.getElementById('log').innerHTML=d.log.map(l=>'<div class="logline">'+l+'</div>').join('')||'<div class="muted">暂无日志</div>';
}
refresh();setInterval(refresh,3000);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(_status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):
        pass  # 不打印每次访问，保持日志干净


if __name__ == "__main__":
    print(f"✅ 监控大盘: http://127.0.0.1:{PANEL_PORT}  (Ctrl+C 退出)")
    ThreadingHTTPServer(("0.0.0.0", PANEL_PORT), Handler).serve_forever()