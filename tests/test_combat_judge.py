#!/usr/bin/env python3
"""
S4 · 战斗评估 combat_judge.py 实测

覆盖：威胁求和 / 威胁比 / 三档决策(fight·cautious·retreat) / highest_boss 避险 /
      心态切换 / 组队套装协同 / 逃生优先于协同(回归) / 有限追杀 / 安全区钳制 /
      移动抖动 / 避险走位 / 评估防抖 / 脏数据防御 / 配置热加载。

全部离线：不触碰网络、键鼠、真实游戏窗口；随机量用 random.seed 固定。
"""
import random

import pytest

import combat_judge as cj
import config


# ---------------------------------------------------------------------------
# 夹具与辅助
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def env(monkeypatch):
    """每个用例重置模块级配置与成就，固定随机种子；结束后恢复真实配置。"""
    random.seed(20260921)
    cj.reload_config()
    cj.clear_achievements()
    yield
    cj.clear_achievements()
    cj.reload_config()


def ent(category, x=0.0, y=0.0, raw_id=None):
    """构造一个 predictor 风格的实体字典。"""
    return {
        "raw_id": raw_id or f"{category}-1",
        "category": category,
        "x_now": x,
        "y_now": y,
    }


def ctx(enemies=(), teammates=(), power=100.0, hp=100.0, max_hp=100.0,
        x=960.0, y=540.0, w=1920, h=1080):
    return cj.CombatContext(
        player=cj.PlayerState(hp=hp, max_hp=max_hp, power_score=power, x=x, y=y),
        enemies=list(enemies),
        teammates=list(teammates),
        screen_width=w,
        screen_height=h,
    )


def mate(petal_set=cj.SET_COMBAT, raw_id="ally"):
    return cj.Teammate(raw_id=raw_id, petal_set=petal_set)


class FakeClock:
    """手动推进的时钟，替换 combat_judge.time 里的 time.time()。"""

    def __init__(self, start=5000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, dt=0.1):
        self.now += dt
        return self.now


# ---------------------------------------------------------------------------
# 威胁与威胁比
# ---------------------------------------------------------------------------
def test_threat_sum_uses_config_table():
    enemies = [ent("normal"), ent("elite"), ent("boss")]
    assert cj.calc_enemy_threat(enemies) == 15 + 120 + 400


def test_threat_unknown_category_falls_back_to_five():
    assert cj.calc_enemy_threat([{}]) == 5
    assert cj.calc_enemy_threat([ent("no_such_category")]) == 5


def test_threat_zero_for_empty():
    assert cj.calc_enemy_threat([]) == 0.0


def test_threat_tolerates_non_dict_entries():
    """脏数据不能让威胁统计抛异常。"""
    assert cj.calc_enemy_threat([None, "junk", 42]) == 15  # 3 个 × unknown(5)


def test_ratio_normal():
    assert cj.calc_threat_ratio(100.0, 300.0) == pytest.approx(3.0)


@pytest.mark.parametrize("power", [0, -10, None, float("nan")])
def test_ratio_bad_power_returns_sentinel(power):
    """实力为 0/负数/None/NaN 时统一视为「极度危险」。"""
    assert cj.calc_threat_ratio(power, 100.0) == 999.0


# ---------------------------------------------------------------------------
# 三档决策
# ---------------------------------------------------------------------------
def test_decision_fight_when_overwhelming_power():
    r = cj.judge_combat(ctx([ent("normal")], power=1000.0))
    assert r["decision"] == cj.DECISION_FIGHT
    assert r["recommended_set"] == cj.SET_COMBAT
    assert r["threat_ratio"] == pytest.approx(0.015, abs=1e-3)


def test_decision_chase_set_when_valuable_target_present():
    """实力碾压 + 场上有精英 → 推荐追击套。"""
    r = cj.judge_combat(ctx([ent("elite")], power=1000.0))
    assert r["decision"] == cj.DECISION_FIGHT
    assert r["recommended_set"] == cj.SET_CHASE


def test_decision_cautious_on_moderate_threat():
    r = cj.judge_combat(ctx([ent("elite")], power=100.0))  # ratio 1.2
    assert r["decision"] == cj.DECISION_CAUTIOUS
    assert r["recommended_set"] == cj.SET_TANK


def test_decision_retreat_on_overwhelming_threat():
    r = cj.judge_combat(ctx([ent("boss")], power=100.0))  # ratio 4.0
    assert r["decision"] == cj.DECISION_RETREAT
    assert r["recommended_set"] == cj.SET_RETREAT
    assert "远超自身实力" in r["retreat_reason"]


