#!/usr/bin/env python3
"""
S7 · 主循环 dry-run 测试（tests/test_agent_main.py）

覆盖两条主线：
1. agent_main 的可离线判定的纯逻辑（开关解析 / 工具返回解析 / 兜底决策 / 复盘过滤 /
   BOSS 行为归纳 / 日志滚动与清理 / 配置热加载与环境变量覆盖）。
2. mcp_server 的 dry-run 降级分支（进程内 mock 感知、键鼠动作只记录不执行），
   以及"主循环用到的工具必须真的注册过"这一回归锁（kb_append 曾漏注册导致静默失败）。

约束：全程离线，不调真实 LLM / 不发真实网络请求 / 不碰键鼠；
落盘一律重定向到 tmp_path，run_logs 不留测试垃圾。
"""
import asyncio
import gzip
import importlib
import json
import os
import time

import pytest

import agent_main
import mcp_server
import perception_server
import predictor


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_predictor():
    """predictor 是模块级全局状态，用例之间必须隔离。"""
    predictor.reset()
    perception_server.reset_mock()
    yield
    predictor.reset()
    perception_server.reset_mock()


@pytest.fixture
def dryrun_env(monkeypatch):
    """打开 dry-run 并重新加载 agent_main，使模块级 DRY_RUN 生效。"""
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    importlib.reload(agent_main)
    yield
    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    importlib.reload(agent_main)


@pytest.fixture
def dryrun_server(monkeypatch):
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    assert mcp_server.dry_run() is True
    yield


@pytest.fixture
def tmp_logs(monkeypatch, tmp_path):
    """把 dry-run 动作日志与滚动日志都重定向到临时目录。"""
    logs = tmp_path / "run_logs"
    logs.mkdir()
    real_get = mcp_server.config.get

    def fake_get(path, default=None):
        if path == "paths.run_logs":
            return str(logs)
        return real_get(path, default)

    monkeypatch.setattr(mcp_server.config, "get", fake_get)
    return logs


# ---------------------------------------------------------------------------
# 1. 环境变量开关解析
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("no", False), ("random", False),
])
def test_env_flag(monkeypatch, raw, expected):
    monkeypatch.setenv("UGF_TEST_FLAG", raw)
    assert agent_main._env_flag("UGF_TEST_FLAG") is expected


def test_env_flag_missing_uses_default():
    assert agent_main._env_flag("UGF_NOT_SET_XYZ", True) is True
    assert agent_main._env_flag("UGF_NOT_SET_XYZ") is False


@pytest.mark.parametrize("raw,expected", [("3", 3), (" 7 ", 7), ("0", 0), ("-2", -2)])
def test_int_env_valid(monkeypatch, raw, expected):
    monkeypatch.setenv("UGF_TEST_INT", raw)
    assert agent_main._int_env("UGF_TEST_INT", 99) == expected


@pytest.mark.parametrize("raw", ["", "abc", "1.5"])
def test_int_env_invalid_falls_back(monkeypatch, raw):
    monkeypatch.setenv("UGF_TEST_INT", raw)
    assert agent_main._int_env("UGF_TEST_INT", 24) == 24


def test_int_env_missing_falls_back(monkeypatch):
    monkeypatch.delenv("UGF_TEST_INT", raising=False)
    assert agent_main._int_env("UGF_TEST_INT", 12) == 12
    assert agent_main._int_env("UGF_TEST_INT", None) == 0


def test_dry_run_flag_reload(dryrun_env):
    assert agent_main.DRY_RUN is True


def test_dry_run_off_by_default():
    assert agent_main.DRY_RUN is False


# ---------------------------------------------------------------------------
# 2. MCP 返回解析（不同 SDK 形状 / 软失败检测）
# ---------------------------------------------------------------------------
class _C:
    def __init__(self, text):
        self.text = text


class _R:
    def __init__(self, text):
        self.content = [_C(text)] if text is not None else []


def test_tool_text_normal():
    assert agent_main._tool_text(_R("hello")) == "hello"


def test_tool_text_empty_content():
    assert agent_main._tool_text(_R(None)) == ""


def test_tool_text_plain_object():
    assert agent_main._tool_text("raw-string") == "raw-string"


@pytest.mark.parametrize("text,key,expected", [
    ('{"_reason": "yolo_timeout", "_error": "慢"}', "_reason", "_reason=yolo_timeout"),
    ('{"_skipped": true}', "_reason", ""),
    ('not json', "_reason", ""),
    ('[1,2]', "_reason", ""),
])
def test_json_fields(text, key, expected):
    assert agent_main._json_fields(text, key) == expected


def test_json_fields_multiple_keys():
    out = agent_main._json_fields('{"a": 1, "b": 2, "c": null}', "a", "b", "c")
    assert "a=1" in out and "b=2" in out and "c" not in out


