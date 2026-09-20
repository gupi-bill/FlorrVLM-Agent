#!/usr/bin/env python3
"""
S4 · 自动调参 auto_tuner.py 实测

覆盖：默认值读取 / 死亡驱动下调敢打度 / 命中率驱动下调置信线 /
      上下限夹紧 / 坏文件与坏字段容错 / 冷静期(hold) / 写入-读取往返 / reset / status。

全部离线：落盘路径由 conftest 的 tmp_tuned 夹具重定向到 tmp_path，
不会在仓库里留下 tuned_overrides.yaml 污染 config 的加载优先级。
"""
import pytest

import auto_tuner
import config


@pytest.fixture(autouse=True)
def tuned(tmp_tuned):
    """每个用例都使用独立的临时调参文件。"""
    return tmp_tuned


def read_raw(path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_raw(path, data):
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------
def test_current_returns_config_defaults_when_no_file():
    c = auto_tuner.current()
    assert c["combat.retreat_ratio"] == config.get("combat.retreat_ratio")
    assert c["predictor.confidence_threshold"] == config.get(
        "predictor.confidence_threshold")


def test_tune_no_change_message_without_signals():
    msg = auto_tuner.tune()
    assert "无需调整" in msg


# ---------------------------------------------------------------------------
# 死亡 → 下调敢打度
# ---------------------------------------------------------------------------
def test_tune_deaths_lowers_retreat_ratio():
    msg = auto_tuner.tune(deaths_extra=2)
    assert "retreat_ratio" in msg
    c = auto_tuner.current()
    assert c["combat.retreat_ratio"] == pytest.approx(0.8, abs=1e-6)


def test_tune_deaths_step_is_linear():
    auto_tuner.tune(deaths_extra=3)
    assert auto_tuner.current()["combat.retreat_ratio"] == pytest.approx(0.7, abs=1e-6)


def test_retreat_ratio_clamped_at_lower_bound():
    """连续多轮重罚，敢打度不能跌破 RETREAT_RATIO_MIN。"""
    for _ in range(12):
        auto_tuner.tune(deaths_extra=5)
        # 冷静期会跳过，强制清零以便继续下调
        auto_tuner._write({**auto_tuner._read(), "_cooldown": 0})
    assert auto_tuner.current()["combat.retreat_ratio"] >= auto_tuner.RETREAT_RATIO_MIN
    assert auto_tuner.current()["combat.retreat_ratio"] == pytest.approx(
        auto_tuner.RETREAT_RATIO_MIN, abs=1e-6)


def test_retreat_ratio_never_negative():
    auto_tuner.tune(deaths_extra=100)
    assert auto_tuner.current()["combat.retreat_ratio"] >= 0


# ---------------------------------------------------------------------------
# 命中率 → 下调置信线
# ---------------------------------------------------------------------------
def test_low_hit_rate_lowers_confidence():
    msg = auto_tuner.tune(hits=2, attempts=10)     # 0.2 < 0.5
    assert "confidence" in msg
    assert auto_tuner.current()["predictor.confidence_threshold"] == pytest.approx(
        0.60, abs=1e-6)


def test_high_hit_rate_leaves_confidence_alone():
    msg = auto_tuner.tune(hits=9, attempts=10)     # 0.9 >= 0.5
    assert "无需调整" in msg
    assert auto_tuner.current()["predictor.confidence_threshold"] == pytest.approx(
        config.get("predictor.confidence_threshold"), abs=1e-6)


def test_zero_attempts_skips_confidence_check():
    """attempts=0 时不能做除零，也不能误判为命中率 0。"""
    msg = auto_tuner.tune(hits=0, attempts=0)
    assert "无需调整" in msg


def test_confidence_clamped_at_lower_bound():
    for _ in range(12):
        auto_tuner.tune(hits=0, attempts=10)
        auto_tuner._write({**auto_tuner._read(), "_cooldown": 0})
    assert auto_tuner.current()[
        "predictor.confidence_threshold"] == pytest.approx(
        auto_tuner.CONF_THRESH_MIN, abs=1e-6)


# ---------------------------------------------------------------------------
# 冷静期（S4：HOLD 原先只计数不消费）
# ---------------------------------------------------------------------------
def test_cooldown_suppresses_immediate_readjustment():
    first = auto_tuner.tune(deaths_extra=1)
    assert "retreat_ratio" in first

    for _ in range(auto_tuner.HOLD):
        msg = auto_tuner.tune(deaths_extra=1)
        assert "冷静期" in msg

    # 冷静期结束后恢复调整
    again = auto_tuner.tune(deaths_extra=1)
    assert "retreat_ratio" in again


def test_value_unchanged_during_cooldown():
    auto_tuner.tune(deaths_extra=1)
    v = auto_tuner.current()["combat.retreat_ratio"]
    auto_tuner.tune(deaths_extra=1)
    auto_tuner.tune(deaths_extra=1)
    assert auto_tuner.current()["combat.retreat_ratio"] == v


def test_no_cooldown_when_nothing_changed():
    auto_tuner.tune()          # 无信号
    assert auto_tuner._read().get("_cooldown", 0) == 0
    # 紧接着给信号，必须能立即调整（不被无谓的冷静期挡住）
    msg = auto_tuner.tune(deaths_extra=1)
    assert "retreat_ratio" in msg


def test_hold_zero_disables_cooldown(monkeypatch):
    monkeypatch.setattr(auto_tuner, "HOLD", 0)
    auto_tuner.tune(deaths_extra=1)
    assert "retreat_ratio" in auto_tuner.tune(deaths_extra=1)


# ---------------------------------------------------------------------------
# 坏文件 / 坏字段容错
# ---------------------------------------------------------------------------
def test_out_of_range_value_is_clamped_on_read(tmp_tuned):
    write_raw(tmp_tuned, {"combat": {"retreat_ratio": 99}})
    assert auto_tuner.current()["combat.retreat_ratio"] == auto_tuner.RETREAT_RATIO_MAX


def test_negative_value_is_clamped_on_read(tmp_tuned):
    write_raw(tmp_tuned, {"combat": {"retreat_ratio": -5}})
    assert auto_tuner.current()["combat.retreat_ratio"] == auto_tuner.RETREAT_RATIO_MIN


def test_non_dict_section_does_not_crash(tmp_tuned):
    """手写坏的 tuned_overrides.yaml（combat 是字符串）不能炸穿调用点。"""
    write_raw(tmp_tuned, {"combat": "broken"})
    c = auto_tuner.current()
    assert c["combat.retreat_ratio"] == pytest.approx(
        config.get("combat.retreat_ratio"), abs=1e-6)
    assert "retreat_ratio" in auto_tuner.tune(deaths_extra=1)


def test_corrupt_yaml_file_falls_back_to_defaults(tmp_tuned):
    with open(tmp_tuned, "w", encoding="utf-8") as f:
        f.write("{ this is : not : valid yaml [")
    c = auto_tuner.current()
    assert c["combat.retreat_ratio"] == pytest.approx(
        config.get("combat.retreat_ratio"), abs=1e-6)


def test_non_dict_top_level_is_ignored(tmp_tuned):
    write_raw(tmp_tuned, ["a", "b"])
    assert auto_tuner.current()["combat.retreat_ratio"] == pytest.approx(
        config.get("combat.retreat_ratio"), abs=1e-6)


def test_bad_cooldown_value_is_tolerated(tmp_tuned):
    write_raw(tmp_tuned, {"_cooldown": "not-a-number"})
    assert "retreat_ratio" in auto_tuner.tune(deaths_extra=1)


# ---------------------------------------------------------------------------
# 往返 / reset / status
# ---------------------------------------------------------------------------
def test_write_then_read_roundtrip(tmp_tuned):
    auto_tuner.tune(deaths_extra=2)
    assert tmp_tuned.exists()
    raw = read_raw(tmp_tuned)
    assert raw["combat"]["retreat_ratio"] == pytest.approx(0.8, abs=1e-6)
    assert auto_tuner.current()["combat.retreat_ratio"] == pytest.approx(0.8, abs=1e-6)


def test_reset_removes_override_file(tmp_tuned):
    auto_tuner.tune(deaths_extra=1)
    assert tmp_tuned.exists()
    msg = auto_tuner.reset()
    assert "已重置" in msg
    assert not tmp_tuned.exists()
    assert auto_tuner.current()["combat.retreat_ratio"] == pytest.approx(
        config.get("combat.retreat_ratio"), abs=1e-6)


def test_reset_is_idempotent(tmp_tuned):
    auto_tuner.reset()
    assert "已重置" in auto_tuner.reset()


def test_status_string_contains_both_metrics(tmp_tuned):
    auto_tuner.tune(deaths_extra=1)          # 1.0 - 0.1 → 0.9
    s = auto_tuner.status()
    assert "敢打度=0.9" in s
    assert f"置信线={config.get('predictor.confidence_threshold')}" in s


def test_both_signals_adjust_together(tmp_tuned):
    msg = auto_tuner.tune(hits=1, attempts=10, deaths_extra=1)
    assert "retreat_ratio" in msg and "confidence" in msg
    c = auto_tuner.current()
    assert c["combat.retreat_ratio"] == pytest.approx(0.9, abs=1e-6)
    assert c["predictor.confidence_threshold"] == pytest.approx(0.60, abs=1e-6)


def test_tune_file_is_valid_yaml_after_many_rounds(tmp_tuned):
    for i in range(8):
        auto_tuner.tune(deaths_extra=1, hits=i, attempts=10)
    raw = read_raw(tmp_tuned)
    assert isinstance(raw, dict)
    assert "combat" in raw