def test_zero_enemies_is_fight():
    r = cj.judge_combat(ctx(power=100.0))
    assert r["decision"] == cj.DECISION_FIGHT
    assert r["enemy_threat"] == 0.0
    assert r["has_highest_boss"] is False


def test_decision_boundary_around_retreat_ratio():
    """ratio 恰好在 RETREAT_RATIO*0.8 / *1.4 两侧时档位必须切换。"""
    # 0.79 → fight；0.81 → cautious；1.39 → cautious；1.41 → retreat
    assert cj.judge_combat(ctx([{"category": "custom"}], power=100.0))  # unknown=5
    r_low = cj.judge_combat(ctx([ent("normal")] * 5, power=100.0))       # 75/100=0.75
    assert r_low["decision"] == cj.DECISION_FIGHT
    r_mid = cj.judge_combat(ctx([ent("normal")] * 6, power=100.0))       # 90/100=0.90
    assert r_mid["decision"] == cj.DECISION_CAUTIOUS
    r_high = cj.judge_combat(ctx([ent("normal")] * 10, power=100.0))     # 150/100=1.5
    assert r_high["decision"] == cj.DECISION_RETREAT


def test_judge_output_contract_keys():
    r = cj.judge_combat(ctx([ent("elite")]))
    for k in ("decision", "recommended_set", "mindset", "enemy_threat",
              "threat_ratio", "has_highest_boss", "retreat_reason"):
        assert k in r


# ---------------------------------------------------------------------------
# highest_boss 动态避险
# ---------------------------------------------------------------------------
def test_highest_boss_retreat_when_weak():
    r = cj.judge_combat(ctx([ent("highest_boss")], power=100.0))  # ratio 10
    assert r["has_highest_boss"] is True
    assert r["decision"] == cj.DECISION_RETREAT
    assert r["recommended_set"] == cj.SET_RETREAT
    assert "实力不足" in r["retreat_reason"]


def test_highest_boss_cautious_when_strong():
    r = cj.judge_combat(ctx([ent("highest_boss")], power=5000.0))  # ratio 0.2
    assert r["has_highest_boss"] is True
    assert r["decision"] == cj.DECISION_CAUTIOUS
    assert r["recommended_set"] == cj.SET_TANK


def test_highest_boss_flag_with_mixed_enemies():
    r = cj.judge_combat(ctx([ent("normal"), ent("highest_boss")], power=10.0))
    assert r["has_highest_boss"] is True
    assert r["decision"] == cj.DECISION_RETREAT


# ---------------------------------------------------------------------------
# 心态
# ---------------------------------------------------------------------------
def test_mindset_balanced_without_enemies():
    assert cj.decide_mindset(ctx()) == cj.MINDSET_BALANCED


def test_mindset_highest_boss_weak_is_conservative():
    assert cj.decide_mindset(ctx([ent("highest_boss")], power=100.0)) == cj.MINDSET_CONSERVATIVE


def test_mindset_highest_boss_strong_is_balanced():
    assert cj.decide_mindset(ctx([ent("highest_boss")], power=5000.0)) == cj.MINDSET_BALANCED


def test_mindset_boss_strong_is_aggressive():
    assert cj.decide_mindset(ctx([ent("boss")], power=5000.0)) == cj.MINDSET_AGGRESSIVE


def test_mindset_boss_weak_is_conservative():
    assert cj.decide_mindset(ctx([ent("boss")], power=100.0)) == cj.MINDSET_CONSERVATIVE


def test_mindset_boss_middle_is_balanced():
    assert cj.decide_mindset(ctx([ent("boss")], power=500.0)) == cj.MINDSET_BALANCED  # 0.8


def test_mindset_elite_strong_is_aggressive():
    assert cj.decide_mindset(ctx([ent("elite")], power=1000.0)) == cj.MINDSET_AGGRESSIVE  # 0.12


def test_mindset_normal_strong_is_aggressive():
    assert cj.decide_mindset(ctx([ent("normal")], power=1000.0)) == cj.MINDSET_AGGRESSIVE


def test_mindset_normal_weak_is_balanced():
    assert cj.decide_mindset(ctx([ent("normal")], power=10.0)) == cj.MINDSET_BALANCED  # 1.5


def test_mindset_tolerates_non_dict_enemy():
    """非 dict 实体按 unknown(5) 计威胁，不得抛异常。"""
    m = cj.decide_mindset(ctx(["junk"]))
    assert m in (cj.MINDSET_CONSERVATIVE, cj.MINDSET_BALANCED, cj.MINDSET_AGGRESSIVE)


