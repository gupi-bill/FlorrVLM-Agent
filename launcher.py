#!/usr/bin/env python3
"""
Universal-Game-Framework 统一启动器 launcher.py  (v2.0 / S11)
=============================================================
四套前端砍成「1 主 + 1 备选」后，本项目**只认这一个入口**：

    python launcher.py                    # 自动挑一个能跑的 UI
    python launcher.py --ui panel         # 强制用监控大盘（主 UI）
    python launcher.py --ui tk            # 强制用 Tk 离线备选
    python launcher.py --ui cli           # 直接进命令行（永可用）
    python launcher.py --ui auto --selftest   # 只探测并打印选择结果，不真的拉起（CI 用）
    python launcher.py --list             # 列出所有 UI 及其可用性

选型（highest → lowest）：
    admin_panel.py（纯标准库 http.server，无重依赖，跨平台）  ← 主 UI
    ui_tkinter.py（标准库 tkinter，无浏览器也能看）            ← 离线备选
    ui/legacy/ui_pyqt.py / ui/legacy/ui_streamlit.py          ← 已归档，仅 --ui 显式指定才可拉起
    agent_cli.py                                              ← 保底（永远可用）

离线开关（自动透传给子进程，无需手工 export）：
    --dry-run            → UGF_DRY_RUN=1（主循环不碰真实键鼠，动作只落盘）
    --mock               → UGF_PERCEPTION_BACKEND=mock（感知走合成场景，不需要 YOLO/截图）
    （两者都开 = 无 GPU、无 X server、无密钥也能完整演示全链路）

退出码：0=正常；2=指定的 UI 不可用；130=被 Ctrl-C。
"""
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEGACY_DIR = os.path.join(BASE_DIR, "ui", "legacy")

# 环境变量：离线/降级开关
ENV_DRY_RUN = "UGF_DRY_RUN"
ENV_PERCEPTION = "UGF_PERCEPTION_BACKEND"

# UI 定义：(key, 相对路径, 是否主 UI, 额外参数)
UI_TABLE = [
    ("panel", os.path.join(BASE_DIR, "admin_panel.py"), True, []),
    ("tk", os.path.join(BASE_DIR, "ui_tkinter.py"), True, []),
    ("pyqt", os.path.join(LEGACY_DIR, "ui_pyqt.py"), False, []),
    ("streamlit", os.path.join(LEGACY_DIR, "ui_streamlit.py"), False, []),
    ("cli", os.path.join(BASE_DIR, "agent_cli.py"), True, []),
]
# 自动选择顺序
AUTO_ORDER = ["panel", "tk", "cli"]


def _has_display() -> bool:
    """Linux 下没有 DISPLAY / WAYLAND_DISPLAY 时，tk/pyqt 起不来（本机即此种情况）。"""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _importable(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def ui_path(key: str) -> str:
    for k, path, _main, _args in UI_TABLE:
        if k == key:
            return path
    return ""


def availability(key: str) -> tuple:
    """返回 (可用否, 原因)。原因用于在 --list / --selftest 里说明为何不可用。"""
    if key not in [k for k, _p, _m, _a in UI_TABLE]:
        return False, "未知 UI"
    path = ui_path(key)
    if not path or not os.path.exists(path):
        return False, f"文件不存在: {path}"
    if key == "panel":
        # admin_panel.py 只用标准库 http.server，永可用
        return True, "纯标准库监控大盘（推荐）"
    if key == "tk":
        if not _importable("tkinter"):
            return False, "tkinter 不可用（Python 未带 tkinter）"
        if not _has_display():
            return False, "无图形显示（本机无 X server / DISPLAY），自动跳过"
        return True, "离线备选 UI"
    if key == "pyqt":
        if not _importable("PyQt6"):
            return False, "PyQt6 未安装（已归档，非主 UI）"
        if not _has_display():
            return False, "无图形显示"
        return True, "已归档 UI"
    if key == "streamlit":
        if not _importable("streamlit"):
            return False, "streamlit 未安装（依赖重，已归档）"
        return True, "已归档 UI（需 streamlit run）"
    if key == "cli":
        return True, "命令行（保底，永可用）"
    return False, "未知 UI"


def detect() -> dict:
    return {k: availability(k) for k, _p, _m, _a in UI_TABLE}


def choose(mode: str = "auto") -> tuple:
    """按 mode 选出要拉起的 UI，返回 (key, 原因)。选不出时 key=None。"""
    if mode and mode != "auto":
        ok, why = availability(mode)
        return (mode if ok else None), why
    for key in AUTO_ORDER:
        ok, why = availability(key)
        if ok:
            return key, why
    ok, why = availability("cli")
    return ("cli" if ok else None), why


def build_cmd(key: str, extra: list = None) -> list:
    """构造子进程命令。streamlit 需走 `streamlit run`，其余直接用解释器执行。"""
    path = ui_path(key)
    if key == "streamlit":
        return [sys.executable, "-m", "streamlit", "run", path] + (extra or [])
    return [sys.executable, path] + (extra or [])


def child_env(dry_run: bool = False, mock: bool = False) -> dict:
    """在父进程环境基础上叠加离线开关，保证子进程与主进程一致。"""
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR + os.pathsep + env.get("PYTHONPATH", "")
    if dry_run:
        env[ENV_DRY_RUN] = "1"
    if mock:
        env[ENV_PERCEPTION] = "mock"
    return env


def mode_label(dry_run: bool = False, mock: bool = False) -> str:
    """给 UI 展示用的模式串。"""
    backend = os.environ.get(ENV_PERCEPTION, "") or "auto"
    parts = []
    parts.append("dry-run" if dry_run or os.environ.get(ENV_DRY_RUN) == "1" else "在线")
    parts.append("mock 感知" if mock or backend == "mock" else "真实感知")
    return " / ".join(parts)


def selftest_text(mode: str = "auto") -> str:
    lines = ["[统一启动器自检] 环境探测："]
    for key, _p, main, _a in UI_TABLE:
        ok, why = availability(key)
        tag = "✅" if ok else "—"
        kind = "主 UI" if main else "已归档"
        lines.append(f"  {tag} {key:<10} [{kind}] {why}")
    key, why = choose(mode)
    lines.append("")
    if key:
        lines.append(f"选择结果: {key}（{why}）")
    else:
        lines.append(f"选择结果: 无可用 UI（{why}）")
    lines.append(f"离线开关: {mode_label()}")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    selftest = "--selftest" in argv
    list_only = "--list" in argv
    dry_run = "--dry-run" in argv
    mock = "--mock" in argv
    mode = "auto"
    if "--ui" in argv:
        i = argv.index("--ui")
        if i + 1 < len(argv):
            mode = argv[i + 1]
    extra = [a for a in argv if a in ("--dry-run", "--mock")]

    if list_only:
        print(selftest_text("auto"))
        return 0
    if selftest:
        print(selftest_text(mode))
        key, _why = choose(mode)
        return 0 if key else 2

    key, why = choose(mode)
    if not key:
        print(selftest_text(mode))
        print(f"\n✗ 指定的 UI 不可用: {mode}（{why}）。可用 --ui cli 进入命令行。")
        return 2
    # UI 脚本本身不接 --dry-run/--mock，开关通过环境变量透传（见 child_env）
    cmd = build_cmd(key)
    print(f"[launcher] 模式: {mode_label(dry_run, mock)}")
    print(f"[launcher] 启动: {key} —— {why}")
    print(f"[launcher] 命令: {' '.join(cmd)}")
    try:
        return subprocess.call(cmd, cwd=BASE_DIR, env=child_env(dry_run, mock))
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError as e:
        print(f"✗ 启动失败: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
