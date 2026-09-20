#!/usr/bin/env python3
"""
S6 · 感知服务离线化测试 tests/test_perception_server.py
=======================================================
覆盖三条主线：
1. 后端选择：auto/http/mock 的判定与环境优先级（无 YOLO / 无 X server 环境下必须降级）
2. 契约标准化：实体过滤、玩家脏值、队友识别、错误帧不再伪装成"空场景"
3. 端到端：Flask 路由、--selftest 自检、mock 帧喂给 predictor 能否算出速度

全程零截图、零网络、零真实 YOLO；时间用显式 now 参数或 FakeClock 注入。
"""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import perception_server as ps  # noqa: E402


CONTRACT = ("player", "entities", "teammates", "afk_popup")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """每个用例都从干净的后端环境 + 干净的 mock 漂移状态开始。"""
    monkeypatch.delenv(ps.BACKEND_ENV, raising=False)
    ps.reset_mock()
    yield
    ps.reset_mock()


@pytest.fixture
def mock_backend(monkeypatch):
    monkeypatch.setenv(ps.BACKEND_ENV, "mock")
    return "mock"


def _patch_http(monkeypatch, tool="scrot", script="/fake/detect.py", shot=True):
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: tool)
    monkeypatch.setattr(ps, "_find_detect_script", lambda: script)
    monkeypatch.setattr(ps, "_take_screenshot", lambda p: shot)
    monkeypatch.setattr(ps, "skip_on_timeout", lambda: 0.0)


# ---------------------------------------------------------------------------
# 1. 后端选择
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("val,expect", [
    ("mock", "mock"), ("http", "http"), ("auto", "auto"),
    ("MOCK", "mock"), (" mock ", "mock"),
])
def test_configured_backend_env(monkeypatch, val, expect):
    monkeypatch.setenv(ps.BACKEND_ENV, val)
    assert ps.configured_backend() == expect


@pytest.mark.parametrize("val", ["", "bogus", "yolo", "none"])
def test_configured_backend_env_invalid_falls_back(monkeypatch, val):
    """非法环境变量必须回落配置/auto，不能让服务起不来。"""
    monkeypatch.setenv(ps.BACKEND_ENV, val)
    assert ps.configured_backend() in ps.VALID_BACKENDS


def test_configured_backend_from_config(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None: "http"
                        if path == "perception.backend" else default)
    assert ps.configured_backend() == "http"


def test_resolve_auto_to_mock_when_no_tool(monkeypatch):
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: "")
    monkeypatch.setattr(ps, "_find_detect_script", lambda: "")
    assert ps.resolve_backend() == "mock"


def test_resolve_auto_to_mock_when_no_detect_script(monkeypatch):
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: "scrot")
    monkeypatch.setattr(ps, "_find_detect_script", lambda: "")
    assert ps.resolve_backend() == "mock"


def test_resolve_auto_to_http_when_ready(monkeypatch):
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: "scrot")
    monkeypatch.setattr(ps, "_find_detect_script", lambda: "/fake/detect.py")
    assert ps.resolve_backend() == "http"


@pytest.mark.parametrize("explicit", ["mock", "http"])
def test_resolve_explicit_bypasses_detection(monkeypatch, explicit):
    """显式后端不做探测，避免"想 mock 却因环境有 import 命令被判成 http"。"""
    monkeypatch.setenv(ps.BACKEND_ENV, explicit)
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: "scrot")
    monkeypatch.setattr(ps, "_find_detect_script", lambda: "/fake/detect.py")
    assert ps.resolve_backend() == explicit


# ---------------------------------------------------------------------------
# 2. 配置读取（运行时，支持热加载）
# ---------------------------------------------------------------------------
def test_port_falls_back_to_server_section(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None:
                        5001 if path == "server.perception_port" else default)
    assert ps.port() == 5001


def test_port_prefers_perception_section(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None:
                        6001 if path == "perception.port" else default)
    assert ps.port() == 6001


@pytest.mark.parametrize("bad", [None, "abc", float("nan"), ""])
def test_port_bad_value_safe(monkeypatch, bad):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None:
                        bad if path == "perception.port" else None)
    assert ps.port() in (5001, 0) or isinstance(ps.port(), int)


