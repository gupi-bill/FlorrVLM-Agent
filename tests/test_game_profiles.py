#!/usr/bin/env python3
"""
S10 · 游戏档案体系固化 —— tests/test_game_profiles.py
=====================================================
锁三件事：
  1. 校验器能挡住"语义错"的档案（不只是缺字段）；
  2. 切换 agent.game 后，核心模块从 config 读到的是**新游戏**的值（核心零改动的证据）；
  3. tools/add_game.py 生成的档案「生成即通过 validate」（strict 口径零错误零建议）。

全部用例走 tmp_path / monkeypatch，不污染 game_profiles/ 与 config.yaml。
"""
import os
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
import game_profile_check as gpc  # noqa: E402
from tools import add_game  # noqa: E402

# 一份"最小合法档案"，用例按需改坏其中一处
BASE_PROFILE = {
    "game": {"name": "good_game", "description": "一份用于测试的合法档案"},
    "server": {"perception_port": 5021},
    "predictor": {
        "rarity_highest_boss": ["Unique"],
        "rarity_boss": ["Super"],
        "rarity_elite": ["Ultra"],
        "rarity_normal": ["Common"],
        "threat": {"highest_boss": 1000, "boss": 400, "elite": 120, "normal": 15,
                   "player_enemy": 150, "player_ally": 0, "unknown": 5},
    },
    "combat": {
        "chase_min_category": "elite",
        "default_set": "combat",
        "sets": ["combat", "tank", "retreat"],
        "tactics": ["低血量先撤"],
    },
    "perception": {"mock": {"entities": [
        {"raw_id": "Unique", "rarity": "Unique", "x": 100, "y": 100, "vx": 10, "vy": 0},
    ]}},
}


def _write(tmp_path, name: str, data, sync: bool = True) -> None:
    """把 dict（或原始文本）写成 game_profiles/<name>.yaml。

    默认把 game.name 同步成文件名（合法档案本就该一致）；
    要造"名字不一致"的坏档案时传 sync=False。
    """
    path = tmp_path / f"{name}.yaml"
    if isinstance(data, dict) and sync and isinstance(data.get("game"), dict):
        data["game"]["name"] = name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


@pytest.fixture
def profiled(tmp_path, monkeypatch):
    """把校验器的档案目录指到 tmp_path，用例只看到自己写的档案。"""
    monkeypatch.setattr(gpc, "PROFILE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def real_profiles(monkeypatch):
    """把 config 的档案目录指向仓库真实 game_profiles/，并在结束后还原配置树。"""
    monkeypatch.setattr(config, "PROFILE_DIR", os.path.join(ROOT, "game_profiles"))
    yield
    monkeypatch.undo()
    config._reload()


# --------------------------------------------------------------------------
# 一、真实档案必须通过（含 strict 口径）
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["florr", "space_invaders"])
def test_real_profiles_pass(name):
    detail = gpc.check_detail(name)
    assert detail["errors"] == [], f"{name} 不应有 ERROR: {detail['errors']}"
    assert detail["ok"] is True


@pytest.mark.parametrize("name", ["florr", "space_invaders"])
def test_real_profiles_pass_strict(name):
    """strict 口径下连建议项都不许有（S10 已补齐 sets/tactics/port）。"""
    detail = gpc.check_detail(name)
    assert detail["warnings"] == [], f"{name} 仍有建议项: {detail['warnings']}"


def test_check_all_real_profiles():
    ok, results = gpc.check_all(strict=True)
    names = [n for n, _ in results]
    assert "florr" in names and "space_invaders" in names
    assert ok is True


# --------------------------------------------------------------------------
# 二、校验器能挡住的语义错误
# --------------------------------------------------------------------------

def test_valid_profile_has_no_problem(profiled):
    _write(profiled, "good_game", BASE_PROFILE)
    detail = gpc.check_detail("good_game")
    assert (detail["ok"], detail["errors"], detail["warnings"]) == (True, [], [])


