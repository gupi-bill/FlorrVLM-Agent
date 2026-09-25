# -*- coding: utf-8 -*-
"""S27 · 知识闭环 A/B 实验器（离线单测）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import knowledge_loop  # noqa: E402
import tools.kb_ab_experiment as ab  # noqa: E402


def test_dangerous_filter():
    assert ab.is_dangerous("retreat", 1.0, 0.0)
    assert ab.is_dangerous("cautious_fight", 0.3, 0.5)      # 低血量
    assert ab.is_dangerous("fight", 1.0, 1.5)               # 高威胁
    assert not ab.is_dangerous("fight", 1.0, 0.5)           # 安全局面


def test_learned_shifts_to_defend():
    # 危险 cautious_fight：无知识 attack，有知识 defend
    assert ab.fallthrough_action("cautious_fight") == "attack"
    assert ab.learned_action("cautious_fight", 0.3, 1.5) == "defend"


def test_safe_situation_unchanged():
    # 安全局面：知识不生效，两组一致（都 attack）
    assert ab.learned_action("fight", 1.0, 0.5) == ab.fallthrough_action("fight")


def test_ab_significant():
    base, learn, rows = ab.run_ab()
    assert len(base) == len(learn) > 0
    diff, lo, hi = ab.bootstrap_diff_ci(base, learn, n=500)
    assert diff > 0
    assert lo > 0  # 显著为正