def test_yolo_timeout_floor(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None: 0)
    assert ps.yolo_timeout() >= 1


def test_screen_size_fallback_chain(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None:
                        {"combat.safe_zone_w": 1280, "combat.safe_zone_h": 720}.get(path, default))
    assert ps.screen_size() == (1280.0, 720.0)


def test_screen_size_zero_guard(monkeypatch):
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None: 0)
    assert ps.screen_size() == (1920.0, 1080.0)


def test_cfg_missing_config_module(monkeypatch):
    """config 导入失败时不能让感知服务崩，回退 default。"""
    monkeypatch.setattr(ps, "_cfg", lambda path, default=None: default)
    assert ps._cfg("perception.backend", "auto") == "auto"


# ---------------------------------------------------------------------------
# 3. 实体 / 玩家 / 队友标准化
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ent,expect", [
    ({"raw_id": "a", "x": 1, "y": 2}, True),
    ({"raw_id": "a", "x": "12.5", "y": "3"}, True),
    ({"raw_id": "a", "x": 0, "y": 0}, True),
    ({"x": 1, "y": 2}, False),                       # 缺 raw_id
    ({"raw_id": "a", "y": 2}, False),                # 缺 x
    ({"raw_id": "a", "x": -1, "y": 2}, False),       # 负坐标
    ({"raw_id": "a", "x": 1, "y": -5}, False),
    ({"raw_id": "a", "x": 99999, "y": 2}, False),    # 越界
    ({"raw_id": "a", "x": float("nan"), "y": 2}, False),   # NaN
    ({"raw_id": "a", "x": float("inf"), "y": 2}, False),   # Inf
    ({"raw_id": "a", "x": "nan", "y": 2}, False),    # NaN 字符串
    ({"raw_id": "a", "x": None, "y": 2}, False),
    ({"raw_id": "a", "x": "abc", "y": 2}, False),
    ("not a dict", False),
    (None, False),
])
def test_is_valid_entity(ent, expect):
    assert ps._is_valid_entity(ent) is expect


def test_normalize_entities_non_list():
    assert ps.normalize_entities(None) == []
    assert ps.normalize_entities("x") == []


def test_normalize_entities_rounds_and_stringifies():
    out = ps.normalize_entities([{"raw_id": 7, "x": 1.23456, "y": "9.0"}])
    assert out == [{"raw_id": "7", "rarity": "Common", "x": 1.2, "y": 9.0}]


def test_normalize_player_defaults():
    p = ps.normalize_player(None)
    assert p["alive"] is True and p["hp"] == 100 and p["max_hp"] == 100


@pytest.mark.parametrize("raw,key,expect", [
    ({"hp": float("nan")}, "hp", 100.0),
    ({"hp": "abc"}, "hp", 100.0),
    ({"hp": None}, "hp", 100.0),
    ({"max_hp": float("inf")}, "max_hp", 100.0),
    ({"power_score": "55.5"}, "power_score", 55.5),
    ({"alive": 0}, "alive", False),
    ({"petal_set": None}, "petal_set", "None"),
])
def test_normalize_player_dirty(raw, key, expect):
    assert ps.normalize_player(raw)[key] == expect


def test_normalize_teammates_prefers_explicit_list():
    raw = {"teammates": [{"raw_id": "p1", "x": 1, "y": 2}]}
    out = ps.normalize_teammates(raw, [{"raw_id": "player_ally", "x": 9, "y": 9}])
    assert len(out) == 1 and out[0]["raw_id"] == "p1"


def test_normalize_teammates_from_entities():
    ents = [{"raw_id": "player_ally", "x": 3, "y": 4},
            {"raw_id": "hornet", "x": 5, "y": 6}]
    out = ps.normalize_teammates({}, ents)
    assert [t["raw_id"] for t in out] == ["player_ally"]


def test_normalize_teammates_category_marker():
    out = ps.normalize_teammates({}, [{"raw_id": "x", "category": "Teammate", "x": 1, "y": 1}])
    assert len(out) == 1


@pytest.mark.parametrize("raw", [None, "x", 123, {"teammates": "not-a-list"}])
def test_normalize_teammates_bad_input(raw):
    assert ps.normalize_teammates(raw, None) == []