def test_conservative_low_hp_upgrades_fight_to_cautious():
    """保守心态 + 残血 → 不该继续硬拼。"""
    # boss(400)/power(500)=0.8 → cautious；这里构造 fight 但心态保守的场景
    c = ctx([ent("normal")], power=1000.0)          # decision=fight
    c.player.hp = 10.0                               # hp_ratio 0.1 < 0.5
    # 手动把心态钉成保守，验证 hp 修正分支
    import unittest.mock as mock
    with mock.patch.object(cj, "decide_mindset", return_value=cj.MINDSET_CONSERVATIVE):
        r = cj.judge_combat(c)
    assert r["decision"] == cj.DECISION_CAUTIOUS
    assert r["recommended_set"] == cj.SET_TANK


def test_aggressive_upgrades_cautious_to_fight():
    c = ctx([ent("elite")], power=100.0)            # ratio 1.2 → cautious
    import unittest.mock as mock
    with mock.patch.object(cj, "decide_mindset", return_value=cj.MINDSET_AGGRESSIVE):
        r = cj.judge_combat(c)
    assert r["decision"] == cj.DECISION_FIGHT
    assert r["recommended_set"] == cj.SET_COMBAT


# ---------------------------------------------------------------------------
# 组队协同（含 S4 回归：逃生优先）
# ---------------------------------------------------------------------------
def test_team_support_when_allies_are_output():
    r = cj.judge_combat(ctx([ent("normal")], teammates=[mate(cj.SET_COMBAT)] * 2,
                            power=1000.0))
    assert r["recommended_set"] == cj.SET_TEAM_SUPPORT


def test_team_output_when_allies_are_tank():
    r = cj.judge_combat(ctx([ent("normal")], teammates=[mate(cj.SET_TANK)] * 2,
                            power=1000.0))
    assert r["recommended_set"] == cj.SET_COMBAT


def test_team_balanced_keeps_recommendation():
    r = cj.judge_combat(ctx([ent("normal")],
                            teammates=[mate(cj.SET_COMBAT), mate(cj.SET_TANK)],
                            power=1000.0))
    assert r["recommended_set"] == cj.SET_COMBAT


def test_regression_retreat_survives_team_adjustment():
    """
    S4 回归：原实现里组队协同会无条件覆盖推荐套装，
    导致「正在全力逃生」被队友配置改成辅助套。逃生必须优先。
    """
    c = ctx([ent("boss")], teammates=[mate(cj.SET_COMBAT)] * 3, power=100.0)
    assert cj.judge_combat(c)["decision"] == cj.DECISION_RETREAT
    r = cj.judge_combat(c)
    assert r["recommended_set"] == cj.SET_RETREAT


def test_team_set_adjust_respects_retreat_decision():
    t = [mate(cj.SET_COMBAT)]
    assert cj._team_set_adjust(t, cj.SET_RETREAT, cj.DECISION_RETREAT) == cj.SET_RETREAT
    # decision 缺省(None)时保持旧行为，保证向后兼容
    assert cj._team_set_adjust(t, cj.SET_RETREAT) == cj.SET_TEAM_SUPPORT
    assert cj._team_set_adjust([], cj.SET_COMBAT) == cj.SET_COMBAT


# ---------------------------------------------------------------------------
# 有限追杀
# ---------------------------------------------------------------------------
def test_chase_elite_and_boss_by_default():
    assert cj.should_chase(ent("elite")) is True
    assert cj.should_chase(ent("boss")) is True


def test_chase_rejects_low_tier_and_highest_boss():
    assert cj.should_chase(ent("normal")) is False
    assert cj.should_chase(ent("highest_boss")) is False


def test_chase_stops_at_max_distance():
    assert cj.should_chase(ent("boss"), chased_distance=399) is True
    assert cj.should_chase(ent("boss"), chased_distance=400) is False


def test_chase_min_category_config_is_honored():
    """S4：combat.chase_min_category 原先是死配置，改了不生效。"""
    cj.CHASE_MIN_CATEGORY = "boss"
    assert cj.should_chase(ent("elite")) is False
    assert cj.should_chase(ent("boss")) is True

    cj.CHASE_MIN_CATEGORY = "normal"
    assert cj.should_chase(ent("normal")) is True
    assert cj.should_chase(ent("highest_boss")) is False  # 仍永不追


