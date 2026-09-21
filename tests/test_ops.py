"""S12 · 运维脚本与容器一致性 测试（tests/test_ops.py）

锁定三件事：
  1. boot_check.py 的分级口径：核心库缺=ERROR；GUI/YOLO/可选库缺=WARN+降级指引（不阻断）。
  2. 运维脚本口径一致：引用的文件存在、端口与 config.yaml 一致。
  3. start_all.sh / stop_all.sh 在 dry-run 下全流程退出码 0，且**不产生副作用**。
"""
import json
import os
import subprocess
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import boot_check  # noqa: E402

PY = sys.executable


def _run(args, env=None, timeout=120):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(args, cwd=BASE_DIR, env=e, capture_output=True,
                          text=True, timeout=timeout)


# ---------------------------------------------------------------- 1. 分级口径
def test_active_machine_has_no_error():
    """本机（无 GUI / 无 YOLO / 无 .env）必须 0 ERROR，否则无头环境无法启动。"""
    issues = boot_check._check()
    errors = [i for i in issues if i["level"] == "ERROR"]
    assert errors == [], f"无头环境不应有 ERROR: {errors}"


def test_optional_missing_libs_are_warn_with_degrade(monkeypatch):
    """缺可选库（cv2/PIL/pyautogui）必须降级为 WARN + 降级说明（旧版误判为 ERROR）。

    注意：conftest 为无头环境注入了这三个库的 stub，故这里用 monkeypatch
    强制 import 失败，保证断言与"本机是否真装了"无关。
    """
    real_import = boot_check.importlib.import_module

    def fake_import(name, *a, **k):
        if name in ("cv2", "PIL", "pyautogui"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, *a, **k)

    monkeypatch.setattr(boot_check.importlib, "import_module", fake_import)
    issues = boot_check._check()
    errors = [i for i in issues if i["level"] == "ERROR"]
    assert not any("可选" in e["msg"] for e in errors), "可选库缺失不得判为 ERROR"

    warns = {i["msg"]: i for i in issues if i["level"] == "WARN"}
    hits = [m for m in warns if "可选库" in m]
    assert len(hits) == 3, f"应恰好 3 条可选库 WARN，实际 {hits}"
    for m in hits:
        assert warns[m].get("degrade"), f"WARN 必须给出降级路径: {m}"


def test_core_missing_lib_is_error(monkeypatch):
    """核心库缺失必须判 ERROR（与可选库分级形成对照）。"""
    real_import = boot_check.importlib.import_module

    def fake_import(name, *a, **k):
        if name == "numpy":
            raise ImportError("simulated missing numpy")
        return real_import(name, *a, **k)

    monkeypatch.setattr(boot_check.importlib, "import_module", fake_import)
    issues = boot_check._check()
    assert any(i["level"] == "ERROR" and "numpy" in i["msg"] for i in issues)


def test_headless_report_gives_degrade_not_error():
    out = boot_check._headless_report()
    assert out, "本机无 X server / 无权重，应产出降级提示"
    assert all(i["level"] == "WARN" for i in out)
    assert all(i.get("degrade") for i in out)


def test_strict_promotes_warn_to_error():
    """--strict（CI/容器门禁）下 WARN 也必须阻断。"""
    r = _run([PY, "boot_check.py", "--strict"])
    assert r.returncode == 1, "strict 模式下存在 WARN 应退出 1"
    r2 = _run([PY, "boot_check.py"])
    assert r2.returncode == 0, "默认模式 WARN 不阻断"


