#!/usr/bin/env python3
"""
FlorrVLM-Agent 感知服务 perception_server.py
==============================================
监听 127.0.0.1:5001，供 MCP Agent 通过 perceive_game 调用。

功能：
- 截图屏幕，传给 florr_powerful_tools 的 YOLO 模型
- 输出统一结构化 JSON：player, entities, afk_popup
- 截图用完立刻删除，不占硬盘
- YOLO 卡住/CPU 满载时超时跳过，不崩溃
- 截图失败静默丢弃，不写错误文件
- 自动过滤非法/负数/越界坐标实体
"""
import json
import os
import subprocess
import sys
import time

from flask import Flask, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLORR_TOOLS_DIR = os.path.join(BASE_DIR, "florr_powerful_tools")
SCREENSHOT_PATH = "/tmp/florr_frame.png"
YOLO_TIMEOUT = 8          # YOLO 检测超时秒数，超过就跳过这一帧
SKIP_ON_TIMEOUT = 0.8     # 超时时休眠秒数，给 CPU 喘息

# 屏幕尺寸（用于越界过滤，可被实际分辨率覆盖）
SCREEN_W = 1920
SCREEN_H = 1080


# ---------------------------------------------------------------------------
# YOLO 调用
# ---------------------------------------------------------------------------
def _find_detect_script() -> str:
    """自动查找 florr_powerful_tools 的检测入口脚本。"""
    candidates = ["detect.py", "main.py", "yolo_detect.py", "infer.py", "run.py"]
    for name in candidates:
        p = os.path.join(FLORR_TOOLS_DIR, name)
        if os.path.exists(p):
            return p
    return ""


def _run_yolo(image_path: str) -> dict:
    """
    调用 YOLO 检测脚本，返回原始检测结果。
    超时返回 {"_timeout": true}，由调用方决定跳过。
    """
    detect_script = _find_detect_script()
    if not detect_script:
        return {"error": f"检测脚本未找到，请在 {FLORR_TOOLS_DIR} 内确认入口文件名"}

    try:
        proc = subprocess.run(
            [sys.executable, detect_script, "--image", image_path],
            capture_output=True,
            text=True,
            cwd=FLORR_TOOLS_DIR,
            timeout=YOLO_TIMEOUT,
        )
        stdout = proc.stdout.strip()
        if not stdout:
            return {"error": "YOLO 无输出", "stderr": proc.stderr[-300:]}
        return json.loads(stdout)
    except subprocess.TimeoutExpired:
        return {"_timeout": True}
    except json.JSONDecodeError as e:
        return {"error": f"YOLO 输出不是 JSON: {e}", "raw": stdout[-300:] if 'stdout' in dir() else ""}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 实体过滤与标准化
# ---------------------------------------------------------------------------
def _is_valid_entity(ent: dict) -> bool:
    """过滤非法实体：缺字段、负数坐标、越界坐标。"""
    if not isinstance(ent, dict):
        return False
    if "raw_id" not in ent or "x" not in ent or "y" not in ent:
        return False
    try:
        x = float(ent["x"])
        y = float(ent["y"])
    except (TypeError, ValueError):
        return False
    if x < 0 or y < 0:
        return False
    if x > SCREEN_W * 2 or y > SCREEN_H * 2:
        return False
    return True


def _normalize_entities(raw: list) -> list:
    """标准化实体列表，过滤非法项。"""
    result = []
    if not isinstance(raw, list):
        return result
    for ent in raw:
        if _is_valid_entity(ent):
            result.append({
                "raw_id": str(ent.get("raw_id", "unknown")),
                "rarity": str(ent.get("rarity", "Common")),
                "x": round(float(ent["x"]), 1),
                "y": round(float(ent["y"]), 1),
            })
    return result


def _normalize_player(raw: dict) -> dict:
    """标准化玩家状态。"""
    if not isinstance(raw, dict):
        return {"alive": True, "hp": 100, "max_hp": 100, "x": 0, "y": 0}
    return {
        "alive": bool(raw.get("alive", True)),
        "hp": float(raw.get("hp", 100)),
        "max_hp": float(raw.get("max_hp", 100)),
        "x": float(raw.get("x", 0)),
        "y": float(raw.get("y", 0)),
        "power_score": float(raw.get("power_score", 100)),
        "petal_set": str(raw.get("petal_set", "combat")),
        "talent": str(raw.get("talent", "none")),
    }


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.route("/perceive", methods=["GET"])
def perceive():
    """
    截图 → YOLO → 标准化 → 删除截图 → 返回 JSON。
    YOLO 超时时返回 {"_skipped": true}，Agent 应跳过这一帧。
    """
    # 1. 截图
    try:
        subprocess.run(["scrot", "-o", SCREENSHOT_PATH],
                       check=True, capture_output=True, timeout=5)
    except Exception:
        try:
            subprocess.run(["import", "-window", "root", SCREENSHOT_PATH],
                           check=True, capture_output=True, timeout=5)
        except Exception:
            # 截图失败，静默返回空帧（不写错误文件）
            return jsonify({
                "player": {"alive": True, "hp": 100, "max_hp": 100, "x": 0, "y": 0},
                "entities": [],
                "afk_popup": False,
                "_skipped": True,
                "_reason": "screenshot_failed",
            })

    # 2. YOLO 检测（用完立刻删截图）
    try:
        detections = _run_yolo(SCREENSHOT_PATH)
    finally:
        # 无论成功失败，截图用完立刻删
        if os.path.exists(SCREENSHOT_PATH):
            try:
                os.remove(SCREENSHOT_PATH)
            except OSError:
                pass

    # 3. YOLO 超时 → 跳过这帧，给 CPU 喘息
    if detections.get("_timeout"):
        time.sleep(SKIP_ON_TIMEOUT)
        return jsonify({
            "player": {"alive": True, "hp": 100, "max_hp": 100, "x": 0, "y": 0},
            "entities": [],
            "afk_popup": False,
            "_skipped": True,
            "_reason": "yolo_timeout",
        })

    # 4. 标准化输出
    player = _normalize_player(detections.get("player", {}))
    entities = _normalize_entities(detections.get("entities", detections.get("monsters", [])))
    afk_popup = bool(detections.get("afk_popup", False))

    return jsonify({
        "player": player,
        "entities": entities,
        "afk_popup": afk_popup,
        "_raw": detections,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "florr_tools_dir": FLORR_TOOLS_DIR,
        "detect_script": _find_detect_script(),
        "yolo_timeout": YOLO_TIMEOUT,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
