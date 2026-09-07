#!/usr/bin/env python3
"""
FlorrVLM-Agent MCP Server mcp_server.py
=========================================
基于 Model Context Protocol 的标准工具服务端。

知识库：
  - 全部知识以 Markdown (.md) 存储在 ./knowledge_md/
  - 目录不存在自动创建
  - 默认纯文本关键词检索；向量检索预留开关，默认关闭

MCP 工具（9 个）：
  kb_list, kb_search, kb_write, kb_append,
  perceive_game, predict_all_entities, reset_predictor,
  game_action, handle_afk
"""
import json
import os
import time
from typing import Optional

import requests

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise ImportError("请先安装 mcp: pip install mcp")

# 本地模块
import predictor

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_md")
os.makedirs(KB_DIR, exist_ok=True)

PERCEPTION_URL = "http://127.0.0.1:5001/perceive"

# 向量检索开关：默认关闭，J1900 低配机器不用装向量库
# 如需开启，设置环境变量 FLORR_VECTOR_SEARCH=1，并安装 chromadb
USE_VECTOR_SEARCH = os.getenv("FLORR_VECTOR_SEARCH", "0") == "1"

mcp = FastMCP("FlorrVLM-Agent")


# ---------------------------------------------------------------------------
# 知识库工具
# ---------------------------------------------------------------------------
@mcp.tool()
def kb_list() -> str:
    """列出知识库中全部 Markdown 文档名称。"""
    files = sorted(f for f in os.listdir(KB_DIR) if f.endswith(".md"))
    return json.dumps(files, ensure_ascii=False, indent=2)


@mcp.tool()
def kb_search(keyword: str) -> str:
    """
    在本地 md 知识库中做关键词检索。
    默认纯文本匹配；向量检索需手动开启 FLORR_VECTOR_SEARCH=1。
    """
    if USE_VECTOR_SEARCH:
        return _vector_search(keyword)
    return _text_search(keyword)


def _text_search(keyword: str) -> str:
    """纯文本关键词检索。"""
    results = []
    keyword_lower = keyword.lower()
    for fname in sorted(os.listdir(KB_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(KB_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        if keyword_lower in content.lower():
            results.append(f"## {fname}\n{content[:2000]}")
    if not results:
        return f"知识库中未找到与「{keyword}」相关的内容。"
    return "\n\n---\n\n".join(results)


def _vector_search(keyword: str) -> str:
    """向量检索（预留，需安装 chromadb + sentence-transformers）。"""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return "[向量检索未安装依赖，回退到文本检索]\n" + _text_search(keyword)

    # 预留实现：实际使用时需构建索引
    return "[向量检索预留功能]\n" + _text_search(keyword)


@mcp.tool()
def kb_write(filename: str, markdown_content: str) -> str:
    """将内容写入知识库，保存为 Markdown 文件。"""
    if not filename.endswith(".md"):
        filename += ".md"
    full_path = os.path.join(KB_DIR, filename)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    return f"已写入知识库: {filename} ({len(markdown_content)} 字符)"


@mcp.tool()
def kb_append(filename: str, markdown_content: str) -> str:
    """追加内容到已有知识库文档（不存在则新建）。"""
    if not filename.endswith(".md"):
        filename += ".md"
    full_path = os.path.join(KB_DIR, filename)
    mode = "a" if os.path.exists(full_path) else "w"
    with open(full_path, mode, encoding="utf-8") as f:
        if mode == "a":
            f.write("\n\n")
        f.write(markdown_content)
    return f"已追加到知识库: {filename}"


# ---------------------------------------------------------------------------
# 游戏感知与预判工具
# ---------------------------------------------------------------------------
@mcp.tool()
def perceive_game() -> str:
    """
    调用本地 YOLO 感知服务，获取当前游戏画面状态。
    同时自动更新 predictor 的实体历史（用于预判）。
    """
    try:
        resp = requests.get(PERCEPTION_URL, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        # 自动喂给预判模块
        entities = data.get("entities", [])
        predictor.update_frame_entities(entities)

        # 去掉 _raw 减少 token
        data.pop("_raw", None)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except requests.ConnectionError:
        return json.dumps({"error": "感知服务未启动，请先运行 perception_server.py"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def predict_all_entities() -> str:
    """
    基于最近多帧坐标，预测全部实体未来 1.2 秒的位置。
    按威胁等级排序，只返回最高前 8 个实体，节省 Token。
    每个实体包含：raw_id, rarity, category, threat_score, x_now, y_now,
                   x_predict, y_predict, vx_per_sec, vy_per_sec, confidence
    """
    results = predictor.predict_all_entities()
    if not results:
        return json.dumps({"status": "insufficient_data",
                           "message": "实体历史帧不足（需至少3帧），请先多次调用 perceive_game"},
                          ensure_ascii=False)
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def reset_predictor() -> str:
    """清空预判模块的全部历史数据（新对局开始时调用）。"""
    predictor.reset()
    return "预判模块历史数据已清空"


# ---------------------------------------------------------------------------
# 游戏动作工具
# ---------------------------------------------------------------------------
@mcp.tool()
def game_action(action_type: str,
                x: Optional[int] = None,
                y: Optional[int] = None) -> str:
    """
    执行 florr.io 游戏键鼠动作。
    action_type: move / attack / defend / synthesize / idle
    move 时需提供 x, y 坐标。
    """
    try:
        import pyautogui
    except ImportError:
        return "错误: 未安装 pyautogui，请执行 pip install pyautogui"

    action_type = action_type.lower()

    if action_type == "move":
        if x is None or y is None:
            return "move 动作必须提供 x 和 y 坐标"
        pyautogui.moveTo(x, y, duration=0.06)
    elif action_type == "attack":
        pyautogui.keyDown("space")
        time.sleep(0.2)
        pyautogui.keyUp("space")
    elif action_type == "defend":
        pyautogui.keyDown("shift")
        time.sleep(0.2)
        pyautogui.keyUp("shift")
    elif action_type == "synthesize":
        pyautogui.press("c")
    elif action_type == "idle":
        time.sleep(0.1)
    else:
        return f"未知动作类型: {action_type}，可选 move/attack/defend/synthesize/idle"

    return f"动作执行成功: {action_type}" + (f" ({x},{y})" if action_type == "move" else "")


@mcp.tool()
def handle_afk() -> str:
    """处理 florr.io 游戏内 AFK 人机验证弹窗。"""
    return ("AFK 弹窗处理流程已触发：请结合 perceive_game 返回的弹窗坐标，"
            "使用 game_action(move/click) 完成验证。")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[MCP] FlorrVLM-Agent 服务启动")
    print(f"[MCP] 知识库目录: {KB_DIR}")
    print(f"[MCP] 向量检索: {'开启' if USE_VECTOR_SEARCH else '关闭(默认)'}")
    mcp.run()
