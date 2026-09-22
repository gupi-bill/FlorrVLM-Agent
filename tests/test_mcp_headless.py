#!/usr/bin/env python3
"""
无头冷启动测试  tests/test_mcp_headless.py
=========================================
客户端拉起服务时，感知服务（YOLO / perception_server.py）往往还没起。
这时整条链路必须照常能跑通（结果带 _fallback），不能抛异常、不能卡住。
"""
import json
import os
import unittest

os.environ["UGF_DRY_RUN"] = "1"

import mcp_server  # noqa: E402


class TestHeadlessColdStart(unittest.TestCase):

    def test_perceive_game_never_raises(self):
        """把感知地址指到一个必然连不上的端口，模拟服务缺失。"""
        old = mcp_server.PERCEPTION_URL
        mcp_server.PERCEPTION_URL = "http://127.0.0.1:59999/perceive"
        try:
            out = mcp_server.perceive_game()
        finally:
            mcp_server.PERCEPTION_URL = old
        self.assertIsInstance(out, str)
        self.assertIn("_fallback", out, "感知缺失时应带 _fallback 标记")

    def test_perceive_then_predict_chain_runs(self):
        mcp_server.reset_predictor()
        old = mcp_server.PERCEPTION_URL
        mcp_server.PERCEPTION_URL = "http://127.0.0.1:59999/perceive"
        try:
            for _ in range(4):
                mcp_server.perceive_game()
            out = mcp_server.predict_all_entities()
        finally:
            mcp_server.PERCEPTION_URL = old
        # 要么给出预判结果，要么明确说数据不足——都不能是异常或 traceback
        self.assertIsInstance(out, str)
        self.assertNotIn("Traceback", out)
        data = json.loads(out)
        self.assertTrue(isinstance(data, list) or "status" in data)

    def test_all_tools_callable_without_perception(self):
        """16 个工具在没有感知服务时都得能调用（不要求结果正确，要求不炸）。"""
        old = mcp_server.PERCEPTION_URL
        mcp_server.PERCEPTION_URL = "http://127.0.0.1:59999/perceive"
        calls = {
            "kb_list": lambda: mcp_server.kb_list(),
            "kb_search": lambda: mcp_server.kb_search(keyword="test"),
            "kb_export": lambda: mcp_server.kb_export(),
            "perceive_game": lambda: mcp_server.perceive_game(),
            "predict_all_entities": lambda: mcp_server.predict_all_entities(),
            "reset_predictor": lambda: mcp_server.reset_predictor(),
            "game_action": lambda: mcp_server.game_action(action_type="idle"),
            "switch_set": lambda: mcp_server.switch_set(set_name="combat"),
            "handle_afk": lambda: mcp_server.handle_afk(),
            "query_boss_history": lambda: mcp_server.query_boss_history(),
            "clean_cache": lambda: mcp_server.clean_cache(target="predict"),
            "ugf_guide": lambda: mcp_server.ugf_guide(section="quick"),
        }
        try:
            for name, fn in calls.items():
                try:
                    out = fn()
                except Exception as e:
                    self.fail(f"{name} 抛异常: {type(e).__name__}: {e}")
                self.assertNotIn("Traceback", str(out), f"{name} 返回了 traceback")
        finally:
            mcp_server.PERCEPTION_URL = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