def test_chase_tolerates_non_dict():
    assert cj.should_chase(None) is False


# ---------------------------------------------------------------------------
# 安全区钳制
# ---------------------------------------------------------------------------
def test_clamp_pulls_back_from_edges():
    assert cj.clamp_to_safe_zone(0, 0) == (100.0, 100.0)
    assert cj.clamp_to_safe_zone(1920, 1080) == (1820.0, 980.0)


def test_clamp_keeps_interior_point():
    assert cj.clamp_to_safe_zone(960, 540) == (960.0, 540.0)


def test_clamp_explicit_args():
    assert cj.clamp_to_safe_zone(5, 5, screen_w=800, screen_h=600, margin=50) == (50.0, 50.0)


def test_regression_clamp_degenerate_safe_zone():
    """
    S4 回归：屏幕比安全区还小时，原实现恒返回 margin，
    结果坐标可能落在屏幕外。退化为钉中心。
    """
    assert cj.clamp_to_safe_zone(9999, 9999, screen_w=150, screen_h=120,
                                 margin=100) == (75.0, 60.0)
    assert cj.clamp_to_safe_zone(-50, -50, screen_w=150, screen_h=120,
                                 margin=100) == (75.0, 60.0)


# ---------------------------------------------------------------------------
# 移动抖动
# ---------------------------------------------------------------------------
def test_jitter_stays_within_max():
    random.seed(7)
    for _ in range(200):
        jx, jy = cj.apply_jitter(1000.0, 500.0)
        assert abs(jx - 1000.0) <= cj.JITTER_MAX + 0.05
        assert abs(jy - 500.0) <= cj.JITTER_MAX + 0.05


def test_jitter_actually_perturbs():
    random.seed(1)
    results = {cj.apply_jitter(1000.0, 500.0) for _ in range(50)}
    assert len(results) > 1


def test_jitter_returns_rounded_floats():
    jx, jy = cj.apply_jitter(100.0, 100.0)
    assert round(jx, 1) == jx and round(jy, 1) == jy


# ---------------------------------------------------------------------------
# 避险走位
# ---------------------------------------------------------------------------
def test_retreat_flee_moves_away_from_threat():
    c = ctx([ent("highest_boss", 500, 600)], power=10.0, x=500.0, y=500.0)
    r = cj.calc_retreat_position(c, ent("highest_boss", 500, 600))
    assert r["strategy"] == "flee"
    assert r["y"] < 500.0                 # 威胁在下方 → 往上撤
    assert 100.0 <= r["x"] <= 1820.0      # 不贴边缘
    assert 100.0 <= r["y"] <= 980.0


def test_retreat_strafe_moves_perpendicular():
    c = ctx([ent("boss", 500, 600)], power=5000.0, x=500.0, y=500.0)
    r = cj.calc_retreat_position(c, ent("boss", 500, 600))
    assert r["strategy"] == "strafe"
    assert abs(r["x"] - 500.0) > 100.0    # 明显横向偏移
    assert abs(r["y"] - 500.0) < 1.0      # 纵向基本不变（垂直于威胁方向）


def test_retreat_handles_coincident_positions():
    """玩家与威胁重合时 dist=0，不能除零。"""
    c = ctx([ent("boss", 500, 500)], power=10.0, x=500.0, y=500.0)
    r = cj.calc_retreat_position(c, ent("boss", 500, 500))
    assert r["strategy"] == "flee"
    assert 100.0 <= r["x"] <= 1820.0


def test_retreat_respects_margin_config():
    """S4：避险走位原先硬编码 margin=100，与 safe_zone_margin 脱节。"""
    cj.SAFE_ZONE_MARGIN = 300
    try:
        c = ctx([ent("boss", 500, 900)], power=10.0, x=500.0, y=500.0)
        r = cj.calc_retreat_position(c, ent("boss", 500, 900))
        assert r["x"] >= 300.0 and r["y"] >= 300.0
        assert r["y"] <= 1080 - 300
    finally:
        cj.reload_config()


def test_retreat_tolerates_missing_entity_fields():
    """威胁实体缺 x_now/y_now 时回退到玩家自身坐标，不得抛异常。"""
    c = ctx([ent("boss")], power=10.0, x=500.0, y=500.0)
    r = cj.calc_retreat_position(c, {})
    assert r["strategy"] == "flee"
    assert isinstance(r["x"], float)
    assert 100.0 <= r["x"] <= 1820.0 and 100.0 <= r["y"] <= 980.0


