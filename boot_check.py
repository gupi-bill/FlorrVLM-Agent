#!/usr/bin/env python3
"""
Universal-Game-Framework 启动自检 boot_check.py
=====================================
v2.0（S12 · 运维脚本与容器一致性）

原则：
  1. 不静默失败 —— 缺啥报啥，并给出修复命令 / 降级路径。
  2. **离线优先** —— 本机无 GUI / 无 X server / 无 YOLO 权重是常态，
     这类缺失只给「降级指引」，不阻断启动（旧版把 cv2/PIL 当 ERROR，
     导致无头机器 start_all.sh --fail-fast 直接退出，属误判）。
  3. 口径一致 —— 顺带校验运维脚本（start_all/stop_all/watchdog/Dockerfile）
     引用的文件、端口与代码实际一致，避免"改了配置脚本没跟上"。

用法:
  python boot_check.py                 # 人读报告（默认：WARN 不阻断）
  python boot_check.py --fail-fast     # 供 start_all.sh 调用：有 ERROR 才退出 1
  python boot_check.py --strict        # 把 WARN 也当 ERROR（CI / 容器门禁）
  python boot_check.py --json          # 机器可读
  python boot_check.py --no-ops        # 跳过运维脚本一致性检查

退出码：0=可启动；1=存在 ERROR（或 strict 模式下存在 WARN）。
"""
import argparse
import importlib
import json
import os
import re
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 依赖分级
# core：缺了连"离线/dry-run 全链路"都跑不起来 —— 判定 ERROR。
CORE_LIBS = {
    "yaml": ("配置解析（config.yaml / game_profiles）", "pip install pyyaml"),
    "flask": ("本地面板 / 感知服务", "pip install flask"),
    "requests": ("HTTP 请求（webhook 汇报 / VLM API）", "pip install requests"),
    "numpy": ("数值计算（预判引擎 / 威胁评分）", "pip install numpy"),
}

# optional：无头环境可缺失，代码内置 mock / dry-run 降级 —— 判定 WARN 并给降级路径。
OPTIONAL_LIBS = {
    "PIL": (
        "图像编码（真实截图）",
        "pip install pillow（无头环境可跳过：感知走 mock 后端）",
        "未启用真实截图；perception_server 用 numpy 合成 mock 帧，全链路可跑通。",
    ),
    "cv2": (
        "OpenCV 视觉处理",
        "无头机器装 opencv-python-headless（比 opencv-python 少一层 GUI 依赖）",
        "视频学习 / 图像处理模块降级为不可用；对局主链路不受影响。",
    ),
    "pyautogui": (
        "真实键鼠控制",
        "有显示器 + X server 的机器上 pip install pyautogui",
        "自动降级为 dry-run：动作只记录不下发（UGF_DRY_RUN=1）。",
    ),
}

# 需要可写的目录（相对 BASE_DIR）
NEEDED_DIRS = ["run_logs", "knowledge_md"]

# 运维脚本一致性检查：脚本 -> 它引用的必须存在的文件
OPS_REFS = {
    "start_all.sh": ["boot_check.py", "perception_server.py", "mcp_server.py",
                     "agent_main.py", "admin_panel.py"],
    "stop_all.sh": [],
    "watchdog.sh": ["agent_main.py"],
    "Dockerfile": ["requirements.txt", "boot_check.py", "start_all.sh"],
}


