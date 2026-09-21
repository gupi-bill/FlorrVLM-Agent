#!/usr/bin/env python3
"""
S17 · 接入流程一键化（onboard）—— tests/test_onboard_game.py
==========================================================
锁五件事：
  1. 五个环节的**编排正确性**：顺序固定、失败即中止、被跳过的环节必须显式标记；
  2. **跳过的环节不许偷跑**（回归用例）：`--no-dry-run` 若仍真跑子进程，
     会白白耗掉 14 秒，命令行开关形同虚设；
  3. 校验未通过时，冒烟/试跑必须判为 skipped+failed，不能让整体误判为成功；
  4. 报告可注入目录（不污染仓库）且内容自洽（结论 / 明细 / 摘要 / 问题 / 建议）；
  5. CLI 契约：`--json` 可解析、非法游戏名退出码 2、`agent_cli.py -c onboard <game>` 已登记。

重环节（感知冒烟 / dry-run 试跑）用真实子进程，但默认只在标记出来的用例里跑，
其余用例靠参数关掉，保证整套测试仍在数十秒内完成。
"""
import json
import os
import subprocess
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import game_profile_check as gpc  # noqa: E402
from tools import add_game  # noqa: E402
from tools import onboard_game as ob  # noqa: E402

PY = sys.executable


# ---------------------------------------------------------------------------
# 沙箱：所有落盘动作指到 tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(add_game, "PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(gpc, "PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(add_game, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    return tmp_path


def _fast(game="onb_game", **kw):
    """跑一条不含子进程的流水线（秒级）。"""
    kw.setdefault("do_smoke", False)
    kw.setdefault("do_dryrun", False)
    kw.setdefault("activate", False)
    kw.setdefault("report_dir", None)
    return ob.onboard(game, **kw)


# ---------------------------------------------------------------------------
# 1. 编排
# ---------------------------------------------------------------------------
def test_step_order_is_fixed(sandbox, tmp_path):
    r = _fast(report_dir=str(tmp_path))
    keys = [s["key"] for s in r["steps"]]
    assert keys == ["generate", "validate", "smoke", "dryrun", "report"]
    assert r["ok"] is True


def test_generate_creates_profile(sandbox, tmp_path):
    r = _fast(report_dir=str(tmp_path))
    prof = tmp_path / "onb_game.yaml"
    assert prof.exists()
    assert r["generated"] is True
    data = yaml.safe_load(prof.read_text(encoding="utf-8"))
    assert data["game"]["name"] == "onb_game"


def test_generate_reuses_existing_profile(sandbox, tmp_path):
    prof = tmp_path / "onb_game.yaml"
    prof.write_text("# 手工档案\n", encoding="utf-8")
    r = _fast(report_dir=str(tmp_path))
    assert r["generated"] is False
    assert prof.read_text(encoding="utf-8") == "# 手工档案\n"   # 不许覆盖


def test_report_written_to_injected_dir(sandbox, tmp_path):
    out = tmp_path / "reports"
    r = _fast(report_dir=str(out))
    path = out / "onboard_onb_game.md"
    assert path.exists() and path.stat().st_size > 200
    assert r["report_path"] == str(path)
    assert "onb_game" in path.read_text(encoding="utf-8")


def test_default_report_dir_is_devplan():
    assert ob.DEFAULT_REPORT_DIR.endswith("devplan")


# ---------------------------------------------------------------------------
# 2. 跳过环节不许偷跑（S17 实测修复项）
# ---------------------------------------------------------------------------
def test_skipped_steps_cost_no_time(sandbox, tmp_path):
    r = _fast(report_dir=str(tmp_path))
    for s in r["steps"]:
        if s["skipped"]:
            assert s["seconds"] < 1.0, f"{s['key']} 被标记跳过却耗时 {s['seconds']}s"
            assert s["issues"] == []


def test_no_dryrun_flag_does_not_spawn_subprocess(sandbox, tmp_path):
    """子进程环节一旦偷跑，必然耗时数秒 —— 用耗时反证它没跑。"""
    r = _fast(report_dir=str(tmp_path))
    dry = [s for s in r["steps"] if s["key"] == "dryrun"][0]
    assert dry["skipped"] is True and dry["seconds"] < 1.0
    assert r["seconds"] < 10


# ---------------------------------------------------------------------------
# 3. 失败传播：校验不过 → 后面判失败
# ---------------------------------------------------------------------------
def _broken_profile(tmp_path, name="broken_game"):
    """用模板生成一份合法档案，再人为制造一个 ERROR（威胁分金字塔倒置）。"""
    os.environ["UGF_NONINTERACTIVE"] = "1"
    data = add_game.collect(name)
    data["threat"]["boss"] = 1
    data["threat"]["elite"] = 999
    (tmp_path / f"{name}.yaml").write_text(add_game.render_yaml(data),
                                           encoding="utf-8")
    return name


def test_validate_failure_blocks_downstream(sandbox, tmp_path):
    name = _broken_profile(tmp_path)
    r = _fast(name, report_dir=str(tmp_path))
    st = {s["key"]: s for s in r["steps"]}
    assert st["validate"]["ok"] is False
    assert st["smoke"]["skipped"] is True and st["smoke"]["ok"] is False
    assert st["dryrun"]["skipped"] is True and st["dryrun"]["ok"] is False
    assert r["ok"] is False
    assert r["issues"]


