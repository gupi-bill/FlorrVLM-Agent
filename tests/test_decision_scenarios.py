"""S20 决策场景矩阵：战斗 / 组队 / 心态 / 边界。

决策层不能只靠单测覆盖数学，要覆盖「局面」。本文件按 PLAN_PHASE2 S20 构造
场景矩阵，对每个场景断言决策结果、推荐套装、心态档位；并覆盖 S18 遗留①
（知识优先级过硬）引入的知识闸门。

场景表实测值同步写入 devplan/SCENARIOS_S20.md。
"""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combat_judge
import knowledge_loop


# ---------------------------------------------------------------------------
# 场景构造器
# ---------------------------------------------------------------------------
def enemy(raw_id="e1", category="normal", x=100.0, y=100.0):
    return {"raw_id": raw_id, "category": category, "x_now": x, "y_now": y,
            "rarity": "Common"}


def make_ctx(hp=100.0, max_hp=100.0, power=100.0, enemies=None, teammates=None,
             current_set=None):
    return combat_judge.CombatContext(
        player=combat_judge.PlayerState(
            hp=hp, max_hp=max_hp, power_score=power,
            current_set=current_set or combat_judge.SET_COMBAT),
        enemies=enemies or [],
        teammates=teammates or [],
    )


def decide(**kw):
    return combat_judge.judge_combat(make_ctx(**kw))


# ---------------------------------------------------------------------------
# 1. 战斗场景
# ---------------------------------------------------------------------------
def test_scenario_fair_fight():
    """势均力敌的普通怪 → 该打就打。"""
    r = decide(power=100, enemies=[enemy(category="normal")])
    assert r["decision"] == combat_judge.DECISION_FIGHT
    assert r["recommended_set"] == combat_judge.SET_COMBAT


def test_scenario_outnumbered():
    """以少打多：一群普通怪叠加后威胁超过自身 → 撤退。"""
    r = decide(power=50, enemies=[enemy(f"e{i}", "normal") for i in range(12)])
    assert r["decision"] == combat_judge.DECISION_RETREAT
    assert r["recommended_set"] == combat_judge.SET_RETREAT
    assert "远超自身实力" in r["retreat_reason"]


def test_scenario_surrounded():
    """被包围：四面八方都有敌人（不同坐标）→ 至少不能是激进强攻。"""
    around = [enemy(f"e{i}", "elite", x=100 + i * 300, y=200 if i % 2 else 800)
              for i in range(4)]
    r = decide(power=60, enemies=around)
    assert r["decision"] in (combat_judge.DECISION_CAUTIOUS,
                             combat_judge.DECISION_RETREAT)


def test_scenario_low_hp_changes_mindset_effect():
    """血量极低 + 保守心态 → 战斗决策降级为谨慎。"""
    ctx = make_ctx(hp=10, max_hp=100, power=100,
                   enemies=[enemy(category="boss")] * 3)
    r = combat_judge.judge_combat(ctx)
    assert r["mindset"] == combat_judge.MINDSET_CONSERVATIVE
    assert r["decision"] != combat_judge.DECISION_FIGHT


def test_scenario_highest_boss_overpowered():
    """highest_boss + 实力不足 → 全力避险，套装换 retreat。"""
    r = decide(power=100, enemies=[enemy("boss1", "highest_boss")])
    assert r["has_highest_boss"] is True
    assert r["decision"] == combat_judge.DECISION_RETREAT
    assert r["recommended_set"] == combat_judge.SET_RETREAT


def test_scenario_highest_boss_strong_player():
    """highest_boss 但实力充足 → 谨慎周旋而非逃命。"""
    r = decide(power=100000, enemies=[enemy("boss1", "highest_boss")])
    assert r["decision"] == combat_judge.DECISION_CAUTIOUS
    assert r["recommended_set"] in (combat_judge.SET_TANK, combat_judge.SET_COMBAT)


def test_scenario_elite_chase_set():
    """普通威胁 + 场上有精英 → 追击套。"""
    r = decide(power=5000, enemies=[enemy("e1", "elite")])
    assert r["decision"] == combat_judge.DECISION_FIGHT
    assert r["recommended_set"] == combat_judge.SET_CHASE


# ---------------------------------------------------------------------------
# 2. 组队友军
# ---------------------------------------------------------------------------
def test_scenario_team_output_ally():
    """队友是输出型（combat）→ 自身转辅助/抗伤更合理。"""
    r = decide(power=100, enemies=[enemy(category="normal")],
               teammates=[combat_judge.Teammate(raw_id="t1",
                                                petal_set=combat_judge.SET_COMBAT)])
    assert r["decision"] == combat_judge.DECISION_FIGHT
    assert r["recommended_set"] in (combat_judge.SET_TEAM_SUPPORT, combat_judge.SET_TANK,
                                    combat_judge.SET_COMBAT)


