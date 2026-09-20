#!/usr/bin/env python3
"""
S5 · 技能管理器 skill_manager.py 实测

覆盖：目录扫描 / 元信息解析 / 加载卸载重载 / 调用与异常兜底 /
清单文案 / 越界名防御 / 损坏技能不拖垮扫描 / report 技能真实输出。
"""
import os
import sys
import textwrap

import pytest

import skill_manager
from skill_manager import SkillManager


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """把 SKILLS_DIR 指向临时目录，并预置一个可控的假技能。"""
    d = tmp_path / "skills"
    d.mkdir()
    monkeypatch.setattr(skill_manager, "SKILLS_DIR", str(d))
    return d


def _make_skill(root, name, entry="run", desc="测试技能", body=None,
                md=None, entry_name=None, py_name="skill.py"):
    p = root / name
    p.mkdir(parents=True, exist_ok=True)
    if md is None:
        md = f"# {name}\n\ndescription: {desc}\nentry: {entry_name or entry}\n"
    (p / "SKILL.md").write_text(md, encoding="utf-8")
    if body is None:
        body = f"def {entry}():\n    return 'ok:{name}'\n"
    (p / py_name).write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 名称合法性
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,ok", [
    ("report", True), ("my_skill", True), ("a-b", True),
    ("../config", False), ("/etc", False), ("..", False), ("a/b", False),
    ("", False), (None, False), ("a\\b", False),
])
def test_is_valid_name(name, ok):
    assert skill_manager.is_valid_name(name) is ok


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------
def test_scan_empty_dir(sandbox):
    assert skill_manager.scan() == []


def test_scan_missing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_manager, "SKILLS_DIR", str(tmp_path / "nope"))
    assert skill_manager.scan() == []


def test_scan_finds_and_parses(sandbox):
    _make_skill(sandbox, "alpha", entry="run", desc="第一个")
    _make_skill(sandbox, "beta", entry="go", desc="第二个")
    got = skill_manager.scan()
    assert [s["name"] for s in got] == ["alpha", "beta"]
    assert got[0]["description"] == "第一个"
    assert got[1]["entry"] == "go"


def test_scan_ignores_non_skill_dirs(sandbox):
    (sandbox / "loose.txt").write_text("x")
    (sandbox / "noskill").mkdir()
    (sandbox / "__pycache__").mkdir()
    _make_skill(sandbox, "alpha")
    assert [s["name"] for s in skill_manager.scan()] == ["alpha"]


# v2.0：缺 description / entry 字段时给空串，不 KeyError
def test_scan_missing_meta_fields(sandbox):
    _make_skill(sandbox, "bare", md="# bare\n\n没写元信息\n")
    got = skill_manager.scan()
    assert got[0]["description"] == "" and got[0]["entry"] == ""


# v2.0：某个技能文件损坏不该拖垮整体扫描
def test_scan_survives_unreadable(sandbox, monkeypatch):
    _make_skill(sandbox, "alpha")
    _make_skill(sandbox, "broken")
    real_open = open

    def fake_open(path, *a, **kw):
        if str(path).endswith("broken/SKILL.md") or str(path).endswith("broken\\SKILL.md"):
            raise UnicodeDecodeError("utf-8", b"x", 0, 1, "boom")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(skill_manager, "open", fake_open, raising=False)
    monkeypatch.setattr("builtins.open", fake_open)
    names = [s["name"] for s in skill_manager.scan()]
    assert "alpha" in names and "broken" in names


# ---------------------------------------------------------------------------
# load / unload / reload / call
# ---------------------------------------------------------------------------
def test_load_and_call(sandbox):
    _make_skill(sandbox, "alpha", entry="run", body="def run(*a, **k):\n    return 'ran'\n")
    m = SkillManager()
    assert "已加载" in m.load("alpha")
    assert m.is_loaded("alpha")
    assert m.call("alpha") == "ran"


def test_load_duplicate(sandbox):
    _make_skill(sandbox, "alpha")
    m = SkillManager()
    m.load("alpha")
    assert "已加载" in m.load("alpha")
    assert m.loaded() == ["alpha"]


@pytest.mark.parametrize("setup", ["no_dir", "no_md", "no_py", "no_entry", "bad_py"])
def test_load_failure_modes(sandbox, setup, monkeypatch):
    if setup == "no_dir":
        name = "ghost"
    elif setup == "no_md":
        (sandbox / "alpha").mkdir()
        (sandbox / "alpha" / "skill.py").write_text("def run(): pass\n", encoding="utf-8")
        name = "alpha"
    elif setup == "no_py":
        (sandbox / "alpha").mkdir()
        (sandbox / "alpha" / "SKILL.md").write_text(
            "# a\n\ndescription: d\nentry: run\n", encoding="utf-8")
        name = "alpha"
    elif setup == "no_entry":
        _make_skill(sandbox, "alpha", entry="run", entry_name="missing_fn")
        name = "alpha"
    else:  # bad_py
        _make_skill(sandbox, "alpha", entry="run", body="raise RuntimeError('boom')\n")
        name = "alpha"
    m = SkillManager()
    # 前面的用例可能已成功注册同名模块，先清干净再验证本次失败不残留
    monkeypatch.delitem(sys.modules, f"ugf_skill_{name}", raising=False)
    assert "无法加载" in m.load(name)
    assert m.is_loaded(name) is False
    # v2.0：失败后不得在 sys.modules 留下残缺模块
    assert f"ugf_skill_{name}" not in sys.modules


