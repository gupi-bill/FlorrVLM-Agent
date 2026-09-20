#!/usr/bin/env python3
"""
S3 · 预判引擎 predictor.py 实测

覆盖：匀速外推 / 帧数不足 / 帧数-置信度单调 / 高速降置信+阈值锁 /
      抖动降置信 / 实体超时剔除 / 威胁排序 / top-N 截断 / 稀有度分级 /
      非法坐标过滤 / 同名多怪最近距离匹配 / 角色识别 / reset / 热加载。

时间全部走 FakeClock（monkeypatch predictor.time），保证速度与超时可确定性复现，
不依赖真实 sleep，也不会因为机器卡顿而 flaky。
"""
import pytest

import config
import predictor


class FakeClock:
    """可手动推进的时钟，替换 predictor 里的 time.time()。"""

    def __init__(self, start=1000.0):
        self.now = start

    def time(self):
        return self.now

    def advance(self, dt=0.1):
        self.now += dt
        return self.now


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """每个用例前清空追踪器、挂上假时钟；用例结束后恢复真实配置。"""
    predictor.reset()
    clock = FakeClock()
    monkeypatch.setattr(predictor, "time", clock)
    yield clock
    predictor.reset()
    predictor.reload_config()


def feed(clock, points, raw_id="wasp", rarity="Super", dt=0.1, role=None):
    """按点序列逐帧喂入一个实体，每帧间隔 dt 秒。"""
    for x, y in points:
        clock.advance(dt)
        ent = {"raw_id": raw_id, "rarity": rarity, "x": x, "y": y}
        if role is not None:
            ent["role"] = role
        predictor.update_frame_entities([ent])


def feed_frames(clock, frames, dt=0.1):
    """frames 为 List[List[dict]]，逐帧喂入整屏实体。"""
    for ents in frames:
        clock.advance(dt)
        predictor.update_frame_entities(ents)


# ---------------------------------------------------------------------------
# 1. 匀速外推
# ---------------------------------------------------------------------------
def test_uniform_motion_extrapolation(env):
    pts = [(100 + 10 * i, 300) for i in range(8)]
    feed(env, pts)
    res = predictor.predict_all_entities()
    assert len(res) == 1
    e = res[0]

    delta_t = 0.1 * (len(pts) - 1)
    vx_expected = (pts[-1][0] - pts[0][0]) / delta_t

    assert e["vx_per_sec"] == pytest.approx(vx_expected, abs=0.02)
    assert e["vy_per_sec"] == pytest.approx(0.0, abs=0.02)
    assert e["prediction_trusted"] is True
    assert e["x_predict"] == pytest.approx(pts[-1][0] + vx_expected * predictor.PREDICT_SECONDS, abs=1.0)
    assert e["y_predict"] == pytest.approx(300.0, abs=0.2)
    assert e["x_now"] == pytest.approx(pts[-1][0], abs=0.1)


# ---------------------------------------------------------------------------
# 2. 帧数不足：只给当前位置，不给预判
# ---------------------------------------------------------------------------
def test_insufficient_frames_falls_back_to_current(env):
    feed(env, [(100, 100), (105, 100)])  # 2 帧 < MIN_FRAMES(3)
    res = predictor.predict_all_entities()
    assert len(res) == 1
    e = res[0]
    assert e["x_now"] == 105.0
    assert e["x_predict"] is None and e["y_predict"] is None
    assert e["prediction_trusted"] is False
    assert e["confidence"] == 0.0
    assert e["vx_per_sec"] == 0


# ---------------------------------------------------------------------------
# 3. 帧数越多置信度越高
# ---------------------------------------------------------------------------
def test_more_frames_higher_confidence(env):
    pts = [(100 + 10 * i, 300) for i in range(3)]
    feed(env, pts)
    conf_low = predictor.predict_all_entities()[0]["confidence"]

    feed(env, [(100 + 10 * i, 300) for i in range(3, 8)])  # 续到 8 帧
    conf_high = predictor.predict_all_entities()[0]["confidence"]

    assert conf_high > conf_low
    assert conf_high == pytest.approx(0.95, abs=0.01)


# ---------------------------------------------------------------------------
# 4. 高速（瞬移）降置信 + 阈值锁置空预判坐标
# ---------------------------------------------------------------------------
def test_high_speed_drops_confidence_and_locks_prediction(env):
    pts = [(100 + 400 * i, 300) for i in range(8)]  # 4000 px/s
    feed(env, pts)
    e = predictor.predict_all_entities()[0]

    assert e["vx_per_sec"] == pytest.approx(4000.0, abs=1.0)
    assert e["confidence"] == pytest.approx(predictor.SPEED_PENALTY_FLOOR, abs=0.01)
    assert e["confidence"] < predictor.CONFIDENCE_THRESHOLD
    assert e["prediction_trusted"] is False
    assert e["x_predict"] is None and e["y_predict"] is None
    # 不可信时当前坐标仍然要给，下游还能参考真实位置
    assert e["x_now"] == pytest.approx(pts[-1][0], abs=0.1)


