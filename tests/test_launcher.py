#!/usr/bin/env python3
"""
S11 · UI 收敛与统一启动器 —— tests/test_launcher.py
====================================================
锁四件事：
  1. 四套前端收敛为「1 主(admin_panel) + 1 备选(ui_tkinter) + CLI 保底」，另两套已归档；
  2. launcher 的自动选择永远能选出一个**可用**的 UI（无 GUI 环境也不会选 pyqt / tk 崩掉）；
  3. dry-run / mock 开关通过环境变量完整透传给子进程；
  4. 主 UI 能正确显示当前运行模式（离线要能一眼看出来）。

全部为纯函数/环境探测测试，不真的拉起 UI 进程。
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import launcher  # noqa: E402


# --------------------------------------------------------------------------
# 一、收敛后的 UI 清单
# --------------------------------------------------------------------------

def test_ui_table_has_five_entries():
    keys = [k for k, _p, _m, _a in launcher.UI_TABLE]
    assert keys == ["panel", "tk", "pyqt", "streamlit", "cli"]


def test_main_ui_is_pure_stdlib_panel():
    assert launcher.ui_path("panel").endswith("admin_panel.py")
    assert os.path.exists(launcher.ui_path("panel"))


def test_legacy_uis_are_archived():
    for key in ("pyqt", "streamlit"):
        path = launcher.ui_path(key)
        assert os.sep + "legacy" + os.sep in path, f"{key} 应归档到 ui/legacy/"
        assert os.path.exists(path)
        head = open(path, encoding="utf-8").read(400)
        assert "DEPRECATED" in head, f"{key} 缺弃用说明"


def test_legacy_ui_keeps_project_root_importable():
    """归档后 sys.path 不含项目根，文件内必须有 bootstrap，否则 import config 会失败。"""
    for key in ("pyqt", "streamlit"):
        path = launcher.ui_path(key)
        src = open(path, encoding="utf-8").read()
        assert "sys.path.insert" in src


def test_auto_order_prefers_panel_then_tk_then_cli():
    assert launcher.AUTO_ORDER == ["panel", "tk", "cli"]


# --------------------------------------------------------------------------
# 二、可用性与选择
# --------------------------------------------------------------------------

def test_detect_covers_all_uis():
    det = launcher.detect()
    assert set(det) == {"panel", "tk", "pyqt", "streamlit", "cli"}
    for key, (ok, why) in det.items():
        assert isinstance(ok, bool) and isinstance(why, str) and why


def test_panel_and_cli_always_available():
    assert launcher.availability("panel")[0] is True
    assert launcher.availability("cli")[0] is True


def test_choose_auto_returns_available_ui():
    key, why = launcher.choose("auto")
    assert key in launcher.AUTO_ORDER
    assert launcher.availability(key)[0] is True
    assert why


def test_choose_explicit_cli():
    key, _why = launcher.choose("cli")
    assert key == "cli"


def test_choose_unknown_returns_none():
    key, why = launcher.choose("nope")
    assert key is None and why


def test_choose_unavailable_legacy_returns_none():
    """本机无 PyQt6 / streamlit，显式指定也应返回 None 而不是硬拉起。"""
    for key in ("pyqt", "streamlit"):
        if launcher.availability(key)[0]:
            pytest.skip(f"{key} 在本机可用（PyQt6/streamlit 已安装），跳过不可用分支")
        assert launcher.choose(key)[0] is None


def test_availability_missing_file():
    assert launcher.availability("ghost_ui") == (False, "未知 UI")


# --------------------------------------------------------------------------
# 三、命令构造与开关透传
# --------------------------------------------------------------------------

def test_build_cmd_panel_uses_current_interpreter():
    cmd = launcher.build_cmd("panel")
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("admin_panel.py")


def test_build_cmd_streamlit_uses_module_run():
    cmd = launcher.build_cmd("streamlit")
    assert cmd[:3] == [sys.executable, "-m", "streamlit"]


def test_child_env_passes_offline_switches(monkeypatch):
    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    monkeypatch.delenv("UGF_PERCEPTION_BACKEND", raising=False)
    env = launcher.child_env(dry_run=True, mock=True)
    assert env["UGF_DRY_RUN"] == "1"
    assert env["UGF_PERCEPTION_BACKEND"] == "mock"
    assert ROOT in env["PYTHONPATH"]


def test_child_env_without_flags_keeps_env(monkeypatch):
    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    env = launcher.child_env()
    assert "UGF_DRY_RUN" not in env


@pytest.mark.parametrize("dry,mock,expect", [
    (True, True, "dry-run / mock"),
    (True, False, "dry-run"),
    (False, True, "mock 感知"),
])
def test_mode_label(monkeypatch, dry, mock, expect):
    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "mock" if mock else "auto")
    assert expect in launcher.mode_label(dry, mock)


# --------------------------------------------------------------------------
# 四、自检输出与退出码
# --------------------------------------------------------------------------

def test_selftest_text_lists_all_uis():
    text = launcher.selftest_text("auto")
    for key in ("panel", "tk", "pyqt", "streamlit", "cli"):
        assert key in text
    assert "选择结果" in text and "离线开关" in text


def test_main_selftest_auto_returns_zero():
    assert launcher.main(["--ui", "auto", "--selftest"]) == 0


def test_main_list_returns_zero():
    assert launcher.main(["--list"]) == 0


def test_main_selftest_unavailable_returns_two():
    if launcher.availability("pyqt")[0]:
        pytest.skip("PyQt6 已安装")
    assert launcher.main(["--ui", "pyqt", "--selftest"]) == 2


# --------------------------------------------------------------------------
# 五、主 UI 的模式显示
# --------------------------------------------------------------------------

def test_panel_mode_default_online(monkeypatch):
    monkeypatch.delenv("UGF_DRY_RUN", raising=False)
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "auto")
    admin_panel = importlib.import_module("admin_panel")
    mode = admin_panel._mode()
    assert mode["offline"] is False
    assert "在线" in mode["label"]


def test_panel_mode_offline_flagged(monkeypatch):
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "mock")
    admin_panel = importlib.import_module("admin_panel")
    mode = admin_panel._mode()
    assert mode["offline"] is True
    assert mode["label"] == "dry-run / mock"


def test_panel_status_exposes_mode(monkeypatch):
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "mock")
    admin_panel = importlib.import_module("admin_panel")
    status = admin_panel._status()
    assert status["mode"]["offline"] is True
    assert 'id="mode"' in admin_panel.PAGE
