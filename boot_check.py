#!/usr/bin/env python3
"""
FlorrVLM-Agent 启动自检 boot_check.py
=====================================
v1.0 —— 解决"装完开不起来、报错看不懂"的问题。

原则：不静默失败。启动前逐项检查环境与依赖，缺啥报啥，并给出修复命令。
可单独运行: python boot_check.py
也可被 start_all.sh 调用: python boot_check.py --fail-fast

检查项：
  1. Python 版本（需 >= 3.8）
  2. 必需第三方库是否可 import
  3. config.yaml 与当前游戏档案(game_profiles/<agent.game>.yaml)是否存在
  4. .env 是否存在（缺 API Key 时给出提示，但不阻断）
  5. 运行目录是否可写（run_logs / knowledge_md）
"""
import importlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 每个库 -> (用途, 缺时的修复命令)
REQUIRED_LIBS = {
    "yaml": ("配置解析", "pip install pyyaml"),
    "flask": ("本地面板/感知服务", "pip install flask"),
    "requests": ("HTTP 请求", "pip install requests"),
    "PIL": ("图像处理", "pip install pillow"),
    "numpy": ("数值计算", "pip install numpy"),
    "cv2": ("OpenCV 视觉", "pip install opencv-python"),
}

# 需要可写的目录（相对 BASE_DIR）
NEEDED_DIRS = ["run_logs", "knowledge_md"]


def _check() -> list:
    """返回违规项列表 [{level, msg, fix}]，空列表表示全部通过。"""
    issues = []

    # 1. Python 版本
    if sys.version_info < (3, 8):
        issues.append({
            "level": "ERROR",
            "msg": f"Python 版本过低: {sys.version.split()[0]}（需 >= 3.8）",
            "fix": "安装 Python 3.8 或更高版本",
        })

    # 2. 第三方库
    for lib, (use, fix) in REQUIRED_LIBS.items():
        try:
            importlib.import_module(lib)
        except ImportError:
            issues.append({
                "level": "ERROR" if lib else "WARN",
                "msg": f"缺少库 {lib}（{use}）",
                "fix": fix,
            })

    # 3. 配置与游戏档案
    for rel in ["config.yaml"]:
        if not os.path.exists(os.path.join(BASE_DIR, rel)):
            issues.append({
                "level": "ERROR",
                "msg": f"缺少配置文件: {rel}",
                "fix": f"从仓库恢复 {rel}",
            })
    game = _active_game()
    profile = os.path.join(BASE_DIR, "game_profiles", f"{game}.yaml")
    if not os.path.exists(profile):
        issues.append({
            "level": "WARN",
            "msg": f"未找到游戏档案: game_profiles/{game}.yaml（将使用兜底默认配置）",
            "fix": f"在 game_profiles/ 下新建 {game}.yaml，或改 config.yaml 的 agent.game",
        })

    # 4. .env（API Key）—— 缺失只提示，不阻断
    if not os.path.exists(os.path.join(BASE_DIR, ".env")):
        issues.append({
            "level": "WARN",
            "msg": "未检测到 .env（可能缺少 API Key）",
            "fix": "复制 .env.example 为 .env 并填入密钥",
        })

    # 5. 目录可写
    for rel in NEEDED_DIRS:
        d = os.path.join(BASE_DIR, rel)
        try:
            os.makedirs(d, exist_ok=True)
            # 用写探针验证可写性
            probe = os.path.join(d, ".write_probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
        except OSError as e:
            issues.append({
                "level": "ERROR",
                "msg": f"目录不可写: {rel}（{e}）",
                "fix": f"确保 {d} 对当前用户可写",
            })

    return issues


def _active_game() -> str:
    """读取当前激活游戏：优先环境变量 AGENT_GAME，其次 config.yaml 的 agent.game。"""
    game = os.getenv("AGENT_GAME")
    if game:
        return game
    try:
        sys.path.insert(0, BASE_DIR)
        import config
        return config.get("agent.game", "florr")
    except Exception:
        return "florr"


def run(fail_fast: bool = False) -> bool:
    """执行自检，打印结果。返回是否全部通过(无 ERROR)。"""
    issues = _check()
    if not issues:
        print("[自检] ✅ 全部通过，可正常启动。")
        return True

    has_error = False
    for it in issues:
        tag = it["level"]
        if tag == "ERROR":
            has_error = True
        print(f"[{tag}] {it['msg']}")
        if it.get("fix"):
            print(f"      修复: {it['fix']}")

    if fail_fast:
        print("\n[自检] ❌ 存在错误项，已终止启动（fail-fast）。先修复再启动。")
    else:
        print("\n[自检] 存在需要关注的问题；ERROR 项若不修复可能运行异常。")
    return not has_error


if __name__ == "__main__":
    ok = run(fail_fast="--fail-fast" in sys.argv)
    sys.exit(0 if ok else 1)