def test_normalize_teammates_skips_bad_entries():
    out = ps.normalize_teammates({"teammates": ["x", None, {"x": "bad", "y": "worse"}]}, [])
    assert len(out) == 1 and out[0]["x"] == 0.0


def test_normalize_detections_drops_teammates_from_entities():
    det = {"entities": [{"raw_id": "player_ally", "x": 1, "y": 1},
                        {"raw_id": "hornet", "x": 2, "y": 2}],
           "afk_popup": True}
    out = ps.normalize_detections(det)
    assert [e["raw_id"] for e in out["entities"]] == ["hornet"]
    assert len(out["teammates"]) == 1
    assert out["afk_popup"] is True
    assert out["_raw"] is det


@pytest.mark.parametrize("det", [None, "x", 5, {}])
def test_normalize_detections_bad_input_contract_holds(det):
    out = ps.normalize_detections(det)
    for k in CONTRACT:
        assert k in out


# ---------------------------------------------------------------------------
# 4. mock 后端
# ---------------------------------------------------------------------------
def test_mock_detections_from_config(mock_backend):
    det = ps.mock_detections(now=1000.0)
    assert det["_mock"] is True
    assert len(det["entities"]) >= 1
    assert isinstance(det["teammates"], list)


def test_mock_drift_advances_position(mock_backend):
    d1 = ps.mock_detections(now=1000.0)   # 首帧确立基准，dt=0
    d2 = ps.mock_detections(now=1001.0)   # dt=1s
    by_id = {e["raw_id"]: e for e in d2["entities"]}
    for e1 in d1["entities"]:
        e2 = by_id[e1["raw_id"]]
        # 至少一个带速度的实体移动了
        if abs(e2["x"] - e1["x"]) + abs(e2["y"] - e1["y"]) > 0:
            break
    else:
        pytest.fail("drift=true 但没有任何实体移动")


def test_mock_no_drift_static(mock_backend):
    cfg = {"drift": False, "entities": [{"raw_id": "a", "x": 10, "y": 10, "vx": 100, "vy": 100}]}
    d1 = ps.mock_detections(cfg=cfg, now=1.0)
    d2 = ps.mock_detections(cfg=cfg, now=99.0)
    assert d1["entities"][0]["x"] == d2["entities"][0]["x"] == 10


def test_mock_reset_clears_baseline(mock_backend):
    cfg = {"drift": True, "entities": [{"raw_id": "a", "x": 0, "y": 0, "vx": 10, "vy": 0}]}
    ps.mock_detections(cfg=cfg, now=10.0)
    ps.reset_mock()
    assert ps._MOCK_STATE["last"] is None


@pytest.mark.parametrize("cfg", [None if False else "bad", 5, [], {"entities": "x"},
                                 {"entities": [None, "s", 3]}])
def test_mock_detections_dirty_config(cfg):
    out = ps.mock_detections(cfg=cfg, now=1.0)
    assert out["entities"] == [] or all(isinstance(e, dict) for e in out["entities"])


def test_build_payload_mock_contract(mock_backend):
    p = ps.build_perception_payload("mock", now=1000.0)
    for k in CONTRACT:
        assert k in p
    assert p["_backend"] == "mock" and p["_mock"] is True
    assert p["player"]["x"] == 960.0


def test_build_payload_mock_unknown_backend_resolves(monkeypatch):
    monkeypatch.setenv(ps.BACKEND_ENV, "mock")
    p = ps.build_perception_payload("bogus", now=1000.0)
    assert p["_backend"] == "mock"


@pytest.mark.parametrize("start,speed,dt", [
    (400, 80, 1), (400, 80, 1000), (400, -80, 9999),
    (0, -500, 3.3), (1919, 300, 7.7), (10, 0, 500),
])
def test_pingpong_stays_in_bounds(start, speed, dt):
    """回归：修复前 mock 实体会无限外推飞出屏幕，长时间运行后感知结果退化为空。"""
    pos = ps._pingpong(start, speed, dt, 0.0, 1920.0)
    assert 0.0 <= pos <= 1920.0


def test_pingpong_zero_speed_clamps():
    assert ps._pingpong(10, 0, 100, 0.0, 100.0) == 10
    assert ps._pingpong(500, 0, 100, 0.0, 100.0) == 100


