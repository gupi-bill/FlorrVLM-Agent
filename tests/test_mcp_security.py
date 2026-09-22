#!/usr/bin/env python3
"""
安全边界测试  tests/test_mcp_security.py
========================================
威胁模型变了：现在调用方是「别的 Agent」，它可能拼错参数、也可能被注入恶意参数。
所以每个工具都必须：越界拒绝、dry-run 下绝不碰真实键鼠、出错给可读文本而不是 traceback。
"""
import os
import sys
import unittest

os.environ["UGF_DRY_RUN"] = "1"  # 安全测试必须在 dry-run 下进行

import mcp_server  # noqa: E402

TRAVERSAL = ["../../evil.md", "../evil.md", "..", "/etc/passwd",
             "a/b/../../evil.md", "..\\evil.md"]
BAD_INPUTS = ["", "   ", "None", "null", "../../../", "\x00evil", "%2e%2e/evil"]

KB_DIR = os.path.normpath(mcp_server.KB_DIR)          # 以服务端实际使用的目录为准
PROJECT_DIR = os.path.dirname(KB_DIR)
OUTSIDE_DIR = os.path.dirname(PROJECT_DIR)


def _contained(path_text: str) -> bool:
    """从返回文本里抠出路径，判断它是否仍在知识库目录内。"""
    import re
    m = re.search(r":\s*(/.*?\.md)", path_text)
    if not m:
        return True  # 没写成功（返回错误文本），自然没有越界
    p = os.path.normpath(m.group(1))
    try:
        return os.path.commonpath([p, KB_DIR]) == KB_DIR
    except ValueError:
        return False


class TestPathTraversal(unittest.TestCase):
    """知识库读写绝不能写到项目目录之外（要么拒绝，要么把路径清洗回库内）。"""

    def test_kb_write_never_escapes(self):
        for bad in TRAVERSAL:
            out = mcp_server.kb_write(filename=bad, markdown_content="x", game_name="t")
            self.assertIsInstance(out, str)
            self.assertNotIn("Traceback", out)
            self.assertTrue(_contained(out), f"{bad!r} 越界了: {out}")
        self.assertFalse(os.path.exists(os.path.join(PROJECT_DIR, "evil.md")))
        self.assertFalse(os.path.exists(os.path.join(OUTSIDE_DIR, "evil.md")))

    def test_kb_append_never_escapes(self):
        for bad in TRAVERSAL:
            out = mcp_server.kb_append(filename=bad, markdown_content="x", game_name="t")
            self.assertNotIn("Traceback", out)
            self.assertTrue(_contained(out), f"{bad!r} 越界了: {out}")
        self.assertFalse(os.path.exists(os.path.join(PROJECT_DIR, "evil.md")))

    def test_kb_search_game_name_traversal_never_escapes(self):
        for bad in ["..", "../../", "/etc"]:
            out = mcp_server.kb_search(keyword="x", game_name=bad)
            self.assertIsInstance(out, str)
            self.assertNotIn("/etc/passwd", out)

    def test_switch_tactic_rejects_traversal(self):
        for bad in ["../../evil.md", "/etc/passwd", ".."]:
            out = mcp_server.switch_tactic(tactic_file=bad)
            self.assertNotIn("Traceback", out)
            self.assertTrue(("错误" in out) or ("没有这份" in out) or ("非法" in out),
                            f"{bad!r} 被放行: {out}")


class TestDryRunNeverTouchesRealInput(unittest.TestCase):
    """dry-run 下不得 import/调用 pyautogui。"""

    def setUp(self):
        self.called = []
        # 一旦有人真的去操作键鼠，这里立刻炸
        sys.modules["pyautogui"].moveTo = lambda *a, **k: self.called.append("moveTo")
        sys.modules["pyautogui"].press = lambda *a, **k: self.called.append("press")
        sys.modules["pyautogui"].keyDown = lambda *a, **k: self.called.append("keyDown")
        sys.modules["pyautogui"].keyUp = lambda *a, **k: self.called.append("keyUp")

    def test_game_action_no_real_input(self):
        for act in ("attack", "defend", "synthesize", "idle"):
            mcp_server.game_action(action_type=act)
        mcp_server.game_action(action_type="move", x=100, y=200)
        self.assertEqual(self.called, [], f"dry-run 下竟然动了键鼠: {self.called}")

    def test_switch_set_no_real_input(self):
        mcp_server.switch_set(set_name="combat")
        self.assertEqual(self.called, [], f"dry-run 下竟然按了键: {self.called}")


class TestReadableErrors(unittest.TestCase):
    """返回给外部 Agent 的东西必须能读懂，不能是 traceback。"""

    def test_no_traceback_on_bad_input(self):
        calls = [
            lambda: mcp_server.game_action(action_type="not-an-action"),
            lambda: mcp_server.game_action(action_type="move"),          # 缺坐标
            lambda: mcp_server.switch_set(set_name="no-such-set"),
            lambda: mcp_server.switch_tactic(tactic_file="nope.md"),
            lambda: mcp_server.clean_cache(target="weird"),
            lambda: mcp_server.kb_write(filename="", markdown_content="x"),
            lambda: mcp_server.ugf_guide(section="no-such-section"),
            lambda: mcp_server.kb_import(backup_path="/nonexistent/path.tar.gz"),
        ]
        for fn in calls:
            try:
                out = fn()
            except Exception as e:  # 工具不该把异常抛给调用方
                self.fail(f"{fn} 抛出了异常: {type(e).__name__}: {e}")
            self.assertIsInstance(out, str)
            self.assertNotIn("Traceback", out)

    def test_unknown_action_lists_options(self):
        out = mcp_server.game_action(action_type="fly")
        self.assertIn("可选", out, "未知动作应提示可选值")


if __name__ == "__main__":
    unittest.main(verbosity=2)
