#!/usr/bin/env python3
"""
FlorrVLM-Agent MCP Server mcp_server.py
=========================================
基于 Model Context Protocol 的标准工具服务端。

知识库：
  - 全部知识以 Markdown (.md) 存储在 ./knowledge_md/
  - 目录不存在自动创建（v0.2）
  - 目录为空时自动写入基础模板文件（v0.2）
  - 默认纯文本关键词检索；向量检索预留开关，默认关闭

MCP 工具（13 个）：
  kb_list, kb_search, kb_write, kb_append,
  perceive_game, predict_all_entities, reset_predictor,
  game_action, switch_set, handle_afk,
  query_boss_history, clean_cache, switch_tactic
"""
import json
import os
import random
import shutil
import time
from typing import Optional

import requests

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise ImportError("请先安装 mcp: pip install mcp")

# 本地模块
import config
import predictor

# ---------------------------------------------------------------------------
# 配置（v0.5：知识库路径来自 config.yaml，改参数不用改源码）
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, config.get("paths.knowledge_md", "knowledge_md"))
os.makedirs(KB_DIR, exist_ok=True)

PERCEPTION_URL = "http://127.0.0.1:5001/perceive"

# 向量检索开关：默认关闭，J1900 低配机器不用装向量库
# 如需开启，设置环境变量 FLORR_VECTOR_SEARCH=1，并安装 chromadb
USE_VECTOR_SEARCH = os.getenv("FLORR_VECTOR_SEARCH", "0") == "1"

mcp = FastMCP("FlorrVLM-Agent")


# ---------------------------------------------------------------------------
# 知识库初始化（v0.2：自动建目录 + 基础模板）
# ---------------------------------------------------------------------------
KB_TEMPLATES = {
    "_README.md": "# 本地知识库\n\n所有知识以 Markdown 存储，由 MCP 工具管理。\n\n## 目录约定\n- `_README.md` 本说明\n- `boss_behavior_log.md` BOSS 行为习惯记录（自动追加）\n- `player_tactics.md` 玩家打法笔记（可手动/自动写入）\n- `review_*.md` 对局复盘（自动生成）\n- `video_tactic_*.md` 视频学习战术（自动生成）\n\n## 检索方式\n默认纯文本关键词检索；设置环境变量 `FLORR_VECTOR_SEARCH=1` 可开启向量检索（需额外安装依赖）。\n",
    "boss_behavior_log.md": "# BOSS 行为日志\n\n记录每次遭遇 BOSS（Super / Unique / Eternal）时的行为习惯：\n- 移动模式\n- 攻击前摇\n- 仇恨切换\n- 击杀/逃脱经验\n\n（由 agent_main.py 每 12 秒批量追加，无需手动维护）\n",
    "player_tactics.md": "# 玩家打法笔记\n\n记录从教程视频 / 对局复盘中学到的打法：\n- 花瓣套装搭配\n- 走位技巧\n- 组队配合\n- 反制套路\n",
    "review_template.md": "# 对局复盘模板\n\n- 结果: 存活 / 死亡\n- 面对怪物: \n- 自身套装: \n- 死亡原因: \n- 可改进点: \n",
}


def ensure_kb_templates():
    """知识库目录为空时自动写入基础模板，保证缺失文件不崩溃。"""
    md_files = [f for f in os.listdir(KB_DIR) if f.endswith(".md")]
    if md_files:
        return
    for fname, content in KB_TEMPLATES.items():
        fpath = os.path.join(KB_DIR, fname)
        if not os.path.exists(fpath):
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
    print(f"[MCP] 知识库为空，已自动写入 {len(KB_TEMPLATES)} 个基础模板到 {KB_DIR}")


ensure_kb_templates()


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
                   x_predict, y_predict, vx_per_sec, vy_per_sec,
                   confidence, prediction_trusted
    confidence < 0.65 时 prediction_trusted=false 且 x_predict/y_predict 为 null。
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
# v0.3 拟人移动：先走到目标附近一个随机中间点，再微移到位，偶尔停顿
# 消除"笔直冲向目标"的机器感
def _path_perturb_move(x: int, y: int):
    import pyautogui
    # 目标点附近随机二次寻路
    mid_x = x + random.uniform(-25, 25)
    mid_y = y + random.uniform(-25, 25)
    pyautogui.moveTo(mid_x, mid_y, duration=0.04)
    # 偶发 100~300ms 停顿，模拟人类反应
    if random.random() < 0.15:
        time.sleep(random.uniform(0.1, 0.3))
    pyautogui.moveTo(x, y, duration=0.06)