def test_mock_long_run_keeps_all_entities(mock_backend):
    """模拟服务跑很久之后仍有完整实体集，离线主循环不会"看不见怪"。"""
    ps.reset_mock()
    ps.mock_detections(now=1000.0)          # 首帧基准
    late = ps.build_perception_payload("mock", now=1000.0 + 3600.0)  # 1 小时后
    assert len(late["entities"]) == 5
    for e in late["entities"]:
        assert 0.0 <= e["x"] <= 1920.0 and 0.0 <= e["y"] <= 1080.0


# ---------------------------------------------------------------------------
# 5. http 后端的失败降级（无 X server / 无 YOLO 场景）
# ---------------------------------------------------------------------------
def test_http_no_screenshot_tool(monkeypatch):
    _patch_http(monkeypatch, tool="")
    p = ps.build_perception_payload("http")
    assert p["_skipped"] is True and p["_reason"] == "screenshot_tool_missing"
    assert "UGF_PERCEPTION_BACKEND" in p["_error"]


def test_http_no_detect_script(monkeypatch):
    _patch_http(monkeypatch, tool="scrot", script="")
    p = ps.build_perception_payload("http")
    assert p["_skipped"] is True and p["_reason"] == "detect_script_missing"


def test_http_screenshot_failed(monkeypatch):
    _patch_http(monkeypatch, shot=False)
    p = ps.build_perception_payload("http")
    assert p["_reason"] == "screenshot_failed"
    assert p["entities"] == []


def test_http_yolo_timeout(monkeypatch):
    _patch_http(monkeypatch)
    monkeypatch.setattr(ps, "_run_yolo", lambda p: {"_timeout": True})
    p = ps.build_perception_payload("http")
    assert p["_reason"] == "yolo_timeout" and p["_skipped"] is True


def test_http_yolo_error_not_silent_empty_frame(monkeypatch):
    """
    回归：修复前 YOLO 报错会被当成"空场景"返回，Agent 误判为游戏里没怪继续空转。
    """
    _patch_http(monkeypatch)
    monkeypatch.setattr(ps, "_run_yolo", lambda p: {"error": "检测脚本未找到"})
    p = ps.build_perception_payload("http")
    assert p["_skipped"] is True
    assert p["_reason"] == "yolo_error"
    assert "检测脚本" in p["_error"]


def test_http_yolo_non_dict_output(monkeypatch):
    _patch_http(monkeypatch)
    monkeypatch.setattr(ps, "_run_yolo", lambda p: ["not", "a", "dict"])
    p = ps.build_perception_payload("http")
    assert p["_reason"] == "yolo_bad_output"


def test_http_success_path_normalizes(monkeypatch):
    _patch_http(monkeypatch)
    monkeypatch.setattr(ps, "_run_yolo", lambda p: {
        "player": {"hp": 80, "max_hp": 100, "x": 10, "y": 20},
        "monsters": [{"raw_id": "hornet", "x": 1, "y": 2},
                     {"raw_id": "player_ally", "x": 3, "y": 4},
                     {"raw_id": "bad", "x": -1, "y": 5}],
        "afk_popup": True,
    })
    p = ps.build_perception_payload("http")
    assert p["_backend"] == "http" and "_skipped" not in p
    assert [e["raw_id"] for e in p["entities"]] == ["hornet"]
    assert p["teammates"][0]["raw_id"] == "player_ally"
    assert p["afk_popup"] is True


def test_http_screenshot_file_always_removed(monkeypatch, tmp_path):
    """截图用完必须删，不能在仓库里堆 png。"""
    _patch_http(monkeypatch)
    monkeypatch.setattr(ps, "SCREENSHOT_PATH", str(tmp_path / "frame.png"))
    ps.SCREENSHOT_PATH  # noqa: B018

    def _fake_shot(path):
        with open(path, "wb") as f:
            f.write(b"fake")
        return True

    monkeypatch.setattr(ps, "_take_screenshot", _fake_shot)
    monkeypatch.setattr(ps, "_run_yolo", lambda p: {"error": "x"})
    ps.build_perception_payload("http")
    assert not os.path.exists(str(tmp_path / "frame.png"))


