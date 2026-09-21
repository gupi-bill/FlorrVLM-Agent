#!/usr/bin/env python3
"""
S15 · 第二款游戏端到端跑通（space_invaders）

这是「Universal」这个词的第一次实证：同一套核心代码，只换 `AGENT_GAME`，
detect → brief → research → ensure → play → report 全链路必须跑出**属于该游戏**的产物
（实体、套装、端口、知识库分区），而不是换了个名字却仍在跑 florr 的数据。

本文件锁定的四个真实缺陷（均为 S15 实测发现，退出码 0 但结果错误）：
1. `config._reload()` 不认 `AGENT_GAME` 环境变量 → 文档声称的切游戏方式实际无效。
2. `agent_main._mcp_server_env()` 只透传 `UGF_*` → MCP 子进程丢掉游戏名，
   父进程按 space_invaders 决策、子进程按 florr 出数据（跨进程口径不一致）。
3. `mcp_server.SET_TO_KEY` 硬编码 florr 五个套装名 → 其它游戏 `switch_set` 必然失败。
4. 知识库写入不带 `game_name` → 多游戏共用一份知识库，经验互相污染。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

PY = sys.executable


@pytest.fixture
def si(monkeypatch):
    """切到 space_invaders 并强制重载配置。"""
    monkeypatch.setenv("AGENT_GAME", "space_invaders")
    monkeypatch.delenv("UGF_GAME", raising=False)
    config._reload()
    return config


# ---------------------------------------------------------------------------
# 1. 游戏选择：环境变量必须真正生效
# ---------------------------------------------------------------------------
def test_active_game_env_wins_over_config_yaml(monkeypatch):
    monkeypatch.setenv("AGENT_GAME", "space_invaders")
    assert config.active_game() == "space_invaders"

    monkeypatch.delenv("AGENT_GAME", raising=False)
    monkeypatch.setenv("UGF_GAME", "space_invaders")
    assert config.active_game() == "space_invaders"

    monkeypatch.delenv("AGENT_GAME", raising=False)
    monkeypatch.delenv("UGF_GAME", raising=False)
    assert config.active_game() == (config._read_yaml(config.CONFIG_PATH)
                                    .get("agent", {}).get("game", "florr"))


def test_env_switch_actually_loads_second_profile(si):
    """环境变量切游戏后，核心读到的必须全是第二款游戏的值。"""
    assert config.get("game.name") == "space_invaders"
    assert config.get("predictor.threat.boss") == 800
    assert config.get("predictor.rarity_highest_boss") == ["mothership"]
    assert config.get("server.perception_port") == 5011
    assert config.get("combat.sets") == ["shoot", "dodge", "focus_mothership"]


def test_mock_scene_comes_from_profile(si):
    """离线场景属于档案，不是通用配置（PROFILE_SPEC §7 移交项）。"""
    raw = [e["raw_id"] for e in config.get("perception.mock.entities", [])]
    assert "mothership" in raw and "alien_swarmer" in raw
    assert "hornet" not in raw          # florr 的实体不能串进来
    # 单人街机：档案已显式置空，不能继承到 DEFAULT 的队友
    assert config.get("perception.mock.teammates", []) == []


@pytest.mark.parametrize("game,port", [("florr", 5001), ("space_invaders", 5011)])
def test_each_game_has_own_perception_port(monkeypatch, game, port):
    monkeypatch.setenv("AGENT_GAME", game)
    config._reload()
    assert config.get("server.perception_port") == port


# ---------------------------------------------------------------------------
# 2. MCP 子进程：游戏名必须透传
# ---------------------------------------------------------------------------
def test_mcp_server_env_forwards_game(monkeypatch):
    monkeypatch.setenv("AGENT_GAME", "space_invaders")
    import importlib
    import agent_main
    importlib.reload(agent_main)
    env = agent_main._mcp_server_env()
    assert env.get("AGENT_GAME") == "space_invaders"


def test_mcp_server_env_matches_parent_when_only_config_yaml(monkeypatch):
    """即使不靠透传，子进程拿到的也应是父进程已解析的激活游戏。"""
    monkeypatch.delenv("AGENT_GAME", raising=False)
    monkeypatch.delenv("UGF_GAME", raising=False)
    import importlib
    import agent_main
    importlib.reload(agent_main)
    assert agent_main._mcp_server_env()["AGENT_GAME"] == config.active_game()


# ---------------------------------------------------------------------------
# 3. 套装：键位映射与决策语义翻译都必须按档案走
# ---------------------------------------------------------------------------
def test_set_keys_follow_profile(si):
    import mcp_server
    assert mcp_server.resolve_set_keys() == {
        "shoot": "1", "dodge": "2", "focus_mothership": "3"}


def test_set_keys_backward_compatible_with_florr(monkeypatch):
    monkeypatch.setenv("AGENT_GAME", "florr")
    config._reload()
    import mcp_server
    keys = mcp_server.resolve_set_keys()
    assert keys == {"combat": "1", "tank": "2", "retreat": "3",
                    "chase": "4", "team": "5"}


def test_decision_set_names_are_translated_by_set_map(si):
    """combat_judge 输出的抽象名必须能落到本游戏的真实套装上。"""
    import mcp_server
    assert mcp_server.normalize_set_name("combat") == "shoot"
    assert mcp_server.normalize_set_name("retreat") == "dodge"
    assert mcp_server.normalize_set_name("chase") == "focus_mothership"
    assert mcp_server.normalize_set_name("shoot") == "shoot"   # 本名直通
    assert mcp_server.normalize_set_name("nope") is None
    assert mcp_server.normalize_set_name("") is None


def test_switch_set_works_for_second_game(si, monkeypatch):
    """换套在 dry-run 下必须落到本游戏套装，而不是「未知套装」。"""
    monkeypatch.setenv("UGF_DRY_RUN", "1")   # 无头环境无真实键鼠，走 dry-run 分支
    import mcp_server
    out = mcp_server.switch_set.fn("retreat") if hasattr(mcp_server.switch_set, "fn") \
        else mcp_server.switch_set("retreat")
    assert "未知套装" not in out
    assert "dodge" in out


def test_profile_declares_valid_set_map(si):
    mapping = config.get("combat.set_map")
    assert isinstance(mapping, dict) and mapping
    sets = config.get("combat.sets")
    assert set(mapping.values()) <= set(sets)


# ---------------------------------------------------------------------------
# 4. 档案校验
# ---------------------------------------------------------------------------
def test_second_profile_passes_strict_check():
    r = subprocess.run([PY, os.path.join(ROOT, "game_profile_check.py"),
                        "space_invaders", "--strict"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# 5. 端到端：真实子进程跑完一个生命周期
# ---------------------------------------------------------------------------
def test_e2e_second_game_dry_run(tmp_path):
    """
    `AGENT_GAME=space_invaders` 下真实跑主循环，断言退出码 0 且各阶段产物非空、
    且产物内容是**这款游戏**的（实体名 / 套装名 / 知识库分区）。
    """
    env = {**os.environ,
           "AGENT_GAME": "space_invaders",
           "UGF_DRY_RUN": "1",
           "UGF_PERCEPTION_BACKEND": "mock"}
    r = subprocess.run([PY, os.path.join(ROOT, "agent_main.py"), "--rounds", "2"],
                       cwd=ROOT, capture_output=True, text=True,
                       timeout=180, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Traceback" not in r.stdout + r.stderr

    # 主循环真的按 space_invaders 的感知数据在跑
    assert "回合 1" in r.stdout or "回合1" in r.stdout

    # 知识库按游戏分区：复盘必须落在 knowledge_md/space_invaders/ 下
    kb_dir = os.path.join(ROOT, "knowledge_md", "space_invaders")
    assert os.path.isdir(kb_dir), f"未生成游戏知识库分区: {kb_dir}"
    reviews = [f for f in os.listdir(kb_dir) if f.startswith("review_")]
    assert reviews, f"复盘未写入: {os.listdir(kb_dir)}"

    body = open(os.path.join(kb_dir, sorted(reviews)[-1]), encoding="utf-8").read()
    # 产物内容必须是本游戏语义，而不是 florr 的 hornet/mantis
    assert ("alien_swarmer" in body or "mothership" in body or "alien_boss" in body)
    assert "hornet" not in body and "mantis" not in body
    assert "shoot" in body          # 本游戏套装名