@pytest.mark.parametrize("text,hit", [
    ("Unknown tool: kb_append", True),
    ("Tool 'kb_write' failed: boom", True),
    ("已写入知识库: x.md", False),
    ("[dry-run] 动作已记录（未真实执行）: attack", False),
])
def test_tool_error(text, hit):
    assert bool(agent_main._tool_error(_R(text))) is hit


# ---------------------------------------------------------------------------
# 3. 兜底决策 / 复盘过滤 / BOSS 行为归纳
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("state,eval_str,expected", [
    ('{"afk_popup": true}', '{"decision":"fight"}', "idle"),
    ('{"afk_popup": false}', '{"decision":"retreat"}', "defend"),
    ('{"afk_popup": false}', '{"decision":"cautious_fight"}', "attack"),
    ('{"afk_popup": false}', '{"decision":"fight"}', "attack"),
    ('{"afk_popup": false}', 'not-json', "attack"),
])
def test_fallback_decide(state, eval_str, expected):
    assert agent_main._fallback_decide(state, eval_str)["action"] == expected


def test_fallback_decide_bad_state():
    assert agent_main._fallback_decide("not-json", "{}") == {"action": "idle"}


@pytest.mark.parametrize("state,teammate,expected", [
    ({"entities": [{"rarity": "Super"}]}, False, True),
    ({"entities": [{"category": "boss"}]}, False, True),
    ({"entities": [{"rarity": "Common"}]}, False, False),
    ({"entities": [{"rarity": "Common"}]}, True, True),
    ({}, False, False),
])
def test_should_review(state, teammate, expected):
    assert agent_main._should_review(state, teammate) is expected


def test_analyze_boss_behavior_insufficient():
    assert "样本不足" in agent_main._analyze_boss_behavior([(0, 0, 10, 10)])


def test_analyze_boss_behavior_straight():
    samples = [(100 + i * 50, 100, 500, 500) for i in range(6)]
    out = agent_main._analyze_boss_behavior(samples)
    assert "直线移动" in out and "平均距离玩家约" in out


def test_analyze_boss_behavior_circling():
    import math
    samples = [(500 + 200 * math.cos(i), 500 + 200 * math.sin(i), 500, 500)
               for i in range(12)]
    assert "绕圈" in agent_main._analyze_boss_behavior(samples)


def test_analyze_boss_behavior_close_count(monkeypatch):
    monkeypatch.setattr(agent_main, "BOSS_CLOSE_DIST", 1000)
    samples = [(100, 100, 120, 120) for _ in range(4)]
    assert "近距离接近 4 次" in agent_main._analyze_boss_behavior(samples)


# ---------------------------------------------------------------------------
# 4. 滚动日志 / 过期清理
# ---------------------------------------------------------------------------
def test_log_cleanup_removes_old(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_main, "LOG_DIR", str(tmp_path))
    old = tmp_path / "agent_20200101.log"
    new = tmp_path / "agent_20990101.log"
    other = tmp_path / "keepme.txt"
    for p in (old, new, other):
        p.write_text("x", encoding="utf-8")
    os.utime(old, (time.time() - 30 * 86400, time.time() - 30 * 86400))
    agent_main._log_cleanup(days=7)
    assert not old.exists()
    assert new.exists() and other.exists()


def test_maybe_rotate_compresses(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_main, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(agent_main, "LOG_MAX_SIZE", 100)
    daily = tmp_path / f"agent_{time.strftime('%Y%m%d')}.log"
    daily.write_text("x" * 500, encoding="utf-8")
    agent_main._maybe_rotate()
    assert not daily.exists()
    gz = [p for p in tmp_path.iterdir() if p.suffix == ".gz"]
    assert gz and gzip.open(gz[0], "rt", encoding="utf-8").read() == "x" * 500


def test_maybe_rotate_keeps_small(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_main, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(agent_main, "LOG_MAX_SIZE", 10 * 1024 * 1024)
    daily = tmp_path / f"agent_{time.strftime('%Y%m%d')}.log"
    daily.write_text("x", encoding="utf-8")
    agent_main._maybe_rotate()
    assert daily.exists()


# ---------------------------------------------------------------------------
# 5. 热加载与子进程环境透传
# ---------------------------------------------------------------------------
def test_reload_config_env_overrides(monkeypatch):
    monkeypatch.setenv("UGF_REPORT_EVERY", "3")
    monkeypatch.setenv("UGF_LEARN_EVERY", "5")
    agent_main.reload_config()
    assert agent_main.REPORT_EVERY == 3
    assert agent_main.LEARNING_STATS_INTERVAL == 5
    monkeypatch.delenv("UGF_REPORT_EVERY")
    monkeypatch.delenv("UGF_LEARN_EVERY")
    agent_main.reload_config()
    assert agent_main.REPORT_EVERY == 0


def test_mcp_server_env_forwards_ugf(monkeypatch):
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "mock")
    env = agent_main._mcp_server_env()
    assert env.get("UGF_PERCEPTION_BACKEND") == "mock"
    assert "PATH" in env


def test_mcp_server_env_sets_dryrun(dryrun_env):
    assert agent_main._mcp_server_env().get("UGF_DRY_RUN") == "1"


# ---------------------------------------------------------------------------
# 6. MCP 服务端 dry-run 降级
# ---------------------------------------------------------------------------
REQUIRED_TOOLS = [
    "kb_list", "kb_search", "kb_write", "kb_append",
    "perceive_game", "predict_all_entities", "reset_predictor",
    "game_action", "switch_set",
]


def _registered_tools():
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


@pytest.mark.parametrize("name", REQUIRED_TOOLS)
def test_required_tool_registered(name):
    """回归锁：主循环用到的工具必须真被注册（kb_append 曾漏注册 → 静默失败）。"""
    assert name in _registered_tools()


def test_kb_append_now_registered():
    assert "kb_append" in _registered_tools()


@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("true", True), ("0", False), ("off", False),
])
def test_server_dry_run_flag(monkeypatch, raw, expected):
    monkeypatch.setenv("UGF_DRY_RUN", raw)
    assert mcp_server.dry_run() is expected


