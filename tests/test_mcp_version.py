#!/usr/bin/env python3
"""
版本与清单一致性测试  tests/test_mcp_version.py
==============================================
别人升级 / 回滚时，版本号和「有哪些工具」必须一眼可查且互相一致。
"""
import os
import re
import subprocess
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(BASE, "mcp_server.py")
os.environ.setdefault("UGF_DRY_RUN", "1")

import mcp_server  # noqa: E402


class TestVersion(unittest.TestCase):

    def test_version_format(self):
        self.assertRegex(mcp_server.VERSION, r"^\d+\.\d+\.\d+(-[\w.]+)?$",
                         "版本号应为 x.y.z 或 x.y.z-后缀")

    def test_cli_version_matches_constant(self):
        r = subprocess.run([sys.executable, SERVER, "--version"],
                           capture_output=True, text=True, cwd=BASE, timeout=120)  # 冷启动要加载 mcp/numpy，慢机器上可达十几秒
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(mcp_server.VERSION, r.stdout)

    def test_changelog_mentions_current_version(self):
        path = os.path.join(BASE, "CHANGELOG.md")
        self.assertTrue(os.path.exists(path), "缺少 CHANGELOG.md")
        text = open(path, encoding="utf-8").read()
        self.assertIn(mcp_server.VERSION, text, "CHANGELOG 里没有当前版本条目")

    def test_install_doc_exists(self):
        for rel in ("docs/MCP_INSTALL.md", "docs/MCP_EXAMPLES.md"):
            self.assertTrue(os.path.exists(os.path.join(BASE, rel)), f"缺少 {rel}")


class TestToolListDocConsistency(unittest.TestCase):
    """README 的工具表格写了几个，运行时就得有几个（防止改名后文档说谎）。"""

    def test_readme_table_matches_runtime(self):
        readme = open(os.path.join(BASE, "README.md"), encoding="utf-8").read()
        runtime = {n for n, _ in mcp_server._runtime_tools()}
        missing = [n for n in runtime if f"`{n}`" not in readme]
        self.assertEqual(missing, [], f"README 工具表里缺少: {missing}")

    def test_install_doc_mentions_guide(self):
        doc = open(os.path.join(BASE, "docs/MCP_INSTALL.md"), encoding="utf-8").read()
        self.assertIn("ugf_guide", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