# ---------------------------------------------------------------------------
# 5. 抖动降置信（v2.0 修复点：原本只按首尾算速度，抖动会被平均掉）
# ---------------------------------------------------------------------------
def test_jitter_lowers_confidence(env):
    straight = [(100 + 50 * i, 300) for i in range(8)]
    ys = [-50, 50, -50, 50, 50, -50, 50, -50]  # 首尾同高，净位移与直线版一致
    jitter = [(100 + 50 * i, 300 + ys[i]) for i in range(8)]

    feed(env, straight)
    e_straight = predictor.predict_all_entities()[0]
    predictor.reset()

    feed(env, jitter)
    e_jitter = predictor.predict_all_entities()[0]

    # 净速度一致 → 差异只可能来自抖动惩罚
    assert e_jitter["vx_per_sec"] == pytest.approx(e_straight["vx_per_sec"], abs=0.02)
    assert e_jitter["confidence"] < e_straight["confidence"]
    assert e_straight["confidence"] == pytest.approx(0.75, abs=0.01)


# ---------------------------------------------------------------------------
# 6. 实体超时：0.4s 内保留抗漏检，超过即剔除
# ---------------------------------------------------------------------------
def test_entity_timeout_keeps_then_drops(env):
    feed(env, [(100, 100), (100, 100), (100, 100)])
    assert predictor.get_status()["tracked_entities"] == 1

    env.advance(0.2)
    predictor.update_frame_entities([])
    assert predictor.get_status()["tracked_entities"] == 1, "0.2s < entity_timeout，应保留抗 YOLO 漏检"

    env.advance(0.3)  # 累计 0.5s > 0.4s
    predictor.update_frame_entities([])
    assert predictor.get_status()["tracked_entities"] == 0
    assert predictor.predict_all_entities() == []


# ---------------------------------------------------------------------------
# 7. 威胁排序
# ---------------------------------------------------------------------------
def test_threat_sorting(env):
    ents = [
        {"raw_id": "wasp", "rarity": "Common", "x": 10, "y": 10},
        {"raw_id": "hornet", "rarity": "Mythic", "x": 20, "y": 20},
        {"raw_id": "queen", "rarity": "Unique", "x": 30, "y": 30},
        {"raw_id": "king", "rarity": "Super", "x": 40, "y": 40},
        {"raw_id": "enemy_player_1", "rarity": "Common", "x": 50, "y": 50},
    ]
    feed_frames(env, [ents, ents, ents])

    res = predictor.predict_all_entities()
    cats = [e["category"] for e in res]
    scores = [e["threat_score"] for e in res]

    assert cats == ["highest_boss", "boss", "player_enemy", "elite", "normal"]
    assert scores == sorted(scores, reverse=True)
    assert predictor.get_highest_threat()["category"] == "highest_boss"


# ---------------------------------------------------------------------------
# 8. top-N 截断
# ---------------------------------------------------------------------------
def test_top_n_truncation(env):
    ents = [{"raw_id": f"mob{i}", "rarity": "Common", "x": 10 * (i + 1), "y": 10}
            for i in range(12)]
    feed_frames(env, [ents, ents])

    res = predictor.predict_all_entities()
    assert len(res) == predictor.MAX_OUTPUT_ENTITIES == 8
    assert len(predictor._trackers) == 12  # 内部仍全量追踪，只是输出截断