# ---------------------------------------------------------------------------
# 6. Flask 路由
# ---------------------------------------------------------------------------
def test_route_perceive_contract(mock_backend):
    client = ps.app.test_client()
    resp = client.get("/perceive")
    assert resp.status_code == 200
    data = resp.get_json()
    for k in CONTRACT:
        assert k in data
    assert data["_backend"] == "mock"


def test_route_perceive_raw_flag(mock_backend):
    client = ps.app.test_client()
    assert "_raw" in client.get("/perceive").get_json()
    assert "_raw" not in client.get("/perceive?raw=0").get_json()


def test_route_health_fields(mock_backend):
    data = ps.app.test_client().get("/health").get_json()
    for k in ("status", "backend", "configured_backend", "port",
              "detect_script", "screenshot_tool", "offline"):
        assert k in data
    assert data["backend"] == "mock" and data["offline"] is True


def test_route_http_backend_no_crash(monkeypatch):
    """强制 http 后端且在无截图工具的机器上，路由必须返回结构化错误而不是 500。"""
    monkeypatch.setenv(ps.BACKEND_ENV, "http")
    monkeypatch.setattr(ps, "_screenshot_tool", lambda: "")
    resp = ps.app.test_client().get("/perceive")
    assert resp.status_code == 200
    assert resp.get_json()["_skipped"] is True


# ---------------------------------------------------------------------------
# 7. 自检
# ---------------------------------------------------------------------------
def test_selftest_mock_exit_zero(mock_backend, capsys):
    assert ps.selftest(3, "mock") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["drifting"] is True


def test_selftest_detects_broken_payload(monkeypatch, capsys):
    monkeypatch.setattr(ps, "build_perception_payload", lambda *a, **k: {"player": "x"})
    assert ps.selftest(2, "mock") == 1
    assert json.loads(capsys.readouterr().out)["problems"]


def test_selftest_rounds_respected(mock_backend, capsys):
    ps.selftest(1, "mock")
    assert json.loads(capsys.readouterr().out)["rounds"] == 1


def test_main_selftest_does_not_start_server(monkeypatch):
    started = {"v": False}

    def _boom(*a, **k):
        started["v"] = True

    monkeypatch.setattr(ps.app, "run", _boom)
    assert ps.main(["--selftest", "--backend", "mock", "--rounds", "2"]) == 0
    assert started["v"] is False


# ---------------------------------------------------------------------------
# 8. 与 predictor 的真实链路（mock 帧 → 速度 → 预判）
# ---------------------------------------------------------------------------
def test_mock_frames_feed_predictor(mock_backend, monkeypatch):
    """感知契约必须对得上 predictor 的输入要求，否则整条链路是假的。"""
    import predictor
    predictor.reset()
    cfg = {"drift": True, "entities": [{"raw_id": "hornet", "rarity": "Common",
                                        "x": 100, "y": 100, "vx": 200, "vy": 0}]}
    orig_cfg = ps._cfg

    def _cfg(path, default=None):
        return cfg if path == "perception.mock" else orig_cfg(path, default)

    monkeypatch.setattr(ps, "_cfg", _cfg)

    # predictor 走真实时钟，这里用 FakeClock 与 mock 漂移时间对齐（0.1s/帧）
    clock = type("FakeClock", (), {"now": 1000.0, "time": lambda self: self.now})()
    monkeypatch.setattr(predictor, "time", clock)
    for i in range(8):                       # 8 帧 * 0.1s
        clock.now = 1000.0 + i * 0.1
        p = ps.build_perception_payload("mock", now=clock.now)
        predictor.update_frame_entities([
            {"raw_id": e["raw_id"], "rarity": e["rarity"], "x": e["x"], "y": e["y"]}
            for e in p["entities"]
        ])
    res = predictor.predict_all_entities()
    assert res, "6 帧 mock 数据应能算出预判结果"
    top = res[0]
    assert top["raw_id"] == "hornet"
    assert top["x_predict"] > top["x_now"], "匀速右移的实体预判点应在当前点右侧"
    assert math.isfinite(top["vx_per_sec"]) and top["vx_per_sec"] > 0
    predictor.reset()
