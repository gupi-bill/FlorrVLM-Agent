# -*- coding: utf-8 -*-
"""S22 · 稳定性长跑与资源门禁（离线）。

锁定三件事：
  1. 长跑检查器（tools/longrun_check.py）本身能跑通、达标、无残留。
  2. watchdog.sh 崩溃自愈：进程异常退出 → 自动拉起 → 正常退出即停。
  3. 看门狗在 agent_main 正常退出（code 0）时不重启。

全部零网络、可离线跑；长跑轮数在测试里取小值（快速），
全量 500 轮由 `python tools/longrun_check.py` 手动/门禁执行。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PY = sys.executable


def _run(cmd, cwd=ROOT, timeout=300):
    env = dict(os.environ)
    env["UGF_DRY_RUN"] = "1"
    env["UGF_PERCEPTION_BACKEND"] = "mock"
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


# ------------------------------------------------------------------ 长跑检查器

def test_longrun_checker_passes_and_leaves_no_residual():
    """长跑冒烟（一次运行，共享启动开销）：检查器应返回 0、四项检查全绿，
    且项目根不留 video_frames 残留。全量 500 轮由 longrun_check.py 单独执行。"""
    vf = os.path.join(ROOT, "video_frames")
    r = _run([PY, "tools/longrun_check.py", "--rounds", "40", "--rss-limit", "200"], timeout=300)
    assert r.returncode == 0, f"长跑未达标:\n{r.stdout}\n{r.stderr}"
    assert "✅ 达标" in r.stdout
    for token in ("exit_zero", "no_rss_monotonic_growth",
                  "no_fd_leak", "no_residual_files"):
        assert token in r.stdout
    assert not os.path.exists(vf), "长跑后残留 video_frames/"


# ------------------------------------------------------------------ watchdog

def _make_fake_agent(dirpath, exits):
    """在 dirpath 放一个 fake agent_main.py：按 exits 列表依次返回退出码，
    并用计数文件记录被调用次数。"""
    counter = os.path.join(dirpath, "count.txt")
    script = f'''# -*- coding: utf-8 -*-
import os
c = "{counter}"
n = int(open(c).read()) if os.path.exists(c) else 0
with open(c, "w") as f:
    f.write(str(n + 1))
exits = {exits!r}
code = exits[n] if n < len(exits) else 0
raise SystemExit(code)
'''
    with open(os.path.join(dirpath, "agent_main.py"), "w", encoding="utf-8") as f:
        f.write(script)
    return counter


def test_watchdog_restarts_then_stops_on_clean_exit(tmp_path):
    """第一次崩溃(exit 1) → 自动拉起 → 第二次正常(exit 0) → 看门狗退出。"""
    import shutil
    wd = tmp_path / "watchdog.sh"
    shutil.copy(os.path.join(ROOT, "watchdog.sh"), wd)
    counter = _make_fake_agent(str(tmp_path), exits=[1, 0])

    env = dict(os.environ)
    env["UGF_PYTHON"] = PY
    r = subprocess.run(["bash", str(wd)], cwd=str(tmp_path), env=env,
                       capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    assert "崩溃" in out and "自动重启" in out, f"未观察到重启:\n{out}"
    assert r.returncode == 0, f"看门狗最终应 0 退出，实得 {r.returncode}\n{out}"
    assert int(open(counter).read()) == 2, "agent_main 应被调用 2 次"


def test_watchdog_stops_when_agent_exits_zero(tmp_path):
    """agent_main 正常退出(0) 时，看门狗不得重启，只调用一次。"""
    import shutil
    wd = tmp_path / "watchdog.sh"
    shutil.copy(os.path.join(ROOT, "watchdog.sh"), wd)
    counter = _make_fake_agent(str(tmp_path), exits=[0])

    env = dict(os.environ)
    env["UGF_PYTHON"] = PY
    r = subprocess.run(["bash", str(wd)], cwd=str(tmp_path), env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert int(open(counter).read()) == 1, "正常退出不应重启"
    assert "自动重启" not in (r.stdout + r.stderr)