def test_broken_profile_report_says_failed(sandbox, tmp_path):
    name = _broken_profile(tmp_path)
    r = _fast(name, report_dir=str(tmp_path))
    body = (tmp_path / f"onboard_{name}.md").read_text(encoding="utf-8")
    assert "⛔ 接入未通过" in body
    assert "前置校验未通过" in body


# ---------------------------------------------------------------------------
# 4. strict / lenient 口径
# ---------------------------------------------------------------------------
def test_strict_counts_warning_as_problem(sandbox, tmp_path):
    """删掉 description → WARN：strict 下失败，lenient 下通过。"""
    os.environ["UGF_NONINTERACTIVE"] = "1"
    data = add_game.collect("warn_game")
    text = add_game.render_yaml(data)
    text = "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith("description:"))
    (tmp_path / "warn_game.yaml").write_text(text, encoding="utf-8")

    strict = _fast("warn_game", strict=True, report_dir=str(tmp_path))
    lenient = _fast("warn_game", strict=False, report_dir=str(tmp_path))
    assert strict["ok"] is False
    assert lenient["ok"] is True
    assert any("[建议]" in i for i in strict["issues"])


# ---------------------------------------------------------------------------
# 5. 报告内容自洽
# ---------------------------------------------------------------------------
def test_report_sections_present(sandbox, tmp_path):
    r = _fast(report_dir=str(tmp_path))
    body = (tmp_path / "onboard_onb_game.md").read_text(encoding="utf-8")
    for sec in ["## 一、结论", "## 二、环节明细", "## 三、档案摘要",
                "## 四、发现的问题", "## 五、后续建议"]:
        assert sec in body
    # 明细表行数 == 环节数
    rows = [ln for ln in body.splitlines() if ln.startswith("| ") and "环节" not in ln
            and "---" not in ln]
    assert len([x for x in rows if x.count("|") >= 5]) >= len(r["steps"]) - 1
    assert "✅ 接入成功" in body
    assert "python tools/onboard_game.py onb_game" in body


def test_profile_summary_fields(sandbox, tmp_path):
    r = _fast(report_dir=str(tmp_path))
    s = r["profile_summary"]
    for k in ["game.name", "combat.default_set", "combat.sets",
              "server.perception_port", "perception.mock.entities"]:
        assert k in s, f"档案摘要缺字段 {k}"
    assert s["game.name"] == "onb_game"
    assert s["perception.mock.entities"] >= 1


# ---------------------------------------------------------------------------
# 6. 参数与 CLI
# ---------------------------------------------------------------------------
def test_underscore_name_rejected(sandbox):
    with pytest.raises(ValueError):
        ob.onboard("_template")


def test_empty_name_rejected(sandbox):
    with pytest.raises(ValueError):
        ob.onboard("")


def test_activation_deferred_until_validate_passes(sandbox, tmp_path):
    """回归：先切后验会把 config.yaml 指向坏游戏，必须改成先验后切。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("agent:\n  game: florr\n", encoding="utf-8")
    name = _broken_profile(tmp_path)
    ob.onboard(name, do_smoke=False, do_dryrun=False, activate=True,
               report_dir=str(tmp_path))
    assert cfg.read_text(encoding="utf-8") == "agent:\n  game: florr\n"


def test_activation_happens_on_success(sandbox, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("agent:\n  game: florr\n", encoding="utf-8")
    r = ob.onboard("good_game", do_smoke=False, do_dryrun=False,
                   activate=True, report_dir=str(tmp_path))
    assert r["ok"] is True
    assert "game: good_game" in cfg.read_text(encoding="utf-8")


def test_cli_json_and_exit_code(sandbox, tmp_path):
    # 子进程不受 monkeypatch 影响，会真的在 game_profiles/ 落档案 → 用完即删
    stray = os.path.join(ROOT, "game_profiles", "cli_game.yaml")
    try:
        proc = subprocess.run(
        [PY, os.path.join(ROOT, "tools", "onboard_game.py"), "cli_game",
         "--no-dry-run", "--no-smoke", "--no-activate",
         "--report-dir", str(tmp_path), "--json"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": ROOT})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout)      # 首行不能有人话提示，否则这里炸
        assert payload["game"] == "cli_game"
        assert payload["ok"] is True
        assert [s["key"] for s in payload["steps"]][-1] == "report"
    finally:
        if os.path.exists(stray):
            os.remove(stray)


def test_cli_bad_name_exit_2(tmp_path):
    proc = subprocess.run(
        [PY, os.path.join(ROOT, "tools", "onboard_game.py"), "_nope"],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# 7. 重环节（真实子进程）—— 默认跳过，仅在显式调用时执行
# ---------------------------------------------------------------------------
def test_smoke_step_runs_mock_perception():
    """无显卡 / 无 YOLO 也要能出场景（S6 离线化的兑现点）。"""
    st = ob.step_smoke("florr", rounds=2)
    assert st["ok"] is True, st["issues"]
    assert st["entities"] >= 1
    assert st["seconds"] < 60


def test_onboard_existing_game_full_pipeline(tmp_path):
    """验收项：对已接入游戏跑完整流程，退出码 0 且报告非空。"""
    r = ob.onboard("space_invaders", rounds=1, activate=False,
                   report_dir=str(tmp_path))
    assert r["ok"] is True, [s["issues"] for s in r["steps"]]
    assert r["generated"] is False
    body = open(r["report_path"], encoding="utf-8").read()
    assert "space_invaders" in body and len(body) > 500
    dry = [s for s in r["steps"] if s["key"] == "dryrun"][0]
    assert dry["ok"] is True and dry["kb_files"]
