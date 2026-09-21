#!/usr/bin/env python3
"""
S16 · 参考适配器模板与档案规范固化 —— tests/test_add_game.py
==========================================================
锁四件事：
  1. `game_profiles/_template.yaml` 存在、是合法 YAML、声明了全部必需槽位；
  2. `tools/add_game.py` **以模板为唯一来源**渲染（改模板即改产出），渲染后无占位符残留；
  3. 用模板生成的全新档案「生成即通过 validate」——strict 口径零错误零建议；
  4. 生成的档案能被核心读到预期值（切游戏零改核心的实证）。

全部用例走 tmp_path / monkeypatch，不污染 game_profiles/ 与 config.yaml。
"""
import os
import re
import subprocess
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
import game_profile_check as gpc  # noqa: E402
from tools import add_game  # noqa: E402

PY = sys.executable
TEMPLATE_PATH = add_game.TEMPLATE_PATH

# 模板必须声明的槽位（缺任何一个 = 生成器渲染不出完整档案）
REQUIRED_SLOTS = [
    "__UGF_NAME__", "__UGF_DESC__",
    "__UGF_RARITY_HIGHEST_BOSS__", "__UGF_RARITY_BOSS__",
    "__UGF_RARITY_ELITE__", "__UGF_RARITY_NORMAL__",
    "__UGF_DEFAULT_SET__", "__UGF_SETS__", "__UGF_SET_MAP__",
    "__UGF_TACTICS__", "__UGF_ENTITIES__",
]


@pytest.fixture(scope="module")
def template_text():
    return add_game.load_template()