def test_json_output_schema():
    r = _run([PY, "boot_check.py", "--json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert set(["ok", "errors", "warnings", "ports"]).issubset(data)
    assert data["ports"]["perception_port"] == 5001
    assert data["ports"]["panel_port"] == 5002


def test_fail_fast_exit_code_matches_error_presence():
    r = _run([PY, "boot_check.py", "--fail-fast"])
    assert r.returncode in (0, 1)
    assert ("fail-fast" in r.stdout) == (r.returncode == 1)


# ---------------------------------------------------------------- 2. 口径一致
def test_config_ports_match_expectation():
    ports = boot_check.config_ports()
    assert ports == {"perception_port": 5001, "panel_port": 5002}


def test_ops_refs_exist():
    for script, refs in boot_check.OPS_REFS.items():
        assert os.path.exists(os.path.join(BASE_DIR, script)), f"缺脚本 {script}"
        for ref in refs:
            assert os.path.exists(os.path.join(BASE_DIR, ref)), f"{script} 引用了不存在的 {ref}"


def test_ops_check_clean_on_current_tree():
    ops_issues = boot_check.check_ops()
    assert ops_issues == [], f"运维脚本口径不一致: {ops_issues}"


def test_ops_check_detects_missing_reference(monkeypatch):
    """引用了不存在的目标时，check_ops 必须报 ERROR（防止校验器自身失效）。

    注意：早期版本会临时删除 start_all.sh 来制造该场景，但本机存在**并发的自动化线**
    同时跑 pytest，删文件会让另一个进程的 boot_check 误报"运维脚本缺失"（曾导致
    10 个用例随机失败）。故改为纯 monkeypatch，不触碰任何磁盘文件。
    """
    monkeypatch.setitem(boot_check.OPS_REFS, "start_all.sh",
                        ["definitely_missing_target.py"])
    issues = boot_check.check_ops()
    assert any(i["level"] == "ERROR" and "definitely_missing_target.py" in i["msg"]
               for i in issues), issues


def test_ops_check_detects_port_drift(monkeypatch):
    """脚本里的端口字面量与 config.yaml 不一致时必须报 ERROR。"""
    real_read = boot_check._read

    def fake_read(rel):
        if rel == "Dockerfile":
            return "EXPOSE 9999\n# panel_port: 9999\n"
        return real_read(rel)

    monkeypatch.setattr(boot_check, "_read", fake_read)
    issues = boot_check.check_ops()
    assert any(i["level"] == "ERROR" and "与 config.yaml" in i["msg"] for i in issues)


def test_scripts_do_not_hardcode_python_binary():
    """脚本必须允许 UGF_PYTHON 覆盖解释器（本机 python 未必是隔离 venv）。"""
    for script in ("start_all.sh", "stop_all.sh", "watchdog.sh"):
        text = open(os.path.join(BASE_DIR, script), encoding="utf-8").read()
        assert "UGF_PYTHON" in text, f"{script} 应支持 UGF_PYTHON 覆盖"
        assert '\nPY=python\n' not in "\n" + text, f"{script} 不应写死 PY=python"


def test_dockerfile_aligns_with_requirements():
    df = open(os.path.join(BASE_DIR, "Dockerfile"), encoding="utf-8").read()
    req = open(os.path.join(BASE_DIR, "requirements.txt"), encoding="utf-8").read()
    assert "requirements.txt" in df
    assert "opencv-python-headless" in df, "容器内必须用 headless 版 opencv"
    assert "COPY . ." in df
    # requirements 里声明的 core 包，Dockerfile 不能有冲突的 pin
    for pkg in ("flask", "pyyaml", "numpy", "mcp"):
        assert pkg in req
    assert "PIP_NO_CACHE_DIR" in df


# ---------------------------------------------------------------- 3. 干跑
def test_start_all_dry_run_exit_zero_and_no_side_effect():
    before = set(os.listdir(BASE_DIR))
    r = _run(["bash", "start_all.sh", "--dry-run"],
             env={"UGF_PYTHON": PY, "UGF_DRY_RUN": ""})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dry-run" in r.stdout
    assert "5001" in r.stdout and "5002" in r.stdout, "应打印从 config.yaml 读到的端口"
    after = set(os.listdir(BASE_DIR))
    new_pids = {f for f in after - before if f.endswith(".pid")}
    assert not new_pids, f"dry-run 不应创建 pid 文件: {new_pids}"


def test_start_all_env_dry_run_equivalent():
    r = _run(["bash", "start_all.sh"], env={"UGF_PYTHON": PY, "UGF_DRY_RUN": "1"})
    assert r.returncode == 0
    assert "dry-run" in r.stdout


def test_start_all_rejects_unknown_flag():
    r = _run(["bash", "start_all.sh", "--nope"], env={"UGF_PYTHON": PY})
    assert r.returncode == 2
    assert "未知参数" in (r.stdout + r.stderr)


def test_start_all_help_exit_zero():
    r = _run(["bash", "start_all.sh", "--help"], env={"UGF_PYTHON": PY})
    assert r.returncode == 0
    assert "用法" in r.stdout


def test_stop_all_dry_run_exit_zero():
    r = _run(["bash", "stop_all.sh", "--dry-run"],
             env={"UGF_PYTHON": PY, "UGF_DRY_RUN": "", "UGF_LOG_KEEP_DAYS": "99999"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_stop_all_cleans_temp_dir_and_rotates_logs(tmp_path):
    """真实清理路径验证：在沙箱目录中跑 stop_all.sh，确认清理生效且越界删除不会发生。"""
    sandbox = tmp_path / "proj"
    sandbox.mkdir()
    for name in ("stop_all.sh",):
        (sandbox / name).write_text(
            open(os.path.join(BASE_DIR, name), encoding="utf-8").read(), encoding="utf-8")
    (sandbox / "video_frames").mkdir()
    (sandbox / "video_frames" / "f.png").write_text("x")
    logs = sandbox / "run_logs"
    logs.mkdir()
    old = logs / "old.log"
    old.write_text("old")
    os.utime(old, (0, 0))  # mtime 归零 = 远超保留期
    fresh = logs / "fresh.log"
    fresh.write_text("new")
    (sandbox / "keepme.tmp").write_text("tmp")

    r = subprocess.run(["bash", "stop_all.sh"], cwd=str(sandbox),
                       env={**os.environ, "UGF_PYTHON": PY, "UGF_LOG_KEEP_DAYS": "7"},
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (sandbox / "video_frames").exists(), "video_frames 应被清理"
    assert not old.exists(), "过期日志应被轮转"
    assert fresh.exists(), "未过期日志必须保留"
    assert not (sandbox / "keepme.tmp").exists(), "临时探针应被清理"


def test_stop_all_keep_logs_preserves():
    r = _run(["bash", "stop_all.sh", "--keep-logs", "--dry-run"],
             env={"UGF_PYTHON": PY, "UGF_DRY_RUN": ""})
    assert r.returncode == 0


def test_watchdog_python_override_and_dry_run_passthrough():
    text = open(os.path.join(BASE_DIR, "watchdog.sh"), encoding="utf-8").read()
    assert "UGF_PYTHON" in text
    assert "export UGF_DRY_RUN" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ---------------------------------------------------------------- 4. 门禁（S13 预热）
def test_check_script_fast_gate_exit_zero():
    r = _run(["bash", "scripts/check.sh", "--fast"], env={"UGF_PYTHON": PY}, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    for stage in ("语法编译", "启动自检", "游戏档案校验", "pytest"):
        assert stage in r.stdout, f"门禁应逐阶段打印: {stage}"


def test_check_script_rejects_unknown_flag():
    r = _run(["bash", "scripts/check.sh", "--nope"], env={"UGF_PYTHON": PY})
    assert r.returncode == 2


# ---------------------------------------------------------------- 4. 门禁（S13 预热）
def test_check_script_fast_gate_exit_zero():
    r = _run(["bash", "scripts/check.sh", "--fast"], env={"UGF_PYTHON": PY}, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    for stage in ("语法编译", "启动自检", "游戏档案校验", "pytest"):
        assert stage in r.stdout, f"门禁应逐阶段打印: {stage}"


def test_check_script_rejects_unknown_flag():
    r = _run(["bash", "scripts/check.sh", "--nope"], env={"UGF_PYTHON": PY})
    assert r.returncode == 2


# ------------------------------------------- 5. 回归：自检不得触发批量删除护栏
def test_dir_writable_probe_does_not_delete():
    """探针必须「零删除」：宿主 safe-delete 护栏（50 次/turn）会在全量测试时拦截
    os.remove，导致自检误报『目录不可写』并拦下 start_all.sh（S12 实测踩到）。"""
    import ast
    src = open(os.path.join(BASE_DIR, "boot_check.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    used = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("remove", "unlink", "rmtree")]
    assert not used, f"boot_check 内不得调用删除类 API（会被删除护栏拦截）: {used}"
    ok, err = boot_check._dir_writable(os.path.join(BASE_DIR, "run_logs"))
    assert ok, f"run_logs 应可写: {err}"


def test_dir_writable_detects_bad_path(tmp_path):
    """不可写/不可建目录必须被识别（用一个文件冒充目录，makedirs 必然失败）。"""
    f = tmp_path / "not_a_dir"
    f.write_text("x")
    ok, _ = boot_check._dir_writable(str(f))
    assert not ok