def _read(rel: str) -> str:
    try:
        with open(os.path.join(BASE_DIR, rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _yaml_scalar(key: str, text: str, default=None):
    """极简 YAML 标量提取（避免为取一个端口引入解析失败风险）。"""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*([0-9]+)", text, re.M)
    return int(m.group(1)) if m else default


def config_ports() -> dict:
    """读取 config.yaml 的感知 / 面板端口。"""
    text = _read("config.yaml")
    return {
        "perception_port": _yaml_scalar("perception_port", text, 5001),
        "panel_port": _yaml_scalar("panel_port", text, 5002),
    }


def _dir_writable(path: str) -> tuple:
    """可写性探测：返回 (是否可写, 错误描述)。

    ⚠️ 这里**刻意不做 os.remove 清理**：宿主环境有 safe-delete 批量删除护栏
    （阈值 50 次/turn），全量测试期间累计删除很容易超过阈值，导致探针删除被拦截
    并抛错 → 自检误报「目录不可写」并把 start_all.sh 拦下（S12 实测踩到）。
    故探针改为「复用同一个文件 + 追加打开」，全程零删除；残留文件仅一个空文件，
    由 stop_all.sh 顺带清理。
    """
    try:
        os.makedirs(path, exist_ok=True)
        if not os.access(path, os.W_OK):
            return False, "权限不足（os.access W_OK=False）"
        with open(os.path.join(path, ".write_probe"), "a", encoding="utf-8"):
            pass
        return True, ""
    except OSError as e:
        return False, str(e)


def _issue(level, msg, fix=None, degrade=None) -> dict:
    it = {"level": level, "msg": msg}
    if fix:
        it["fix"] = fix
    if degrade:
        it["degrade"] = degrade
    return it


def _check() -> list:
    """返回问题列表 [{level, msg, fix, degrade}]，空列表表示全部通过。"""
    issues = []

    # 1. Python 版本
    if sys.version_info < (3, 8):
        issues.append(_issue(
            "ERROR", f"Python 版本过低: {sys.version.split()[0]}（需 >= 3.8）",
            "安装 Python 3.8 或更高版本"))

    # 2. 核心依赖（缺 = 阻断）
    for lib, (use, fix) in CORE_LIBS.items():
        try:
            importlib.import_module(lib)
        except ImportError:
            issues.append(_issue("ERROR", f"缺少核心库 {lib}（{use}）", fix))

    # 3. 可选依赖（缺 = 降级，不阻断）
    for lib, (use, fix, degrade) in OPTIONAL_LIBS.items():
        try:
            importlib.import_module(lib)
        except ImportError:
            issues.append(_issue("WARN", f"缺少可选库 {lib}（{use}）", fix, degrade))

    # 4. 运行环境（GUI / X server / 模型权重）—— 只提示降级
    issues.extend(_headless_report())

    # 5. 配置与游戏档案
    if not os.path.exists(os.path.join(BASE_DIR, "config.yaml")):
        issues.append(_issue("ERROR", "缺少配置文件: config.yaml",
                             "从仓库恢复 config.yaml"))
    game = _active_game()
    profile = os.path.join(BASE_DIR, "game_profiles", f"{game}.yaml")
    if not os.path.exists(profile):
        issues.append(_issue(
            "WARN", f"未找到游戏档案: game_profiles/{game}.yaml（将使用兜底默认配置）",
            f"在 game_profiles/ 下新建 {game}.yaml，或改 config.yaml 的 agent.game",
            "核心参数回落到 config.yaml 默认值。"))

    # 6. .env（API Key）—— 缺失只提示，不阻断
    if not os.path.exists(os.path.join(BASE_DIR, ".env")):
        issues.append(_issue(
            "WARN", "未检测到 .env（可能缺少 API Key）",
            "复制 .env.example 为 .env 并填入密钥",
            "无密钥时自动走离线降级：不调用外部 LLM / VLM，决策使用规则兜底。"))

    # 7. 目录可写
    for rel in NEEDED_DIRS:
        d = os.path.join(BASE_DIR, rel)
        ok, err = _dir_writable(d)
        if not ok:
            issues.append(_issue("ERROR", f"目录不可写: {rel}（{err}）",
                                 f"chmod 或换个可写路径: {rel}"))

    # 8. 运维脚本一致性
    issues.extend(check_ops())

    return issues


def _headless_report() -> list:
    """GUI / X server / YOLO 权重检查：一律 WARN + 降级指引（不阻断）。"""
    out = []
    # 注意：DISPLAY 可能被设置但 X server 并不存在（本机即如此），
    # 故以「X socket 是否存在 / 有无 Xvfb」为准，而不是只看环境变量。
    display = os.getenv("DISPLAY") or ""
    x_socket = os.path.isdir("/tmp/.X11-unix") and bool(os.listdir("/tmp/.X11-unix"))
    has_xvfb = shutil.which("Xvfb") is not None
    if not x_socket and not has_xvfb:
        out.append(_issue(
            "WARN",
            f"未检测到图形环境（DISPLAY={display or '未设置'}，无 X socket，且无 Xvfb）",
            "有界面机器：直接运行；无头机器：apt install xvfb 后用 Xvfb :99 起虚拟屏",
            "自动走 mock 感知 + dry-run 动作（UGF_DRY_RUN=1），全部离线链路可验证。"))

    weight_dirs = [os.path.join(BASE_DIR, d) for d in ("models", "weights")]
    has_weights = any(os.path.isdir(d) and os.listdir(d) for d in weight_dirs)
    if not has_weights:
        out.append(_issue(
            "WARN", "未检测到视觉模型权重（models/ 或 weights/ 为空/不存在）",
            "需要真实目标检测时放入 YOLO 权重并在配置里指定路径",
            "目标检测不可用；感知改用 mock 实体（见 game_profiles/<game>.yaml 的 perception.mock）。"))
    return out


def check_ops() -> list:
    """运维脚本口径一致性：引用文件存在 + 端口与 config.yaml 一致。"""
    issues = []
    ports = config_ports()

    for script, refs in OPS_REFS.items():
        path = os.path.join(BASE_DIR, script)
        if not os.path.exists(path):
            issues.append(_issue("ERROR", f"运维脚本缺失: {script}",
                                 f"从仓库恢复 {script}"))
            continue
        for ref in refs:
            if not os.path.exists(os.path.join(BASE_DIR, ref)):
                issues.append(_issue(
                    "ERROR", f"{script} 引用了不存在的 {ref}",
                    f"修正 {script} 的文件名，或恢复 {ref}"))

    # 端口口径：脚本里若写了端口，必须与 config.yaml 一致
    for script in ("start_all.sh", "Dockerfile", "README.md"):
        text = _read(script)
        if not text:
            continue
        for key, val in ports.items():
            for found in re.findall(rf"{key}\s*[:=]\s*\"?(\d+)", text):
                if int(found) != val:
                    issues.append(_issue(
                        "ERROR",
                        f"{script} 中的 {key}={found} 与 config.yaml 的 {val} 不一致",
                        f"把 {script} 的端口改成 {val}，或改 config.yaml 后同步脚本"))
    return issues


def _active_game() -> str:
    """读取当前激活游戏：优先环境变量 AGENT_GAME，其次 config.yaml 的 agent.game。"""
    game = os.getenv("AGENT_GAME")
    if game:
        return game
    try:
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        import config
        return config.get("agent.game", "florr")
    except Exception:
        return "florr"


def _is_ops_issue(it: dict) -> bool:
    return ("运维脚本" in it["msg"]) or ("引用了不存在的" in it["msg"]) \
        or ("与 config.yaml" in it["msg"])


def run(fail_fast: bool = False, strict: bool = False,
        with_ops: bool = True, as_json: bool = False) -> bool:
    """执行自检并打印结果。返回是否可启动（无 ERROR；strict 时无 WARN）。"""
    issues = _check() if with_ops else [i for i in _check()
                                        if not _is_ops_issue(i)]
    errors = [i for i in issues if i["level"] == "ERROR"]
    warns = [i for i in issues if i["level"] == "WARN"]
    if strict:
        errors = errors + warns
        warns = []

    if as_json:
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warns,
            "ports": config_ports(),
        }, ensure_ascii=False, indent=2))
        return not errors

    if not issues:
        print("[自检] ✅ 全部通过，可正常启动。")
        return True

    for it in issues:
        print(f"[{it['level']}] {it['msg']}")
        if it.get("fix"):
            print(f"       修复: {it['fix']}")
        if it.get("degrade"):
            print(f"       降级: {it['degrade']}")

    print(f"\n[自检] 汇总：ERROR {len(errors)} 项 / WARN {len(warns)} 项")
    if errors:
        print("[自检] ❌ 存在错误项，已终止启动（fail-fast）。先修复再启动。"
              if fail_fast else
              "[自检] ❌ 存在错误项，启动后可能运行异常。")
    else:
        print("[自检] ⚠️ 仅有可降级项：可正常启动（自动走 mock / dry-run 分支）。")
    return not errors


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="UGF 启动自检")
    p.add_argument("--fail-fast", action="store_true",
                   help="有 ERROR 时以退出码 1 终止（供 start_all.sh 调用）")
    p.add_argument("--strict", action="store_true",
                   help="WARN 也视为不可启动（CI / 容器门禁）")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.add_argument("--no-ops", action="store_true", help="跳过运维脚本一致性检查")
    a = p.parse_args(argv)
    ok = run(fail_fast=a.fail_fast, strict=a.strict,
             with_ops=not a.no_ops, as_json=a.json)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