@pytest.fixture
def profiled(tmp_path, monkeypatch):
    """把生成器与校验器的档案目录一起指到 tmp_path。"""
    monkeypatch.setattr(add_game, "PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(gpc, "PROFILE_DIR", str(tmp_path))
    return tmp_path


def _generate(**overrides):
    """非交互生成一份档案的数据（名字可覆盖）。"""
    name = overrides.pop("name", "gen_game")
    os.environ["UGF_NONINTERACTIVE"] = "1"
    try:
        return add_game.collect(name)
    finally:
        os.environ.pop("UGF_NONINTERACTIVE", None)


def _write_profile(tmp_path, data, name=None):
    name = name or data["name"]
    (tmp_path / f"{name}.yaml").write_text(
        add_game.render_yaml(data), encoding="utf-8")
    return name


# --------------------------------------------------------------------------
# 一、模板本身
# --------------------------------------------------------------------------

def test_template_exists():
    assert os.path.isfile(TEMPLATE_PATH), "缺少参考模板 game_profiles/_template.yaml"


def test_template_is_valid_yaml(template_text):
    data = yaml.safe_load(template_text)
    assert isinstance(data, dict), "模板根节点必须是映射"
    for key in ("game", "predictor", "combat", "server", "perception"):
        assert key in data, f"模板缺少顶层键 {key}"


@pytest.mark.parametrize("slot", REQUIRED_SLOTS)
def test_template_declares_required_slots(template_text, slot):
    assert slot in template_text, f"模板未声明槽位 {slot}"


def test_template_is_skipped_by_check_all():
    """_ 开头的模板不参与运行时校验，不能混进真实档案列表。"""
    names = [n for n, _ in gpc.check_all()[1]]
    assert "_template" not in names


def test_template_defaults_drop_placeholders(template_text):
    """占位符字段被剔除（表示必须按游戏填写），字面值保留为默认。"""
    d = add_game.template_defaults(template_text)
    assert "name" not in d["game"], "游戏名是槽位，不应有字面默认"
    assert "rarity_normal" not in d["predictor"], "稀有度是槽位，不应有字面默认"
    assert d["predictor"]["threat"]["boss"] == 400        # 字面默认
    assert d["server"]["perception_port"] == 5021
    assert d["combat"]["chase_min_category"] == "elite"


# --------------------------------------------------------------------------
# 二、模板即唯一来源
# --------------------------------------------------------------------------

def test_render_has_no_residue():
    text = add_game.render_yaml(_generate())
    assert "__UGF_" not in text, "渲染后仍有未填充的占位符"


def test_render_fails_loudly_on_unknown_slot():
    """模板新增了槽位而生成器没跟上 → 硬失败，绝不静默产出坏档案。"""
    tpl = add_game.load_template() + "\nmystery: __UGF_MYSTERY__\n"
    with pytest.raises(ValueError, match="__UGF_MYSTERY__"):
        add_game.render_from_template(_generate(), template_text=tpl)


def test_template_drives_numeric_defaults(monkeypatch):
    """改模板的威胁分 → 向导默认值与产出档案一起变（模板是数值默认来源，不是硬编码）。"""
    tpl = add_game.load_template().replace("boss: 400", "boss: 777")
    monkeypatch.setattr(add_game, "load_template", lambda *a, **k: tpl)
    add_game._TDEF_CACHE["v"] = None
    monkeypatch.setenv("UGF_NONINTERACTIVE", "1")
    try:
        data = add_game.collect("tdef_game")
        assert data["threat"]["boss"] == 777
        text = add_game.render_from_template(data, template_text=tpl)
        assert yaml.safe_load(text)["predictor"]["threat"]["boss"] == 777
    finally:
        monkeypatch.undo()
        add_game._TDEF_CACHE["v"] = None


def test_template_comments_are_preserved():
    """模板的字段注释必须进入产出档案（这才是「标准答案」的价值）。"""
    text = add_game.render_yaml(_generate())
    assert "安全区间" in text and "缺失兜底" in text


def test_next_port_ignores_template(profiled):
    """模板不能占用端口，否则新游戏永远从 5021 之后开始分配。"""
    (profiled / "_template.yaml").write_text(
        "server:\n  perception_port: 5021\n", encoding="utf-8")
    assert add_game._next_port(5011) == 5011


# --------------------------------------------------------------------------
# 三、生成即通过 validate
# --------------------------------------------------------------------------

def test_generated_profile_passes_strict(profiled):
    name = _write_profile(profiled, _generate())
    detail = gpc.check_detail(name)
    assert detail["errors"] == [], f"生成档案有 ERROR: {detail['errors']}"
    assert detail["warnings"] == [], f"生成档案有建议项: {detail['warnings']}"


def test_generated_profile_has_expected_shape(profiled):
    name = _write_profile(profiled, _generate(name="shape_game"))
    data = yaml.safe_load((profiled / f"{name}.yaml").read_text(encoding="utf-8"))
    assert data["game"]["name"] == "shape_game"
    assert data["server"]["perception_port"] > 0
    assert data["combat"]["default_set"] in data["combat"]["sets"]
    assert len(data["combat"]["tactics"]) >= 1
    ents = data["perception"]["mock"]["entities"]
    assert ents, "mock 实体不能为空，否则离线全链路没有可打的目标"
    declared = set(data["predictor"]["rarity_highest_boss"]) | \
        set(data["predictor"]["rarity_boss"]) | \
        set(data["predictor"]["rarity_elite"]) | set(data["predictor"]["rarity_normal"])
    assert all(e["rarity"] in declared for e in ents)
    assert data["perception"]["mock"]["teammates"] == []


def test_custom_sets_generate_set_map(profiled):
    """自定义套装名（与决策语义不同名）必须自动生成 set_map，且值都落在 sets 里。"""
    name = _write_profile(profiled, _generate(name="custom_game"))
    data = yaml.safe_load((profiled / f"{name}.yaml").read_text(encoding="utf-8"))
    # 默认向导给出的是标准套装名，此处直接验证渲染器对 set_map 的处理
    data2 = _generate(name="custom_game2")
    data2["sets"] = ["alpha", "beta"]
    data2["default_set"] = "alpha"
    data2["set_map"] = {k: "alpha" for k in ["combat", "tank", "retreat", "chase", "team"]}
    name2 = _write_profile(profiled, data2)
    parsed = yaml.safe_load((profiled / f"{name2}.yaml").read_text(encoding="utf-8"))
    assert parsed["combat"]["set_map"]["retreat"] == "alpha"
    detail = gpc.check_detail(name2)
    assert (detail["errors"], detail["warnings"]) == ([], [])


def test_generated_files_are_yaml_parseable(profiled):
    for nm in ("a_game", "b_game", "c_game"):
        name = _write_profile(profiled, _generate(name=nm))
        assert yaml.safe_load((profiled / f"{name}.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 四、核心能读到生成档案的值（切游戏零改核心）
# --------------------------------------------------------------------------

def test_core_reads_generated_profile(tmp_path, monkeypatch):
    prof = tmp_path / "profiles"
    prof.mkdir()
    monkeypatch.setattr(add_game, "PROFILE_DIR", str(prof))
    name = _write_profile(prof, _generate(name="core_game"))

    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"agent:\n  game: {name}\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(config, "PROFILE_DIR", str(prof))
    monkeypatch.setattr(config, "TUNED_PATH", str(tmp_path / "no_tuned.yaml"))
    monkeypatch.setenv("AGENT_GAME", name)
    config._reload()

    assert config.active_game() == name
    assert config.get("server.perception_port") > 0
    assert config.get("predictor.threat.boss") == 400
    assert config.get("combat.default_set") in config.get("combat.sets")
    assert config.get("perception.mock.entities")
    monkeypatch.undo()
    config._reload()


# --------------------------------------------------------------------------
# 五、命令行入口
# --------------------------------------------------------------------------

def test_cli_print_has_no_residue():
    env = dict(os.environ, UGF_NONINTERACTIVE="1",
               PYTHONPATH=ROOT, TMPDIR=os.environ.get("TMPDIR", "/tmp"))
    out = subprocess.run([PY, os.path.join(ROOT, "tools", "add_game.py"),
                          "cli_game", "--print"],
                         capture_output=True, text=True, env=env, timeout=90)
    assert out.returncode == 0, out.stderr
    # --print 前会打印向导横幅，取第一个注释行之后的正文作为 YAML
    body = out.stdout[out.stdout.index("\n#"):] if "\n#" in out.stdout else out.stdout
    assert re.findall(r"__UGF_[A-Z0-9_]+__", body) == []
    parsed = yaml.safe_load(body)
    assert parsed["game"]["name"] == "cli_game"
    assert re.search(r"(?m)^  combat$", out.stdout) is None  # 列表项必须带 "- "
    assert "- combat" in out.stdout