def test_scenario_team_tank_ally():
    """队友是抗伤型（tank）→ 自身该打输出。"""
    r = decide(power=100, enemies=[enemy(category="normal")],
               teammates=[combat_judge.Teammate(raw_id="t1",
                                                petal_set=combat_judge.SET_TANK)])
    assert r["recommended_set"] != combat_judge.SET_TANK


def test_scenario_retreat_outranks_team_adjust():
    """回归：跑路优先级高于组队协同，套装不能被队友配置覆盖成辅助套。"""
    r = decide(power=30, enemies=[enemy(f"e{i}", "normal") for i in range(10)],
               teammates=[combat_judge.Teammate(raw_id="t1",
                                                petal_set=combat_judge.SET_COMBAT)])
    assert r["decision"] == combat_judge.DECISION_RETREAT
    assert r["recommended_set"] == combat_judge.SET_RETREAT


def test_scenario_empty_teammates_list_is_noop():
    r = decide(power=100, enemies=[enemy(category="normal")], teammates=[])
    assert r["recommended_set"] == combat_judge.SET_COMBAT


# ---------------------------------------------------------------------------
# 3. 心态档位
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("category,power,expected", [
    ("normal", 100000, combat_judge.MINDSET_AGGRESSIVE),
    ("normal", 50, combat_judge.MINDSET_BALANCED),
    ("elite", 100000, combat_judge.MINDSET_AGGRESSIVE),
    ("boss", 100000, combat_judge.MINDSET_AGGRESSIVE),
    ("boss", 100, combat_judge.MINDSET_CONSERVATIVE),
    ("highest_boss", 100, combat_judge.MINDSET_CONSERVATIVE),
])
def test_mindset_matrix(category, power, expected):
    ctx = make_ctx(power=power, enemies=[enemy(category=category)])
    assert combat_judge.decide_mindset(ctx) == expected


def test_mindset_no_enemy_is_balanced():
    assert combat_judge.decide_mindset(make_ctx()) == combat_judge.MINDSET_BALANCED


# ---------------------------------------------------------------------------
# 4. 边界与脏数据
# ---------------------------------------------------------------------------
def test_scenario_no_enemies():
    r = decide(power=100, enemies=[])
    assert r["decision"] == combat_judge.DECISION_FIGHT
    assert r["enemy_threat"] == 0.0
    assert r["threat_ratio"] == 0.0


def test_scenario_zero_power():
    """实力为 0（感知未就绪）→ 威胁比取极大值，不能直接崩。"""
    r = decide(power=0, enemies=[enemy()])
    assert r["threat_ratio"] == 999.0
    assert r["decision"] == combat_judge.DECISION_RETREAT


def test_scenario_all_nan_coords():
    """坐标全 NaN：不能让 NaN 污染决策链。"""
    e = {"raw_id": "n1", "category": "normal",
         "x_now": float("nan"), "y_now": float("nan")}
    r = decide(power=100, enemies=[e])
    assert not math.isnan(r["threat_ratio"])
    assert r["decision"] in (combat_judge.DECISION_FIGHT,
                             combat_judge.DECISION_CAUTIOUS,
                             combat_judge.DECISION_RETREAT)


def test_scenario_nan_hp():
    p = combat_judge.PlayerState(hp=float("nan"), max_hp=float("nan"),
                                 power_score=100)
    ctx = combat_judge.CombatContext(player=p, enemies=[enemy()])
    r = combat_judge.judge_combat(ctx)
    assert not math.isnan(r["threat_ratio"])


def test_scenario_entities_burst_and_drop():
    """实体突增突减：决策必须单调跟随威胁变化，不能滞后或反向。"""
    few = decide(power=100, enemies=[enemy("e1", "normal")])
    many = decide(power=100, enemies=[enemy(f"e{i}", "normal") for i in range(15)])
    rank = {combat_judge.DECISION_FIGHT: 0,
            combat_judge.DECISION_CAUTIOUS: 1,
            combat_judge.DECISION_RETREAT: 2}
    assert rank[many["decision"]] >= rank[few["decision"]]
    # 威胁回落后应能回到进攻
    assert decide(power=100000, enemies=[])["decision"] == combat_judge.DECISION_FIGHT


