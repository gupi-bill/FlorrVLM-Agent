#!/usr/bin/env python3
"""
内置使用手册测试  tests/test_mcp_guide.py
========================================
外部 Agent 第一次连进来时，靠 ugf_guide 自学怎么用。
这里保证手册不写死、不漂移、不缺项。
"""
import os
import unittest

os.environ.setdefault("UGF_DRY_RUN", "1")

import mcp_server  # noqa: E402  （conftest 已注入项目根与无头 stub）

EXPECTED = {
    "kb_list", "kb_search", "kb_write", "kb_append", "kb_export", "kb_import",
    "perceive_game", "predict_all_entities", "reset_predictor",
    "game_action", "switch_set", "handle_afk",
    "query_boss_history", "clean_cache", "switch_tactic", "ugf_guide",
}


class TestUgfGuide(unittest.TestCase):

    def test_runtime_tools_match_expected(self):
        names = {n for n, _ in mcp_server._runtime_tools()}
        self.assertEqual(names, EXPECTED, "运行时工具清单与预期不一致（漏注册或改名）")

    def test_guide_lists_every_tool(self):
        g = mcp_server.ugf_guide("all")
        for name in EXPECTED:
            self.assertIn(name, g, f"手册里缺工具 {name}")

    def test_guide_has_chains_and_notes(self):
        g = mcp_server.ugf_guide("all")
        self.assertIn("perceive_game", g)
        self.assertIn("predict_all_entities", g)
        self.assertIn("game_action", g)
        self.assertIn("dry-run", g)

    def test_sections(self):
        for sec in ("quick", "tools", "chains", "notes"):
            self.assertTrue(mcp_server.ugf_guide(sec).strip(), f"{sec} 章节为空")
        self.assertTrue(mcp_server.ugf_guide().strip(), "默认章节(all)不应为空")

    def test_unknown_section_readable(self):
        out = mcp_server.ugf_guide("不存在的章节")
        self.assertIn("未知章节", out)
        self.assertNotIn("Traceback", out)

    def test_guide_not_huge(self):
        # 手册要能被外部模型低成本读完
        self.assertLess(len(mcp_server.ugf_guide("all")), 6000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
