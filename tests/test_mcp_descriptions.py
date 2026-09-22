#!/usr/bin/env python3
"""
MCP 工具描述契约测试  tests/test_mcp_descriptions.py
==================================================
本项目的消费方是「别的 LLM」——它只看得到工具名 + 描述 + 入参 schema。
所以描述必须自检：够长、说清返回什么、不泄漏内部绝对路径。
"""
import ast
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(BASE, "mcp_server.py")

MIN_LEN = 80
FORBIDDEN = ("/home/", "/Users/", "C:\\\\", "/opt/")


def _tools():
    src = open(SERVER, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and \
           any("mcp.tool" in ast.unparse(d) for d in n.decorator_list):
            out[n.name] = ast.get_docstring(n) or ""
    return out


class TestMcpDescriptions(unittest.TestCase):

    def setUp(self):
        self.tools = _tools()

    def test_tool_count(self):
        self.assertEqual(len(self.tools), 16, "工具数量应为 16")

    def test_every_tool_has_description(self):
        for name, doc in self.tools.items():
            self.assertTrue(doc.strip(), f"{name} 缺少描述")

    def test_description_long_enough(self):
        for name, doc in self.tools.items():
            self.assertGreaterEqual(
                len(doc.strip()), MIN_LEN,
                f"{name} 描述过短（{len(doc)} < {MIN_LEN}），外部模型看不懂")

    def test_description_mentions_return(self):
        for name, doc in self.tools.items():
            self.assertIn("返回", doc, f"{name} 描述没写清「返回」什么")

    def test_no_internal_path_leak(self):
        for name, doc in self.tools.items():
            for bad in FORBIDDEN:
                self.assertNotIn(bad, doc, f"{name} 描述里泄漏了内部路径 {bad}")

    def test_server_still_importable(self):
        # 替换 docstring 很容易写坏语法，这里用编译兜底
        src = open(SERVER, encoding="utf-8").read()
        compile(src, SERVER, "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
