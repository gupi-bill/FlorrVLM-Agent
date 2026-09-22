#!/usr/bin/env python3
"""
tools/install_mcp.py 的契约测试  tests/test_install_mcp.py
========================================================
覆盖：--list 能跑、--dry-run 不落盘、真实写入/覆盖/卸载、custom 目标、未知目标拒绝。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE, "tools", "install_mcp.py")


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=BASE)


class TestInstallMcp(unittest.TestCase):

    def test_list_ok(self):
        r = run("--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("workbuddy", r.stdout)

    def test_unknown_target_rejected(self):
        r = run("--target", "no-such-client")
        self.assertEqual(r.returncode, 2)
        self.assertIn("未知目标", r.stdout + r.stderr)

    def test_custom_requires_path(self):
        r = run("--target", "custom")
        self.assertEqual(r.returncode, 2)

    def test_custom_dryrun_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mcp.json")
            r = run("--target", "custom", "--path", p, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(os.path.exists(p), "dry-run 不应落盘")
            self.assertIn("ugf", r.stdout)

    def test_custom_write_then_remove(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mcp.json")
            # 预置一条别人的服务，验证是「合并」而不是覆盖
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"mcpServers": {"other": {"command": "x"}}}, f)

            r = run("--target", "custom", "--path", p)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.load(open(p, encoding="utf-8"))
            self.assertIn("other", data["mcpServers"], "不能覆盖已有服务")
            self.assertIn("ugf", data["mcpServers"])
            entry = data["mcpServers"]["ugf"]
            self.assertEqual(entry["env"]["UGF_DRY_RUN"], "1", "默认必须 dry-run")
            self.assertTrue(entry["args"][0].endswith("mcp_server.py"))
            self.assertTrue(os.path.exists(entry["args"][0]))

            r2 = run("--target", "custom", "--path", p, "--remove")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            data2 = json.load(open(p, encoding="utf-8"))
            self.assertNotIn("ugf", data2["mcpServers"])
            self.assertIn("other", data2["mcpServers"])

    def test_online_flag_sets_dryrun_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "mcp.json")
            run("--target", "custom", "--path", p)
            data = json.load(open(p, encoding="utf-8"))
            self.assertEqual(data["mcpServers"]["ugf"]["env"]["UGF_DRY_RUN"], "1")
            run("--target", "custom", "--path", p, "--online")
            data = json.load(open(p, encoding="utf-8"))
            self.assertEqual(data["mcpServers"]["ugf"]["env"]["UGF_DRY_RUN"], "0")

    def test_toml_target_gives_guidance_only(self):
        r = run("--target", "codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("mcp_servers.ugf", r.stdout)

    def test_mcp_install_doc_exists_and_mentions_installer(self):
        doc = os.path.join(BASE, "docs", "MCP_INSTALL.md")
        self.assertTrue(os.path.exists(doc), "缺少 docs/MCP_INSTALL.md")
        text = open(doc, encoding="utf-8").read()
        self.assertIn("install_mcp.py", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