def test_duplicate_rarity_across_tiers(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["predictor"]["rarity_boss"] = ["Ultra"]  # Ultra 已在 elite 档
    _write(profiled, "good_game", data)
    detail = gpc.check_detail("good_game")
    assert detail["ok"] is False
    assert any("分档自相矛盾" in e for e in detail["errors"])


@pytest.mark.parametrize("hi,lo", [(100, 400), (10, 20)])
def test_inverted_threat_pyramid(profiled, hi, lo):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["predictor"]["threat"]["highest_boss"] = hi
    data["predictor"]["threat"]["boss"] = lo
    _write(profiled, "good_game", data)
    detail = gpc.check_detail("good_game")
    assert any("金字塔倒置" in e for e in detail["errors"])


def test_negative_threat(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["predictor"]["threat"]["elite"] = -1
    _write(profiled, "good_game", data)
    assert any("为负数" in e for e in gpc.check_detail("good_game")["errors"])


def test_name_mismatch_with_filename(profiled):
    _write(profiled, "good_game", BASE_PROFILE)  # game.name 是 good_game
    other = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    other["game"]["name"] = "another_name"
    _write(profiled, "good_game", other, sync=False)
    assert any("不一致" in e for e in gpc.check_detail("good_game")["errors"])


def test_unknown_top_level_key(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["predctor"] = {}  # 拼写错误
    _write(profiled, "good_game", data)
    assert any("未知顶层键" in e for e in gpc.check_detail("good_game")["errors"])


def test_default_set_not_in_sets(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["combat"]["default_set"] = "not_declared"
    _write(profiled, "good_game", data)
    assert any("不在 combat.sets" in e for e in gpc.check_detail("good_game")["errors"])


def test_sets_must_be_nonempty_str_list(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["combat"]["sets"] = [1, 2]
    _write(profiled, "good_game", data)
    assert any("combat.sets" in e for e in gpc.check_detail("good_game")["errors"])


def test_mock_rarity_not_declared(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["perception"]["mock"]["entities"][0]["rarity"] = "Ghost"
    _write(profiled, "good_game", data)
    assert any("不属于任何已声明档位" in e for e in gpc.check_detail("good_game")["errors"])


def test_missing_threat_key(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["predictor"]["threat"].pop("unknown")
    _write(profiled, "good_game", data)
    assert any("predictor.threat.unknown" in e for e in gpc.check_detail("good_game")["errors"])


def test_missing_profile_and_broken_yaml(profiled):
    detail = gpc.check_detail("nope")
    assert detail["ok"] is False and "档案不存在" in detail["errors"][0]
    _write(profiled, "good_game", "game:\n  name: [unclosed\n")
    assert any("YAML 语法错误" in e for e in gpc.check_detail("good_game")["errors"])


def test_root_must_be_mapping(profiled):
    _write(profiled, "good_game", "- 1\n- 2\n")
    assert any("根节点必须是映射" in e for e in gpc.check_detail("good_game")["errors"])


def test_recommended_fields_are_warnings_only(profiled):
    """缺 description / port / sets / tactics 只降级为建议，不阻断。"""
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data["game"].pop("description")
    data.pop("server")
    data["combat"].pop("sets")
    data["combat"].pop("default_set")
    data["combat"].pop("tactics")
    _write(profiled, "good_game", data)
    detail = gpc.check_detail("good_game")
    assert detail["ok"] is True and len(detail["warnings"]) == 4


# --------------------------------------------------------------------------
# 三、check_all / check_one 的口径（修掉"退出码永远 0"）
# --------------------------------------------------------------------------

def test_check_all_fails_when_one_profile_broken(profiled):
    _write(profiled, "a_game", BASE_PROFILE)
    bad = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    bad["game"]["name"] = "b_game"
    bad["predictor"]["threat"]["boss"] = 9999  # boss > highest_boss → 倒置
    _write(profiled, "b_game", bad)
    ok, results = gpc.check_all()
    assert ok is False
    assert [n for n, _ in results] == ["a_game", "b_game"]


def test_check_all_skips_template_files(profiled):
    _write(profiled, "_template", {"game": {"name": "x"}})
    _write(profiled, "a_game", BASE_PROFILE)
    ok, results = gpc.check_all()
    assert ok is True and [n for n, _ in results] == ["a_game"]


def test_check_all_strict_counts_warnings(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data.pop("server")
    _write(profiled, "a_game", data)
    assert gpc.check_all(strict=False)[0] is True
    assert gpc.check_all(strict=True)[0] is False


def test_check_one_backward_compat(profiled):
    data = yaml.safe_load(yaml.safe_dump(BASE_PROFILE, allow_unicode=True))
    data.pop("server")
    _write(profiled, "a_game", data)
    ok, problems = gpc.check_one("a_game")
    assert ok is True
    assert any(p.startswith(gpc.WARN_PREFIX) for p in problems)


def test_report_all_text(profiled):
    _write(profiled, "a_game", BASE_PROFILE)
    text = gpc.report_all(strict=True)
    assert "✅ 全部档案通过" in text and "[✅] a_game" in text


# --------------------------------------------------------------------------
# 四、切换游戏 = 核心读到新值（"核心零改动"的实证）
# --------------------------------------------------------------------------

def _switch(tmp_path, monkeypatch, game: str):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"agent:\n  game: {game}\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config, "TUNED_PATH", str(tmp_path / "no_tuned.yaml"))
    config._reload()


def test_switch_game_changes_core_values(tmp_path, monkeypatch, real_profiles):
    _switch(tmp_path, monkeypatch, "space_invaders")
    assert config.get("predictor.threat.boss") == 800
    assert config.get("predictor.rarity_highest_boss") == ["mothership"]
    assert config.get("server.perception_port") == 5011
    assert config.get("combat.sets") == ["shoot", "dodge", "focus_mothership"]

    _switch(tmp_path, monkeypatch, "florr")
    assert config.get("predictor.threat.boss") == 400
    assert config.get("predictor.rarity_highest_boss") == ["Unique", "Eternal"]
    assert config.get("server.perception_port") == 5001
    assert "retreat" in config.get("combat.sets")


def test_profile_merge_replaces_lists_not_concat(tmp_path, monkeypatch, real_profiles):
    """切回 florr 后 rarity 列表不能残留上一款游戏的取值（_merge 必须是替换）。"""
    _switch(tmp_path, monkeypatch, "space_invaders")
    _switch(tmp_path, monkeypatch, "florr")
    assert config.get("predictor.rarity_normal") == ["Rare", "Unusual", "Common"]


def test_profile_does_not_leak_sets(tmp_path, monkeypatch, real_profiles):
    _switch(tmp_path, monkeypatch, "space_invaders")
    assert "shoot" in config.get("combat.sets")
    _switch(tmp_path, monkeypatch, "florr")
    assert "shoot" not in config.get("combat.sets")


# --------------------------------------------------------------------------
# 五、tools/add_game.py：生成即通过 validate
# --------------------------------------------------------------------------

def test_generated_profile_passes_strict(tmp_path, monkeypatch):
    monkeypatch.setattr(add_game, "PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(gpc, "PROFILE_DIR", str(tmp_path))
    monkeypatch.setenv("UGF_NONINTERACTIVE", "1")
    text = add_game.render_yaml(add_game.collect("gen_game"))
    (tmp_path / "gen_game.yaml").write_text(text, encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["game"]["name"] == "gen_game"
    assert isinstance(data["server"]["perception_port"], int)
    assert data["combat"]["default_set"] in data["combat"]["sets"]
    assert data["combat"]["tactics"]
    assert data["perception"]["mock"]["entities"]
    detail = gpc.check_detail("gen_game")
    assert (detail["ok"], detail["errors"], detail["warnings"]) == (True, [], [])


def test_generated_mock_rarities_are_declared(tmp_path, monkeypatch):
    monkeypatch.setenv("UGF_NONINTERACTIVE", "1")
    text = add_game.render_yaml(add_game.collect("gen_game2"))
    data = yaml.safe_load(text)
    declared = set()
    for key in gpc.RARITY_TIERS:
        declared |= set(data["predictor"][key])
    for ent in data["perception"]["mock"]["entities"]:
        assert ent["rarity"] in declared


def test_generator_escapes_special_characters(monkeypatch):
    """描述里带冒号/引号也不能把 YAML 写坏。"""
    monkeypatch.setenv("UGF_NONINTERACTIVE", "1")
    data = add_game.collect("gen_game3")
    data["description"] = '带: 冒号 与 "引号" 的描述'
    data["tactics"] = ['先: 撤', '再 "打"']
    parsed = yaml.safe_load(add_game.render_yaml(data))
    assert parsed["game"]["description"] == data["description"]
    assert parsed["combat"]["tactics"] == data["tactics"]


@pytest.mark.parametrize("raw,expect", [
    ("my game!", "my_game"),
    ("../../evil", "evil"),
    ("ok_name", "ok_name"),
    ("", "florr"),
])
def test_sanitize_name(raw, expect):
    assert add_game._sanitize_name(raw) == expect


def test_next_port_avoids_used(tmp_path, monkeypatch):
    monkeypatch.setattr(add_game, "PROFILE_DIR", str(tmp_path))
    _write(tmp_path, "a", {"server": {"perception_port": 5011}})
    _write(tmp_path, "b", {"server": {"perception_port": 5021}})
    assert add_game._next_port() == 5031


def test_activate_game_only_touches_agent_block(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("game:\n  title: 全局标题\nagent:\n  game: florr\n", encoding="utf-8")
    monkeypatch.setattr(add_game, "CONFIG_PATH", str(cfg))
    msg = add_game.activate_game("space_invaders")
    text = cfg.read_text(encoding="utf-8")
    assert "已切换" in msg
    assert "title: 全局标题" in text  # 未被误改
    assert yaml.safe_load(text)["agent"]["game"] == "space_invaders"


def test_activate_game_noop_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(add_game, "CONFIG_PATH", str(tmp_path / "missing.yaml"))
    assert "不存在" in add_game.activate_game("x")


def test_selfcheck_reports_problems(tmp_path, monkeypatch):
    monkeypatch.setattr(gpc, "PROFILE_DIR", str(tmp_path))
    _write(tmp_path, "gen_game", BASE_PROFILE)
    ok, problems = add_game.selfcheck("gen_game")
    assert ok is True and problems == []
    _write(tmp_path, "gen_game", {"game": {"name": "gen_game"}})
    ok2, problems2 = add_game.selfcheck("gen_game")
    assert ok2 is False and problems2