@mcp.tool()
def game_action(action_type: str,
                x: Optional[int] = None,
                y: Optional[int] = None) -> str:
    """
    执行 florr.io 游戏键鼠动作。
    action_type: move / attack / defend / synthesize / idle
    move 时需提供 x, y 坐标，会自动做拟人化路径微扰+偶发停顿。
    套装切换请使用独立工具 switch_set。
    """
    try:
        import pyautogui
    except ImportError:
        return "错误: 未安装 pyautogui，请执行 pip install pyautogui"

    action_type = action_type.lower()

    if action_type == "move":
        if x is None or y is None:
            return "move 动作必须提供 x 和 y 坐标"
        _path_perturb_move(x, y)
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


# v0.3 套装切换：映射到数字键 1~5（florr.io 花瓣槽位）
SET_TO_KEY = {
    "combat": "1",
    "tank": "2",
    "retreat": "3",
    "chase": "4",
    "team": "5",
}


@mcp.tool()
def switch_set(set_name: str) -> str:
    """
    切换花瓣套装（v0.3）。
    set_name: combat / tank / retreat / chase / team。
    通过按数字键完成切换。
    """
    try:
        import pyautogui
    except ImportError:
        return "错误: 未安装 pyautogui，请执行 pip install pyautogui"

    key = SET_TO_KEY.get(set_name.lower())
    if key is None:
        return f"未知套装: {set_name}，可选 {'/'.join(SET_TO_KEY)}"
    pyautogui.press(key)
    return f"已切换套装: {set_name} (按键 {key})"


@mcp.tool()
def handle_afk() -> str:
    """处理 florr.io 游戏内 AFK 人机验证弹窗。"""
    return ("AFK 弹窗处理流程已触发：请结合 perceive_game 返回的弹窗坐标，"
            "使用 game_action(move/click) 完成验证。")


# ---------------------------------------------------------------------------
# 运行辅助工具（v0.5）
# ---------------------------------------------------------------------------
@mcp.tool()
def query_boss_history(boss_name: str = "") -> str:
    """
    读取知识库里的 BOSS 行为习惯记录。
    缺省返回全部；传入 boss_name 则只返回包含该名字的记录。
    """
    fpath = os.path.join(KB_DIR, "boss_behavior_log.md")
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return "知识库还没有 BOSS 行为记录(文件不存在)。"
    if not boss_name:
        return content or "知识库还没有 BOSS 行为记录。"
    # 按 "### " 小节切分，只看命中的段落
    hits = [seg for seg in content.split("### ")
            if boss_name.lower() in seg.lower()]
    return ("\n\n".join(f"### {seg}" for seg in hits)
            if hits else f"知识库中没有关于「{boss_name}」的 BOSS 行为记录。")


@mcp.tool()
def clean_cache(target: str = "all") -> str:
    """
    清理运行期缓存。
    target: all(默认, 清预判历史)/ predict(只清预判) / frames(只清临时帧目录)。
    """
    done = []
    if target in ("all", "predict"):
        predictor.reset()
        done.append("预判历史已清空")
    if target in ("all", "frames"):
        frame_dir = os.path.join(BASE_DIR, config.get("paths.frames", "video_frames"))
        if os.path.isdir(frame_dir):
            shutil.rmtree(frame_dir, ignore_errors=True)
        done.append("临时帧目录已清理")
    return "; ".join(done) if done else f"未知目标: {target}，可选 all/predict/frames"


@mcp.tool()
def switch_tactic(tactic_file: str) -> str:
    """
    指定知识库里的一份 Markdown 文件作为"当前战术"。
    会在玩家战术文档(_current_tactic.md)里记录，供后续决策快速读取。
    """
    if not tactic_file.endswith(".md"):
        tactic_file += ".md"
    src = os.path.join(KB_DIR, tactic_file)
    if not os.path.exists(src):
        return f"知识库中没有这份战术文档: {tactic_file}"
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    mark = os.path.join(KB_DIR, "_current_tactic.md")
    with open(mark, "w", encoding="utf-8") as f:
        f.write(f"# 当前战术: {tactic_file}\n\n来自: {tactic_file}\n\n{content[:2000]}")
    return f"已切换当前战术为: {tactic_file}"


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[MCP] FlorrVLM-Agent 服务启动")
    print(f"[MCP] 知识库目录: {KB_DIR}")
    print(f"[MCP] 向量检索: {'开启' if USE_VECTOR_SEARCH else '关闭(默认)'}")
    mcp.run()