def test_load_rejects_traversal(sandbox, monkeypatch):
    m = SkillManager()
    assert "无法加载" in m.load("../../etc")


def test_unload(sandbox):
    _make_skill(sandbox, "alpha")
    m = SkillManager()
    m.load("alpha")
    assert "已卸载" in m.unload("alpha")
    assert m.loaded() == []
    assert "未加载" in m.unload("alpha")


def test_call_not_loaded(sandbox):
    _make_skill(sandbox, "alpha")
    m = SkillManager()
    assert "未加载" in m.call("alpha")


# v2.0：技能内部抛异常必须收敛成字符串，不能炸穿调用方
def test_call_exception_captured(sandbox):
    _make_skill(sandbox, "alpha", entry="run",
                body="def run():\n    raise ValueError('boom')\n")
    m = SkillManager()
    m.load("alpha")
    out = m.call("alpha")
    assert "调用失败" in out and "boom" in out


def test_reload_picks_up_change(sandbox):
    _make_skill(sandbox, "alpha", entry="run", body="def run():\n    return 'v1'\n")
    m = SkillManager()
    m.load("alpha")
    assert m.call("alpha") == "v1"
    (sandbox / "alpha" / "skill.py").write_text("def run():\n    return 'v2'\n",
                                                encoding="utf-8")
    m.reload("alpha")
    assert m.call("alpha") == "v2"


def test_loaded_sorted(sandbox):
    for n in ("zeta", "alpha", "mid"):
        _make_skill(sandbox, n)
    m = SkillManager()
    for n in ("zeta", "alpha", "mid"):
        m.load(n)
    assert m.loaded() == ["alpha", "mid", "zeta"]


def test_summary_marks(sandbox):
    _make_skill(sandbox, "alpha", desc="甲")
    _make_skill(sandbox, "beta", desc="乙")
    m = SkillManager()
    m.load("beta")
    s = m.summary()
    assert "甲" in s and "乙" in s
    assert "✓ beta" in s and "· alpha" in s


def test_summary_empty(sandbox):
    assert "暂无" in SkillManager().summary()


# ---------------------------------------------------------------------------
# 真实技能包 report（v2.0 实装）
# ---------------------------------------------------------------------------
def test_builtin_report_skill_scannable():
    real = skill_manager.SKILLS_DIR
    if not os.path.isdir(os.path.join(real, "report")):
        pytest.skip("内置 report 技能不存在")
    meta = {s["name"]: s for s in skill_manager.scan()}
    assert "report" in meta
    assert meta["report"]["entry"] == "report_run"
    assert meta["report"]["description"]


def test_builtin_report_skill_returns_real_progress(monkeypatch, tmp_path):
    """v0.8 桩恒返回"汇报技能演示"；v2.0 必须输出真实字段。"""
    import session
    monkeypatch.setattr(session, "STATE_FILE", str(tmp_path / "agent_state.json"))
    monkeypatch.setattr(session, "HISTORY_FILE", str(tmp_path / "session_history.json"))
    snap_dir = tmp_path / "run_logs"
    snap_dir.mkdir(exist_ok=True)
    snap = snap_dir / "agent_snapshot.json"
    monkeypatch.setattr(session, "SNAP_PATH", str(snap))
    session.record_end("florr", 42, 3, ["report"])
    snap.write_text('{"game":"florr","round":42,"deaths":3,"hp":78,"max_hp":100,'
                    '"decision":"cautious","mindset":"steady","set":"tank",'
                    '"threats":[{"name":"Hornet","threat":400}]}', encoding="utf-8")

    m = SkillManager()
    assert "已加载" in m.load("report")
    out = m.call("report")
    assert "汇报技能演示" not in out
    assert "42" in out and "78/100" in out and "cautious" in out and "Hornet" in out


def test_builtin_report_skill_offline_safe(monkeypatch, tmp_path):
    """无快照、无档案时必须给出降级文案而不是抛异常。"""
    import session
    monkeypatch.setattr(session, "STATE_FILE", str(tmp_path / "missing_state.json"))
    monkeypatch.setattr(session, "HISTORY_FILE", str(tmp_path / "missing_hist.json"))
    monkeypatch.setattr(session, "SNAP_PATH", str(tmp_path / "missing_snap.json"))
    m = SkillManager()
    m.load("report")
    out = m.call("report")
    assert "当前游戏" in out and "离线" in out
