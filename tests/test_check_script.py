"""S21 门禁与可观测性测试。

覆盖两件事：
1. `scripts/check.sh` 真的是「一条命令验证整个项目」—— 包含 MCP 工具核对与 CLI 冒烟，
   且任一环节失败即非零退出（退出码 = 环节编号）。
2. 运行模式可查询、口径统一（config.runtime_mode 是唯一真源，大盘与 CLI 都从这里取）。
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "scripts", "check.sh")
PY = sys.executable


def run(args, timeout=600):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout)


# ---------------------------------------------------------------------------
# 1. 门禁脚本
# ---------------------------------------------------------------------------
def test_check_script_exists_and_is_executable():
    assert os.path.exists(CHECK)
    # 无执行位时也能用 bash 跑，这里只要求 bash 语法正确
    r = run(["bash", "-n", CHECK])
    assert r.returncode == 0, r.stderr


def test_check_help_exit_zero():
    r = run(["bash", CHECK, "--help"])
    assert r.returncode == 0
    assert "check.sh" in r.stdout


def test_check_unknown_arg_exit_two():
    r = run(["bash", CHECK, "--definitely-not-an-arg"])
    assert r.returncode == 2


def test_check_fast_passes():
    """--fast 跑静态与自检，应当秒级通过。"""
    r = run(["bash", CHECK, "--fast"], timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "全部门禁通过" in r.stdout


def test_check_script_contains_all_six_steps():
    """门禁必须包含 6 个环节，缺一个就不是"一条命令验证整个项目"。"""
    src = open(CHECK, encoding="utf-8").read()
    for key in ("compileall", "boot_check.py", "game_profile_check.py",
                "pytest", "mcp_tools_check.py", "cli_smoke.py"):
        assert key in src, f"门禁缺少环节: {key}"


def test_check_script_failure_exit_codes_are_distinct():
    """每个环节失败都要有独立退出码，便于定位。"""
    src = open(CHECK, encoding="utf-8").read()
    for code in ("exit 1", "exit 2", "exit 3", "exit 4", "exit 5", "exit 6"):
        assert code in src, f"缺少退出码: {code}"


def test_check_script_picks_python_with_yaml():
    """门禁自带解释器探测，不能用没装依赖的系统 python 跑出假失败。"""
    src = open(CHECK, encoding="utf-8").read()
    assert "import yaml" in src
    assert "UGF_PYTHON" in src


# ---------------------------------------------------------------------------
# 2. 运行模式可观测
# ---------------------------------------------------------------------------
def test_runtime_mode_keys_and_defaults(monkeypatch):
    import config
    for k in ("UGF_DRY_RUN", "DRY_RUN", "UGF_PERCEPTION_BACKEND",
              "LLM_API_URL", "LLM_API_KEY", "VLM_API_URL", "VLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    m = config.runtime_mode()
    assert set(m) >= {"mode", "dry_run", "perception_backend", "llm", "vlm", "game"}
    assert m["mode"] == "online"
    assert m["llm"] == "off" and m["vlm"] == "off"


def test_runtime_mode_dry_run(monkeypatch):
    import config
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    m = config.runtime_mode()
    assert m["mode"] == "dry-run" and m["dry_run"] is True


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_runtime_mode_flag_variants(monkeypatch, val):
    import config
    monkeypatch.setenv("UGF_DRY_RUN", val)
    assert config.runtime_mode()["dry_run"] is True


def test_runtime_mode_backend_env_overrides_config(monkeypatch):
    import config
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "http")
    assert config.runtime_mode()["perception_backend"] == "http"


def test_runtime_mode_dry_run_downgrades_auto_to_mock(monkeypatch):
    """dry-run + auto 时实际必然走 mock，不能显示成 auto 让人以为在等真机。"""
    import config
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    monkeypatch.delenv("UGF_PERCEPTION_BACKEND", raising=False)
    monkeypatch.setattr(config, "get", lambda p, d=None: "auto", raising=False)
    assert config.runtime_mode()["perception_backend"] == "mock"


def test_runtime_mode_llm_vlm_on(monkeypatch):
    import config
    monkeypatch.setenv("LLM_API_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("VLM_API_URL", "http://y")
    monkeypatch.setenv("VLM_API_KEY", "k2")
    m = config.runtime_mode()
    assert m["llm"] == "on" and m["vlm"] == "on"


def test_runtime_mode_text_contains_everything(monkeypatch):
    import config
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    t = config.runtime_mode_text()
    for key in ("模式=", "感知=", "LLM=", "VLM=", "游戏="):
        assert key in t


def test_cli_mode_command(monkeypatch):
    import agent_cli
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    out = agent_cli._cmd_mode()
    assert "dry-run" in out and "运行模式" in out
    assert "mode" in agent_cli._command_registry("")


def test_admin_panel_mode_uses_single_source(monkeypatch):
    """大盘模式必须与 config.runtime_mode 同口径，不能各写一套解析。"""
    import admin_panel
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    monkeypatch.setenv("UGF_PERCEPTION_BACKEND", "mock")
    m = admin_panel._mode()
    assert m["offline"] is True
    assert "dry-run" in m["run"]
    assert m["perception"] == "mock"
    assert m["llm"] in ("on", "off") and m["vlm"] in ("on", "off")
    assert "模式=" in m["summary"]