@pytest.mark.parametrize("action", ["attack", "defend", "synthesize", "idle"])
def test_game_action_dryrun_no_real_input(dryrun_server, tmp_logs, action):
    out = mcp_server.game_action(action)
    assert out.startswith("[dry-run]") and action in out


def test_game_action_dryrun_move(dryrun_server, tmp_logs):
    out = mcp_server.game_action("MOVE", 123, 456)
    assert "[dry-run]" in out and "(123,456)" in out


def test_game_action_dryrun_move_without_coords(dryrun_server, tmp_logs):
    assert "必须提供" in mcp_server.game_action("move")


def test_game_action_dryrun_writes_log(dryrun_server, tmp_logs):
    mcp_server.game_action("attack")
    log_file = tmp_logs / "dryrun_actions.log"
    assert log_file.exists()
    assert "attack" in log_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("set_name,key", [
    ("combat", "1"), ("tank", "2"), ("retreat", "3"), ("chase", "4"), ("team", "5"),
])
def test_switch_set_dryrun(dryrun_server, tmp_logs, set_name, key):
    out = mcp_server.switch_set(set_name)
    assert "[dry-run]" in out and key in out


def test_switch_set_unknown(dryrun_server, tmp_logs):
    assert "未知套装" in mcp_server.switch_set("nuke")


def test_inproc_perception():
    data = mcp_server._inproc_perception()
    assert data["_fallback"] == "inproc-mock"
    assert len(data["entities"]) == 5
    assert data["player"]["alive"] is True


def test_inproc_perception_carries_reason():
    assert mcp_server._inproc_perception("boom")["_fallback_reason"] == "boom"


def test_perceive_game_dryrun_falls_back(monkeypatch, dryrun_server, tmp_logs):
    def boom(*a, **k):
        raise mcp_server.requests.ConnectionError("no server")

    monkeypatch.setattr(mcp_server.requests, "get", boom)
    out = json.loads(mcp_server.perceive_game())
    assert out["_fallback"] == "inproc-mock"
    assert len(out["entities"]) == 5


def test_perceive_game_nondryrun_reports_error(monkeypatch):
    def boom(*a, **k):
        raise mcp_server.requests.ConnectionError("no server")

    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    monkeypatch.setattr(mcp_server.requests, "get", boom)
    out = json.loads(mcp_server.perceive_game())
    assert "感知服务未启动" in out["error"]


def test_perceive_game_feeds_predictor(monkeypatch, dryrun_server, tmp_logs):
    """感知 → 预判必须真的连上：多帧后能算出带速度的预判。"""
    def boom(*a, **k):
        raise mcp_server.requests.ConnectionError("no server")

    monkeypatch.setattr(mcp_server.requests, "get", boom)
    for _ in range(6):
        json.loads(mcp_server.perceive_game())
    preds = json.loads(mcp_server.predict_all_entities())
    assert isinstance(preds, list) and preds
    assert any(p.get("raw_id") for p in preds)


def test_mock_entities_actually_drift():
    """回归锁：mock 实体的位移必须随累计时间推进（修复前恒等于一帧增量）。"""
    perception_server.reset_mock()
    a = perception_server.mock_detections(now=1000.0)
    b = perception_server.mock_detections(now=1003.0)
    c = perception_server.mock_detections(now=1006.0)
    pos = {"a": a, "b": b, "c": c}
    moved = 0
    for e in b["entities"]:
        xa = pos["a"]["entities"][[x["raw_id"] for x in a["entities"]].index(e["raw_id"])]["x"]
        xc = pos["c"]["entities"][[x["raw_id"] for x in c["entities"]].index(e["raw_id"])]["x"]
        if abs(xc - xa) > 1:
            moved += 1
    assert moved >= 3, f"仅 {moved} 个实体在 6 秒内移动，mock 漂移仍未累积"