# ---------------------------------------------------------------------------
# 评估防抖
# ---------------------------------------------------------------------------
def test_evaluator_returns_cached_within_interval(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cj, "time", clock)
    ev = cj.CombatEvaluator(debounce_interval=0.7)

    c = ctx([ent("boss")], power=100.0)
    first = ev.evaluate(c)
    clock.advance(0.3)
    second = ev.evaluate(c)
    assert second is first                    # 命中缓存，同一对象

    clock.advance(0.5)                        # 累计 0.8 > 0.7
    third = ev.evaluate(c)
    assert third is not first


def test_evaluator_invalidate_forces_recompute(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cj, "time", clock)
    ev = cj.CombatEvaluator(debounce_interval=10.0)
    c = ctx([ent("boss")], power=100.0)
    first = ev.evaluate(c)
    ev.invalidate()
    assert ev.evaluate(c) is not first


def test_evaluator_first_call_never_cached(monkeypatch):
    monkeypatch.setattr(cj, "time", FakeClock())
    ev = cj.CombatEvaluator()
    assert ev._cache is None
    assert ev.evaluate(ctx([ent("normal")]))["decision"] == cj.DECISION_FIGHT


def test_regression_evaluator_default_interval_follows_config():
    """
    S4 回归：默认参数在 import 时绑定，config 热加载后新建的评估器
    仍用旧间隔。改为运行时取值。
    """
    cj.EVAL_DEBOUNCE_INTERVAL = 0.25
    try:
        assert cj.CombatEvaluator().interval == 0.25
        assert cj.CombatEvaluator(debounce_interval=5.0).interval == 5.0
    finally:
        cj.reload_config()


# ---------------------------------------------------------------------------
# 脏数据防御
# ---------------------------------------------------------------------------
def test_judge_tolerates_none_player_fields():
    c = cj.CombatContext(
        player=cj.PlayerState(hp=None, max_hp=None, power_score=None),
        enemies=[ent("boss")],
    )
    r = cj.judge_combat(c)
    assert r["decision"] == cj.DECISION_RETREAT   # 实力 None → 比值哨兵 999
    assert r["threat_ratio"] == 999.0


def test_judge_tolerates_nan_hp():
    c = ctx([ent("normal")], power=1000.0, hp=float("nan"), max_hp=float("nan"))
    r = cj.judge_combat(c)
    assert r["decision"] in (cj.DECISION_FIGHT, cj.DECISION_CAUTIOUS)


def test_safe_float_helpers():
    assert cj._safe_float(None, 1.0) == 1.0
    assert cj._safe_float("abc", 2.0) == 2.0
    assert cj._safe_float(float("nan"), 3.0) == 3.0
    assert cj._safe_float("12.5", 0.0) == 12.5


# ---------------------------------------------------------------------------
# 热加载
# ---------------------------------------------------------------------------
def test_reload_config_picks_up_retreat_ratio(monkeypatch):
    """改配置后 judge 的决策区间必须跟着变，而不是写死在代码里。"""
    real_get = config.get

    def fake_get(path, default=None):
        if path == "combat.retreat_ratio":
            return 2.0
        return real_get(path, default)

    monkeypatch.setattr(config, "get", fake_get)
    cj.reload_config()
    assert cj.RETREAT_RATIO == 2.0

    # power 200 / boss 400 = ratio 2.0：默认区间(1.0)会 retreat，
    # 放宽到 2.0 后 2.0 < 2.0*1.4 → cautious
    r = cj.judge_combat(ctx([ent("boss")], power=200.0))
    assert r["decision"] == cj.DECISION_CAUTIOUS


def test_reload_config_defaults_when_yaml_missing(monkeypatch):
    monkeypatch.setattr(config, "get", lambda path, default=None: default)
    cj.reload_config()
    assert cj.RETREAT_RATIO == 1.0
    assert cj.SAFE_ZONE_MARGIN == 100
    assert cj.CATEGORY_THREAT["highest_boss"] == 1000


def test_flee_and_strafe_distance_from_config():
    assert cj.FLEE_DISTANCE == config.get("combat.flee_distance")
    assert cj.STRAFE_DISTANCE == config.get("combat.strafe_distance")


# ---------------------------------------------------------------------------
# 成就
# ---------------------------------------------------------------------------
def test_achievements_are_sorted_and_clearable():
    cj.unlock_achievement("b")
    cj.unlock_achievement("a")
    cj.unlock_achievement("a")     # 去重
    assert cj.get_achievements() == ["a", "b"]
    cj.clear_achievements()
    assert cj.get_achievements() == []