def test_scenario_jitter_entities_same_position():
    """超高频抖动：同一批实体重复出现不应改变结论（决策是纯函数）。"""
    es = [enemy(f"e{i}", "normal", x=500.0, y=500.0) for i in range(3)]
    a = decide(power=100, enemies=es)
    b = decide(power=100, enemies=list(es))
    assert a == b


def test_scenario_unknown_category():
    r = decide(power=100, enemies=[enemy(category="不存在的档位")])
    assert r["enemy_threat"] >= 0


# ---------------------------------------------------------------------------
# 5. 知识闸门（S18 遗留①）
# ---------------------------------------------------------------------------
TACTICS = ["retreat", "keep_distance"]


def test_gate_blocks_empty_field():
    """空场：知识里写了撤退也不该一路防守（S18 实测 14 轮全 defend 的修复）。"""
    assert knowledge_loop.knowledge_gate("cautious_fight", TACTICS,
                                         hp_ratio=1.0, threat_ratio=0.0) is False
    assert knowledge_loop.decide_action("cautious_fight", TACTICS,
                                        hp_ratio=1.0, threat_ratio=0.0) == ""


def test_gate_allows_low_hp():
    assert knowledge_loop.knowledge_gate("cautious_fight", TACTICS,
                                         hp_ratio=0.3, threat_ratio=0.5) is True
    assert knowledge_loop.decide_action("cautious_fight", TACTICS,
                                        hp_ratio=0.3, threat_ratio=0.5) == "defend"


def test_gate_allows_high_threat():
    assert knowledge_loop.knowledge_gate("cautious_fight", TACTICS,
                                         hp_ratio=1.0, threat_ratio=2.0) is True


def test_gate_retreat_always_applies():
    assert knowledge_loop.knowledge_gate("retreat", TACTICS,
                                         hp_ratio=1.0, threat_ratio=0.1) is True


def test_gate_fight_only_when_ahead():
    assert knowledge_loop.knowledge_gate("fight", ["focus_fire"],
                                         threat_ratio=0.4) is True
    assert knowledge_loop.knowledge_gate("fight", ["focus_fire"],
                                         threat_ratio=3.0) is False


def test_gate_no_tactics_is_false():
    assert knowledge_loop.knowledge_gate("retreat", [], threat_ratio=5.0) is False


def test_gate_matrix_is_exhaustive_over_decisions():
    for d in ("fight", "cautious_fight", "retreat", "unknown_decision"):
        v = knowledge_loop.knowledge_gate(d, TACTICS, 1.0, 1.5)
        assert isinstance(v, bool)
    assert knowledge_loop.knowledge_gate("unknown_decision", TACTICS, 1.0, 1.5) is False


# ---------------------------------------------------------------------------
# 6. 端到端：场景 → 动作（含知识）
# ---------------------------------------------------------------------------
def _fallback(state: dict, ev: dict, kb_text: str = ""):
    import agent_main
    return agent_main._fallback_decide(json.dumps(state, ensure_ascii=False),
                                       json.dumps(ev, ensure_ascii=False),
                                       kb_text)


KB_TEXT = "共找到 1 条结果:\n## tactics.md\n- 战术: 低血量立即撤退并保持距离\n"


@pytest.mark.parametrize("hp_ratio,threat,expect_kb", [
    (1.0, 0.0, False),    # 空场满血：不带偏
    (0.2, 2.0, True),     # 残血高威胁：知识生效
    (1.0, 2.0, True),     # 满血但被压：知识生效
    (1.0, 0.5, False),    # 满血优势：不生效
])
def test_end_to_end_scenarios(hp_ratio, threat, expect_kb):
    state = {"afk_popup": False,
             "player": {"hp": 100 * hp_ratio, "max_hp": 100}}
    ev = {"decision": "cautious_fight", "threat_ratio": threat}
    act = _fallback(state, ev, KB_TEXT)
    assert (act.get("source") == "kb") is expect_kb
    assert act["action"] == ("defend" if expect_kb else "attack")


def test_end_to_end_retreat_with_knowledge():
    state = {"afk_popup": False, "player": {"hp": 100, "max_hp": 100}}
    ev = {"decision": "retreat", "threat_ratio": 0.2}
    assert _fallback(state, ev, KB_TEXT) == {"action": "defend", "source": "kb"}


def test_end_to_end_afk_overrides_everything():
    state = {"afk_popup": True, "player": {"hp": 10, "max_hp": 100}}
    ev = {"decision": "retreat", "threat_ratio": 9.0}
    assert _fallback(state, ev, KB_TEXT) == {"action": "idle"}
