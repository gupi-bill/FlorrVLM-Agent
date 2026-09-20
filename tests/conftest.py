#!/usr/bin/env python3
"""
pytest 公共夹具（v2.0 S3 起）

职责：
1. 把项目根目录注入 sys.path，使 `import predictor / config / combat_judge ...` 在任何 cwd 下可用。
2. 为无头环境注入缺失的可选依赖 stub（pyautogui / cv2 / PIL），
   让"真实环境跑不了"的分支在测试里也能走到降级路径，而不是直接 ImportError。
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _install_stub(name: str, attrs: dict):
    """仅在目标模块确实不可用时注入 stub，避免污染已安装实现。"""
    try:
        __import__(name)
        return
    except Exception:
        pass
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod


# 无头环境下这三个可选依赖不可用：提供最小 stub，令降级分支可测
_install_stub("pyautogui", {
    "size": lambda: (1920, 1080),
    "position": lambda: (0, 0),
    "moveTo": lambda *a, **k: None,
    "click": lambda *a, **k: None,
    "keyDown": lambda *a, **k: None,
    "keyUp": lambda *a, **k: None,
    "FAILSAFE": False,
    "OFFLINE_STUB": True,
})
_install_stub("cv2", {"OFFLINE_STUB": True})
_install_stub("PIL", {"OFFLINE_STUB": True})
