#!/usr/bin/env python3
"""
传输一致性测试  tests/test_mcp_transport.py
==========================================
stdio 是默认传输；streamable-http 用于多客户端同时接入。
这里保证：HTTP 传输下拿到的工具清单与 stdio 下完全一致（16 个，不多不少）。
"""
import json
import os
import socket
import subprocess
import sys
import time
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(BASE, "mcp_server.py")

EXPECTED = {
    "kb_list", "kb_search", "kb_write", "kb_append", "kb_export", "kb_import",
    "perceive_game", "predict_all_entities", "reset_predictor",
    "game_action", "switch_set", "handle_afk",
    "query_boss_history", "clean_cache", "switch_tactic", "ugf_guide",
}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _sse_payload(text: str):
    """从响应里取出 JSON 结果：优先解析 SSE 的 data 块，否则按纯 JSON 解析。"""
    out = None
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                out = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
    if out is not None:
        return out
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


class TestStreamableHttp(unittest.TestCase):
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        env = dict(os.environ, UGF_DRY_RUN="1", PYTHONUNBUFFERED="1")
        cls.proc = subprocess.Popen(
            [sys.executable, SERVER, "--transport", "streamable-http",
             "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=BASE, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        # 等服务起来（最多 20 秒）
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", cls.port), 0.5):
                    break
            except OSError:
                if cls.proc.poll() is not None:
                    raise RuntimeError("服务进程提前退出")
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        if cls.proc and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    def _post(self, payload, session=None):
        import requests
        url = f"http://127.0.0.1:{self.port}/mcp"
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if session:
            headers["mcp-session-id"] = session
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        # text/event-stream 没带 charset，requests 会按 latin-1 猜，中文会乱码
        r.encoding = "utf-8"
        return r

    def _handshake(self):
        """initialize + notifications/initialized，缺后一步服务端会拒绝后续调用。"""
        r = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "0"}}})
        self.assertEqual(r.status_code, 200)
        session = r.headers.get("mcp-session-id")
        self.assertTrue(session, "streamable-http 必须返回 mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                   session=session)
        return session

    def test_initialize_and_tools_list(self):
        session = self._handshake()
        r2 = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                        session=session)
        self.assertEqual(r2.status_code, 200)
        data = _sse_payload(r2.text)
        names = {t["name"] for t in data.get("result", {}).get("tools", [])}
        self.assertEqual(names, EXPECTED, "HTTP 传输下的工具清单与预期不一致")

    def test_guide_callable_over_http(self):
        session = self._handshake()
        r2 = self._post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "ugf_guide", "arguments": {"section": "quick"}}},
                        session=session)
        self.assertEqual(r2.status_code, 200)
        data = _sse_payload(r2.text)
        text = json.dumps(data, ensure_ascii=False)
        self.assertIn("Universal-Game-Framework", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
