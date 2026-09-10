#!/usr/bin/env python3
"""
FlorrVLM-Agent 简易本地面板 admin_panel.py
============================================
浏览器打开 http://127.0.0.1:5002 即可查看：
- 当前状态（进程存活 / 最新日志）
- 知识库概况（文件数 / 各文档标题）
- 运行日志（run_logs/ 当天的尾部）

只读，不修改任何文件。纯标准库，无第三方依赖，占用极小。
"""
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
KB_DIR = os.path.join(BASE_DIR, config.get("paths.knowledge_md", "knowledge_md"))
PANEL_PORT = config.get("server.panel_port", 5002)


def _latest_log_text(n_lines: int = 50) -> str:
    """读当天日志尾部 n 行；无日志返回提示。"""
    today = datetime.now().strftime("%Y%m%d")
    fpath = os.path.join(LOG_DIR, f"agent_{today}.log")
    if not os.path.exists(fpath):
        return "(还没有日志，Agent 主循环启动后自动生成)"
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return "(读取日志失败)"
    return "\n".join(lines[-n_lines:])


def _kb_summary() -> list:
    """列出知识库文档名与开头标题。"""
    if not os.path.isdir(KB_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(KB_DIR)):
        if not fn.endswith(".md"):
            continue
        fp = os.path.join(KB_DIR, fn)
        title = ""
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"):
                        title = line.strip()
                        break
        except OSError:
            pass
        out.append({"file": fn, "title": title, "size": os.path.getsize(fp)})
    return out


def _status() -> dict:
    return {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "log_dir": LOG_DIR,
        "kb_dir": KB_DIR,
        "log_tail": _latest_log_text(),
        "kb_files": _kb_summary(),
    }


PAGE = """<!DOCTYPE html><html lang="zh"><meta charset="utf-8">
<title>FlorrVLM-Agent 面板</title>
<style>
 body{font-family:system-ui;background:#0f1420;color:#e6e8ee;margin:0;padding:20px}
 h1{font-size:18px} h2{font-size:14px;margin-top:22px;color:#7fd0ff}
 pre{background:#161c2b;border:1px solid #2a3348;padding:10px;border-radius:8px;
     white-space:pre-wrap;max-height:260px;overflow:auto;font-size:12px}
 table{border-collapse:collapse;font-size:13px;width:100%}
 td,th{border:1px solid #2a3348;padding:6px 8px;text-align:left}
 .ok{color:#4ade80}.warn{color:#facc15}
</style>
<h1>FlorrVLM-Agent 实时状态</h1>
<p class="ok" id="time">加载中…</p>
<h2>运行日志（当天尾部）</h2><pre id="log">…</pre>
<h2>知识库</h2>
<table><thead><tr><th>文件</th><th>标题</th><th>大小</th></tr></thead>
<tbody id="kb"></tbody></table>
<script>
async function refresh(){
  const r=await fetch('/api/status');const d=await r.json();
  document.getElementById('time').textContent='时间: '+d.time;
  document.getElementById('time').className=d.log_dir?'ok':'warn';
  document.getElementById('log').textContent=d.log_tail;
  document.getElementById('kb').innerHTML=d.kb_files.map(f=>
    '<tr><td>'+f.file+'</td><td>'+f.title+'</td><td>'+f.size+' B</td></tr>').join('')
    ||'<tr><td colspan=3>知识库为空</td></tr>';
}
refresh();setInterval(refresh,3000);
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(_status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
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
    print(f"本地面板: http://127.0.0.1:{PANEL_PORT}")
    HTTPServer(("0.0.0.0", PANEL_PORT), Handler).serve_forever()