# ---------------------------------------------------------------------------
# 9. 稀有度分级
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("rarity,expected", [
    ("Unique", "highest_boss"),
    ("Eternal", "highest_boss"),
    ("Super", "boss"),
    ("Ultra", "elite"),
    ("Mythic", "elite"),
    ("Legendary", "elite"),
    ("Epic", "elite"),
    ("Rare", "normal"),
    ("Unusual", "normal"),
    ("Common", "normal"),
    ("super", "boss"),        # 大小写不敏感
    ("  epic ", "elite"),     # 容忍空白
    ("Weird", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_classify_by_rarity(rarity, expected):
    assert predictor.classify_by_rarity(rarity) == expected


# ---------------------------------------------------------------------------
# 10. 非法坐标过滤
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("x,y", [
    (None, 10), (-1, 10), (10, -0.5), ("abc", 10), (10, "abc"),
    (200000, 10), (10, 200000), (float("nan"), 1),
])
def test_invalid_coords_filtered(env, x, y):
    env.advance(0.1)
    predictor.update_frame_entities([{"raw_id": "wasp", "rarity": "Common", "x": x, "y": y}])
    assert predictor.get_status()["tracked_entities"] == 0


def test_valid_coord_accepted(env):
    env.advance(0.1)
    predictor.update_frame_entities([{"raw_id": "wasp", "rarity": "Common", "x": 0, "y": 0}])
    assert predictor.get_status()["tracked_entities"] == 1


# ---------------------------------------------------------------------------
# 11. 同名多怪最近距离匹配（v0.2 修复点，防串号）
# ---------------------------------------------------------------------------
def test_nearest_match_keeps_two_same_raw_id_apart(env):
    a = [(100 + 10 * i, 100) for i in range(6)]   # 向右
    b = [(900 - 10 * i, 900) for i in range(6)]   # 向左
    for i in range(6):
        env.advance(0.1)
        predictor.update_frame_entities([
            {"raw_id": "wasp", "rarity": "Common", "x": a[i][0], "y": a[i][1]},
            {"raw_id": "wasp", "rarity": "Common", "x": b[i][0], "y": b[i][1]},
        ])

    assert len(predictor._trackers) == 2, "两只同名怪应各自独立成链"
    for tracker in predictor._trackers.values():
        xs = [h["x"] for h in tracker.history]
        assert xs == sorted(xs) or xs == sorted(xs, reverse=True), "串号会导致坐标来回跳变"

    xs_now = sorted(e["x_now"] for e in predictor.predict_all_entities())
    assert xs_now == [150.0, 850.0]


# ---------------------------------------------------------------------------
# 12. 角色识别
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw_id,explicit,expected", [
    ("enemy_player_1", None, "player_enemy"),
    ("hostile_bee", None, "player_enemy"),
    ("teammate_bee", None, "player_ally"),
    ("party_member", None, "player_ally"),
    ("wasp", None, "monster"),
    ("wasp", "player_ally", "player_ally"),
    ("wasp", "bogus_role", "monster"),   # 非法 explicit 不应污染结果
    (None, None, "monster"),
])
def test_detect_role(raw_id, explicit, expected):
    assert predictor.detect_role(raw_id, explicit) == expected


def test_role_updates_category_each_frame(env):
    """稀有度/身份逐帧变化时，分类必须跟着重算（v2.0 修复点）。"""
    feed(env, [(100, 100), (105, 100), (110, 100)], rarity="Common")
    assert predictor.predict_all_entities()[0]["category"] == "normal"

    feed(env, [(115, 100), (120, 100), (125, 100)], rarity="Super")  # 升档
    e = predictor.predict_all_entities()[0]
    assert e["category"] == "boss"
    assert e["threat_score"] == 400


# ---------------------------------------------------------------------------
# 13. reset
# ---------------------------------------------------------------------------
def test_reset_clears_state(env):
    feed(env, [(100 + 10 * i, 300) for i in range(5)])
    assert predictor.get_status()["tracked_entities"] == 1

    predictor.reset()
    assert predictor.get_status()["tracked_entities"] == 0
    assert predictor.predict_all_entities() == []
    assert predictor.get_highest_threat() is None
    assert predictor._uid_counter == 0


# ---------------------------------------------------------------------------
# 14. 配置热加载
# ---------------------------------------------------------------------------
def test_reload_config_picks_up_overrides(monkeypatch, env):
    real_get = config.get

    def fake_get(path, default=None):
        overrides = {
            "predictor.predict_seconds": 2.0,
            "predictor.confidence_threshold": 0.9,
            "predictor.max_output_entities": 3,
        }
        return overrides.get(path, real_get(path, default))

    try:
        monkeypatch.setattr(config, "get", fake_get)
        predictor.reload_config()
        assert predictor.PREDICT_SECONDS == 2.0
        assert predictor.CONFIDENCE_THRESHOLD == 0.9
        assert predictor.MAX_OUTPUT_ENTITIES == 3
    finally:
        monkeypatch.undo()
        predictor.reload_config()

    # 回滚后恢复 yaml 原值
    assert predictor.PREDICT_SECONDS == pytest.approx(1.2)
    assert predictor.CONFIDENCE_THRESHOLD == pytest.approx(0.65)
    assert predictor.MAX_OUTPUT_ENTITIES == 8


def test_status_reports_effective_config():
    st = predictor.get_status()
    assert st["predict_seconds"] == pytest.approx(1.2)
    assert st["entity_timeout"] == pytest.approx(0.4)
    assert st["max_output"] == 8
    assert st["confidence_threshold"] == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# 15. 历史长度上限
# ---------------------------------------------------------------------------
def test_history_maxlen_cap(env):
    feed(env, [(100 + i, 300) for i in range(20)])
    tracker = list(predictor._trackers.values())[0]
    assert len(tracker.history) == predictor.HISTORY_MAXLEN == 10
    # 超出后 oldest 被丢弃，速度仍按窗口内首尾计算
    e = predictor.predict_all_entities()[0]
    assert e["x_now"] == pytest.approx(119.0, abs=0.1)
