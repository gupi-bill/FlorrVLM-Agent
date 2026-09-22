#!/usr/bin/env python3
"""
Universal-Game-Framework MCP Server mcp_server.py
=========================================
基于 Model Context Protocol 的标准工具服务端。

知识库：
  - 全部知识以 Markdown (.md) 存储在 ./knowledge_md/
  - 目录不存在自动创建（v0.2）
  - 目录为空时自动写入基础模板文件（v0.2）
  - 默认纯文本关键词检索；向量检索预留开关，默认关闭

MCP 工具（16 个，README 表格与运行时清单由 mcp_tools_check 锁死）：
  kb_list, kb_search, kb_write, kb_append, kb_export, kb_import,
  perceive_game, predict_all_entities, reset_predictor,
  game_action, switch_set, handle_afk,
  query_boss_history, clean_cache, switch_tactic, ugf_guide

SDK 兼容：mcp 1.x 用 FastMCP，2.x 改名 MCPServer；两条路径均在 S9 实测可注册、
可列举、可调用（本机实际为 2.2.0）。
"""
import argparse
import asyncio
import inspect
import json
import os
import random
import shutil
import sys
import time
from typing import Optional

import requests

# mcp 1.x 用 mcp.server.fastmcp.FastMCP；2.x 已将其改名为 mcp.server.mcpserver.MCPServer。
# requirements.txt 已把 mcp 上界锁在 <2.0.0；此处再做一层兼容，避免本机装了 2.x 时直接 import 失败。
# ⚠️ 2.x 还有其它 API 变更，工具注册是否完全可用由 S9 实测确认。
try:
    from mcp.server.fastmcp import FastMCP
    MCP_SDK_VERSION = 1
except ImportError:
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP
        MCP_SDK_VERSION = 2
    except ImportError:
        raise ImportError("请先安装 mcp: pip install 'mcp>=1.0.0,<2.0.0'")

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


def _perception_url() -> str:
    """
    v2.0 S6：端口随配置走（perception.port > server.perception_port），
    避免改了 config.yaml 却仍打 5001 这种"改了没生效"的坑。
    """
    try:
        port = int(config.get("perception.port", 0) or 0)
        if port <= 0:
            port = int(config.get("server.perception_port", 5001) or 5001)
    except (TypeError, ValueError):
        port = 5001
    return f"http://127.0.0.1:{port}/perceive"


# 向量检索开关：默认关闭，J1900 低配机器不用装向量库
# 如需开启，设置环境变量 FLORR_VECTOR_SEARCH=1，并安装 chromadb
USE_VECTOR_SEARCH = os.getenv("FLORR_VECTOR_SEARCH", "0") == "1"


def _stderr(msg: str):
    """
    v2.0 S7：所有启动期输出必须走 stderr。
    MCP stdio 传输把服务端 stdout 当作 JSON-RPC 通道，任何 print 到 stdout 的
    内容都会被客户端解析成协议消息而报 ValidationError（实测复现，S7 修复）。
    """
    try:
        print(msg, file=sys.stderr, flush=True)
    except Exception:
        pass


def _safe_name(name: str, sep: str = "_") -> str:
    """
    v2.0 S9：把外部传入的「文件名 / 游戏名 / 战术名」清洗成单层安全名字。

    MCP 工具的入参来自 LLM 或外部客户端，等同不可信输入。此前
    `filename="../../etc/passwd.md"` 会直接 `os.path.join(KB_DIR, filename)`
    写到知识库之外；`game_name=".."` 会让 kb_list 列出上一级目录。
    统一在这里去掉目录分隔符与 `..` 回溯片段，调用方拿到的一定是单层相对名。
    """
    raw = (name or "").strip()
    raw = raw.replace("\\", sep).replace("/", sep)
    if sep:
        raw = "".join(ch if not ch.isspace() else sep for ch in raw)
    raw = raw.replace("\0", "").replace("..", "")
    return raw.strip().strip(sep).strip(".").strip()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def dry_run() -> bool:
    """UGF_DRY_RUN=1 时不执行任何真实键鼠动作，只走流程与写状态。"""
    return _env_flag("UGF_DRY_RUN")


def _dryrun_log(kind: str, detail: str):
    """dry-run 下把"本该发生的动作"落盘，便于离线验收与回放核对。"""
    try:
        log_dir = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
        os.makedirs(log_dir, exist_ok=True)
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{kind}\t{detail}\n")
        with open(os.path.join(log_dir, "dryrun_actions.log"), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

# 版本号（M5）：对外暴露在 MCP 握手返回的 serverInfo 里，客户端能看出接的是哪一版
VERSION = "2.1.0-mcp"

try:
    mcp = FastMCP("Universal-Game-Framework", version=VERSION)
except TypeError:  # 老版本 SDK 不接受 version 参数
    mcp = FastMCP("Universal-Game-Framework")


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
    _stderr(f"[MCP] 知识库为空，已自动写入 {len(KB_TEMPLATES)} 个基础模板到 {KB_DIR}")


ensure_kb_templates()


# ---------------------------------------------------------------------------
# 知识库工具
# ---------------------------------------------------------------------------
@mcp.tool()
def kb_list(game_name: str = "") -> str:
    """列出知识库里已有的 Markdown 文档名。

    用途：动手前先看本地有没有这个游戏的资料，避免重复研究。
    入参：game_name 可选；给了就只列该游戏文件夹下的文档。
    返回：JSON 字符串——文档名数组。
    下一步：把感兴趣的文档名交给 kb_search 检索正文；没有相关资料就先 kb_write 建一份。
    """
    if game_name:
        safe_game_name = _safe_name(game_name, "_")
        game_dir = os.path.join(KB_DIR, safe_game_name) if safe_game_name else None
        if game_dir and os.path.isdir(game_dir):
            files = sorted(f for f in os.listdir(game_dir) if f.endswith(".md"))
        else:
            files = []
    else:
        files = sorted(f for f in os.listdir(KB_DIR) if f.endswith(".md"))
    return json.dumps(files, ensure_ascii=False, indent=2)


@mcp.tool()
def kb_search(keyword: str, game_name: str = "") -> str:
    """在本地 Markdown 知识库里做关键词检索。

    用途：查某只怪 / 某个 BOSS / 某套战术的已知资料（语义检索优先，不可用时降级为全文匹配）。
    入参：keyword 必填关键词；game_name 可选，限定在某个游戏文件夹内搜索。
    返回：命中的文档片段文本；没有命中时返回空结果或提示文本。
    下一步：把资料用于决策；资料缺失或过时就用 kb_write / kb_append 补上。
    """
    if game_name:
        safe_game_name = _safe_name(game_name, "_")
        search_dir = os.path.join(KB_DIR, safe_game_name) if safe_game_name else None
        if not search_dir or not os.path.isdir(search_dir):
            return f"未找到游戏: {game_name} 的知识库文件夹"
        search_base = search_dir
    else:
        search_base = KB_DIR

    # v2.0 S9：原先此处有 `USE_VECTOR_SEARCH = False` 的局部变量，把模块级
    # FLORR_VECTOR_SEARCH 开关彻底短路成死配置；且 _vector_search 只收 1 个参数，
    # 真放行时会 TypeError。改为读全局开关 + 对齐签名。
    if USE_VECTOR_SEARCH:
        return _vector_search(keyword, search_base)
    return _text_search(keyword, search_base)


def _text_search(keyword: str, search_base: str) -> str:
    """纯文本关键词检索。"""
    results = []
    keyword_lower = keyword.lower()
    for root, dirs, files in os.walk(search_base):
        # 只搜索 md 文件
        md_files = [f for f in files if f.endswith(".md")]
        for fname in sorted(md_files):
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            if keyword_lower in content.lower():
                results.append(f"## {os.path.relpath(fpath, search_base)}\n{content[:2000]}")
    # v2.0 S9：删除 return 之后 3 行不可达代码（S7 遗留），并补上命中计数前缀。
    if not results:
        return "未找到相关内容"
    return f"共找到 {len(results)} 条结果:\n" + "\n\n---\n\n".join(results)


def _vector_search(keyword: str, search_base: str = None) -> str:
    """向量检索（预留，需安装 chromadb + sentence-transformers）。"""
    base = search_base or KB_DIR
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return "[向量检索未安装依赖，回退到文本检索]\n" + _text_search(keyword, base)

    # 预留实现：实际使用时需构建索引
    return "[向量检索预留功能]\n" + _text_search(keyword, base)


@mcp.tool()
def kb_write(filename: str, markdown_content: str, game_name: str = "") -> str:
    """把一段 Markdown 写进知识库（不存在则新建，已存在则整体覆盖）。

    用途：保存新学到的战术、怪物习性、本局结论。
    入参：filename 文件名（不要带路径）；markdown_content 正文；game_name 可选，用于分类到子文件夹。
    返回：成功为「已写入知识库: <路径> (N 字符)」；失败返回「错误: ...」。
    注意：这是覆盖写。想追加请用 kb_append。
    下一步：想追加而不是覆盖，用 kb_append；写完可用 kb_search 抽查内容。
    """
    # v2.0 S9：文件名来自 LLM/外部客户端，先清洗再拒绝空名，
    # 杜绝 `../../` 穿越写到知识库之外、以及空名落到 KB_DIR 目录本身。
    filename = _safe_name(filename, "_")
    if not filename:
        return "错误: filename 不能为空或仅含路径分隔符"
    if not filename.endswith(".md"):
        filename += ".md"

    full_path = _resolve_kb_path(filename, game_name)
    if full_path is None:
        return f"错误: 非法的知识库路径 (filename={filename!r}, game={game_name!r})"

    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(markdown_content or "")
    except OSError as e:
        return f"写入知识库失败: {e}"
    return f"已写入知识库: {full_path} ({len(markdown_content or '')} 字符)"


def _resolve_kb_path(filename: str, game_name: str = ""):
    """
    把 (文件名, 游戏名) 解析成 KB_DIR 内的绝对路径；越界一律返回 None。
    集中一处，保证 kb_write / kb_append 口径完全一致（S9）。
    """
    safe_file = _safe_name(filename, "_")
    if not safe_file:
        return None
    root = KB_DIR
    if game_name:
        safe_game = _safe_name(game_name, "_")
        if safe_game:
            root = os.path.join(KB_DIR, safe_game)
            try:
                os.makedirs(root, exist_ok=True)
            except OSError:
                return None
    full = os.path.normpath(os.path.join(root, safe_file))
    # 二次守门：normpath 后必须仍在 KB_DIR 内
    if os.path.commonpath([os.path.normpath(KB_DIR), full]) != os.path.normpath(KB_DIR):
        return None
    return full


@mcp.tool()
def kb_append(filename: str, markdown_content: str, game_name: str = "") -> str:
    """向知识库已有文档追加内容（文档不存在则自动新建）。

    用途：一局结束后补一行结论、给 BOSS 习性加一条新观察。
    入参：filename、markdown_content、game_name（可选，分类文件夹）。
    返回：成功为「已追加到知识库: <路径>」；失败返回「错误: ...」。
    下一步：配合 kb_search 复用这些累积经验。
    """
    filename = _safe_name(filename, "_")
    if not filename:
        return "错误: filename 不能为空或仅含路径分隔符"
    if not filename.endswith(".md"):
        filename += ".md"

    full_path = _resolve_kb_path(filename, game_name)
    if full_path is None:
        return f"错误: 非法的知识库路径 (filename={filename!r}, game={game_name!r})"

    try:
        mode = "a" if os.path.exists(full_path) else "w"
        with open(full_path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n")
            f.write(markdown_content or "")
    except OSError as e:
        # 注意：这里是"写失败必须显式报错"，S7 的 kb_append 静默失败正是吃了这个亏
        return f"追加到知识库失败: {e}"
    return f"已追加到知识库: {full_path}"


# ---------------------------------------------------------------------------
# 知识库导入导出工具（v2.0）
# ---------------------------------------------------------------------------
def _kb_dirs():
    kb = os.path.join(BASE_DIR, config.get("paths.knowledge_md", "knowledge_md"))
    arch = os.path.join(BASE_DIR, config.get("agent.kb_archive_dir", "knowledge_archive"))
    return kb, arch


@mcp.tool()
def kb_export() -> str:
    """把整个知识库（活跃 + 归档）打包成 tar.gz 备份。

    用途：换机迁移、定期备份。
    入参：无。
    返回：备份文件路径或状态文本。
    下一步：在新机器上用 kb_import 恢复。
    """
    import kb_maintainer
    kb, arch = _kb_dirs()
    return kb_maintainer.export(kb, arch)


@mcp.tool()
def kb_import(backup_path: str) -> str:
    """从 kb_export 生成的 tar.gz 备份恢复知识库（同名文件覆盖）。

    入参：backup_path，备份文件的绝对路径或相对项目根目录的路径。
    返回：恢复结果文本（含恢复的文件数）。
    下一步：kb_list 确认恢复结果，kb_search 抽查具体内容。
    """
    import kb_maintainer
    kb, arch = _kb_dirs()
    if not os.path.isabs(backup_path):
        backup_path = os.path.join(BASE_DIR, backup_path)
    return kb_maintainer.import_backup(kb, arch, backup_path)


# ---------------------------------------------------------------------------
# 游戏感知与预判工具
# ---------------------------------------------------------------------------
@mcp.tool()
def perceive_game() -> str:
    """获取当前游戏画面状态（自身 HP、周围实体列表等），并自动喂给预判模块。

    用途：每一步决策前先「看一眼」，也是 predict_all_entities 的数据来源。
    入参：无。
    返回：JSON 字符串——含自身状态与 entities 实体列表。需要连续调用多帧（≥3 帧）
          后续预判才有效。感知服务不可用时会自动降级为进程内合成帧，
          结果里带 _fallback 标记（离线联调照常可用，不会抛异常）。
    下一步：predict_all_entities 做位置预判，或 kb_search 查资料。
    """
    try:
        resp = requests.get(_perception_url(), timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except requests.ConnectionError:
        # v2.0 S7：dry-run 下不要求外部感知服务常驻 —— 直接在进程内合成一帧，
        # 保证 detect→predict→judge→act 全链路可离线跑通（结果带 _fallback 标记）。
        if dry_run():
            data = _inproc_perception()
        else:
            return json.dumps({"error": "感知服务未启动，请先运行 perception_server.py"},
                              ensure_ascii=False)
    except Exception as e:
        if dry_run():
            data = _inproc_perception(str(e))
        else:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    try:
        # 自动喂给预判模块
        entities = data.get("entities", [])
        predictor.update_frame_entities(entities)

        # 去掉 _raw 减少 token
        data.pop("_raw", None)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"感知结果处理失败: {e}"}, ensure_ascii=False)


def _inproc_perception(reason: str = "") -> dict:
    """
    dry-run 降级：在本进程内直接调用 perception_server 的取帧函数拿一帧 mock 场景。
    与 HTTP 路由共用 build_perception_payload()，避免"降级链路能跑、真实链路跑挂"。
    """
    try:
        import perception_server
        data = perception_server.build_perception_payload("mock")
        data["_fallback"] = "inproc-mock"
        if reason:
            data["_fallback_reason"] = str(reason)[:200]
        _dryrun_log("perceive", f"inproc-mock entities={len(data.get('entities') or [])}")
        return data
    except Exception as e:  # 连降级都失败也必须给出结构化错误，不能抛穿
        _dryrun_log("perceive", f"inproc-mock 失败: {e}")
        return {"error": f"dry-run 进程内感知降级失败: {e}",
                "player": {}, "entities": [], "teammates": []}


@mcp.tool()
def predict_all_entities() -> str:
    """预测画面中全部实体未来约 1.2 秒的位置。

    用途：判断威胁、决定走位与攻击目标。
    入参：无（依赖此前多次 perceive_game 积累的历史帧）。
    返回：JSON 数组，按威胁从高到低最多 8 个实体，每项含 raw_id / rarity / category /
          threat_score / x_now / y_now / x_predict / y_predict / vx_per_sec / vy_per_sec /
          confidence / prediction_trusted。confidence < 0.65 时 prediction_trusted=false
          且 x_predict、y_predict 为 null（此时不要相信预判）。
          历史帧不足时返回 {"status": "insufficient_data", ...}。
    下一步：据此决定 game_action 的 move / attack。
    """
    results = predictor.predict_all_entities()
    if not results:
        return json.dumps({"status": "insufficient_data",
                           "message": "实体历史帧不足（需至少3帧），请先多次调用 perceive_game"},
                          ensure_ascii=False)
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def reset_predictor() -> str:
    """清空预判模块的全部历史帧。

    用途：新开一局、重生、或画面大幅跳变后调用，避免用旧轨迹误判。
    入参：无。返回：确认文本。
    下一步：重新连续调用 perceive_game 积累帧。
    """
    predictor.reset()
    return "预判模块历史数据已清空"


# ---------------------------------------------------------------------------
# 游戏动作工具
# ---------------------------------------------------------------------------
# v0.3 拟人移动：先走到目标附近一个随机中间点，再微移到位，偶尔停顿
# 消除"笔直冲向目标"的机器感
def _path_perturb_move(x: int, y: int):
    # S2 审计 W：与同文件其它键鼠入口保持一致，缺失 pyautogui 时直接返回而非抛 ImportError
    if dry_run():
        return
    try:
        import pyautogui
    except ImportError:
        return
    # 目标点附近随机二次寻路
    mid_x = x + random.uniform(-25, 25)
    mid_y = y + random.uniform(-25, 25)
    pyautogui.moveTo(mid_x, mid_y, duration=0.04)
    # 偶发 100~300ms 停顿，模拟人类反应
    if random.random() < 0.15:
        time.sleep(random.uniform(0.1, 0.3))
    pyautogui.moveTo(x, y, duration=0.06)


# v2.0 S9：合法动作集中定义，校验先于 dry-run 分支，避免无效动作被记成成功
VALID_ACTIONS = ("move", "attack", "defend", "synthesize", "idle")


@mcp.tool()
def game_action(action_type: str,
                x: Optional[int] = None,
                y: Optional[int] = None) -> str:
    """执行一个游戏动作。

    用途：把决策落地成实际操作。
    入参：action_type 必填，取 move / attack / defend / synthesize / idle；
          move 时必须给 x、y 目标坐标（内部会做拟人化路径微扰和偶发停顿）。
          切换套装请用 switch_set，不要用本工具。
    返回：动作执行结果文本。默认 dry-run（UGF_DRY_RUN=1）只校验参数并返回描述，
          不会真的动键鼠；只有在获得授权的环境里才关闭 dry-run。
    下一步：回到 perceive_game → predict_all_entities 的循环；遇到 AFK 弹窗用 handle_afk。
    """
    action_type = (action_type or "").lower()

    # v2.0 S9：合法性校验必须在 dry-run 分支之前。原先 dry-run 直接放行，
    # `game_action("fly")` 会返回"动作已记录"，把无效动作伪装成成功。
    if action_type not in VALID_ACTIONS:
        return f"未知动作类型: {action_type or '(空)'}，可选 {'/'.join(sorted(VALID_ACTIONS))}"

    if action_type == "move" and (x is None or y is None):
        return "move 动作必须提供 x 和 y 坐标"

    # v2.0 S7：dry-run 不做任何真实键鼠动作，只记录"本该执行的动作"并落盘
    if dry_run():
        coord = f" ({x},{y})" if action_type == "move" else ""
        _dryrun_log("action", f"{action_type}{coord}")
        return "[dry-run] 动作已记录（未真实执行）: " + action_type + coord

    try:
        import pyautogui
    except ImportError:
        return "错误: 未安装 pyautogui，请执行 pip install pyautogui"

    if action_type == "move":
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


def resolve_set_keys() -> dict:
    """
    解析当前游戏的「套装名 → 数字键」映射。

    v2.0 S15 修复：`SET_TO_KEY` 原本把 florr 的 5 个套装名（combat/tank/retreat/chase/team）
    硬编码进核心模块。任何非 florr 游戏调用 `switch_set` 都必然落到「未知套装」——
    核心模块认了游戏名，违反「核心只认键的语义」这一设计前提。

    改为按当前档案 `combat.sets` 的声明顺序映射 1~9；档案未声明 sets 时回退 florr 默认
    （florr.yaml 的 sets 顺序恰好等于原硬编码映射，因此对既有行为零影响）。
    """
    sets = config.get("combat.sets")
    if isinstance(sets, (list, tuple)):
        names = [str(s).strip().lower() for s in sets if str(s or "").strip()]
        if names:
            return {name: str(i + 1) for i, name in enumerate(names) if i < 9}
    return dict(SET_TO_KEY)


def normalize_set_name(set_name: str):
    """
    把「抽象决策套装名」翻译成当前游戏档案里的实际套装名；无法翻译时返回 None。

    `combat_judge` 输出的是与游戏无关的决策语义：combat / tank / retreat / chase / team。
    这些名字只对 florr 恰好等于套装名。非 florr 游戏必须由档案的 `combat.set_map`
    声明映射关系（决策语义 → 本游戏套装），否则决策层的输出在换套环节必然失败。
    """
    set_keys = resolve_set_keys()
    name = (set_name or "").strip().lower()
    if not name:
        return None
    if name in set_keys:
        return name
    mapping = config.get("combat.set_map")
    if isinstance(mapping, dict):
        target = str(mapping.get(name) or "").strip().lower()
        if target in set_keys:
            return target
    return None


@mcp.tool()
def switch_set(set_name: str) -> str:
    """切换当前套装 / 阵型。

    入参：set_name 可传当前游戏档案 combat.sets 里的名字（例如 space_invaders 的
          shoot / dodge / focus_mothership），也可传决策层的抽象名
          （combat / tank / retreat / chase / team），后者按档案 combat.set_map 翻译。
    返回：「已切换套装: <名称> (按键 N)」；dry-run 下返回
          「[dry-run] 套装切换已记录（未真实执行）」；传错名字时返回「未知套装: ...」并列出可选值。
    下一步：perceive_game 确认切换生效，再继续决策。
    """
    set_keys = resolve_set_keys()
    resolved = normalize_set_name(set_name)
    if resolved is None:
        return f"未知套装: {set_name}，可选 {'/'.join(set_keys)}"
    key = set_keys[resolved]
    # 抽象名被翻译过时显式标出，便于核对「决策想要什么 → 实际切了什么」
    label = f"{set_name} → {resolved}" if resolved != (set_name or "").strip().lower() else resolved

    # v2.0 S7：dry-run 只记录换套意图，不按真实按键
    if dry_run():
        _dryrun_log("switch_set", f"{label} (按键 {key})")
        return f"[dry-run] 套装切换已记录（未真实执行）: {label} (按键 {key})"

    try:
        import pyautogui
    except ImportError:
        return "错误: 未安装 pyautogui，请执行 pip install pyautogui"

    pyautogui.press(key)
    return f"已切换套装: {label} (按键 {key})"


@mcp.tool()
def handle_afk() -> str:
    """处理游戏内的 AFK 人机验证弹窗。

    用途：长时间挂机触发验证时调用。
    入参：无。
    返回：操作指引文本。
    下一步：结合 perceive_game 返回的弹窗坐标，用 game_action(move) 完成点击验证。
    """
    return ("AFK 弹窗处理流程已触发：请结合 perceive_game 返回的弹窗坐标，"
            "使用 game_action(move/click) 完成验证。")


# ---------------------------------------------------------------------------
# 运行辅助工具（v0.5）
# ---------------------------------------------------------------------------
@mcp.tool()
def query_boss_history(boss_name: str = "") -> str:
    """读取知识库里记录的 BOSS 行为习惯。

    入参：boss_name 可选；不传返回全部记录，传了只返回名字匹配的记录。
    返回：历史习性文本；无记录时返回「知识库还没有 BOSS 行为记录(文件不存在)。」
    下一步：把习性用于决策，打完用 kb_append 补充新观察。
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
    """清理运行期缓存。

    入参：target 取 all（默认，清全部）/ predict（只清预判历史）/ frames（只清临时帧目录）。
    返回：清理结果文本。
    用途：长时间运行后释放磁盘；换局前保证预判数据干净。
    下一步：清完预判历史后重新连续 perceive_game 积累帧；长时间运行前可先清 frames 省磁盘。
    """
    done = []
    if target in ("all", "predict"):
        predictor.reset()
        done.append("预判历史已清空")
    if target in ("all", "frames"):
        frame_dir = os.path.join(BASE_DIR, config.get("paths.frames", "video_frames"))
        # v2.0 S9：目录不存在时也报"已清理"会误导排障，改为区分「已清理/本就不存在」
        if os.path.isdir(frame_dir):
            shutil.rmtree(frame_dir, ignore_errors=True)
            done.append("临时帧目录已清理" if not os.path.isdir(frame_dir) else "临时帧目录清理失败")
        else:
            done.append("临时帧目录不存在（无需清理）")
    return "; ".join(done) if done else f"未知目标: {target}，可选 all/predict/frames"


@mcp.tool()
def switch_tactic(tactic_file: str) -> str:
    """指定知识库里的一份 Markdown 文件作为「当前战术」。

    用途：让后续决策直接读取这份战术，不用每次重新检索。
    入参：tactic_file，知识库中的文档名。
    返回：「已切换当前战术为: <文件名>」；文件名非法或文档不存在时返回对应错误文本。
    下一步：配合 kb_search / kb_append 迭代这份战术。
    """
    raw_name = tactic_file
    tactic_file = _safe_name(tactic_file, "_")
    if not tactic_file:
        return f"错误: 非法的战术文件名: {raw_name!r}"
    if not tactic_file.endswith(".md"):
        tactic_file += ".md"
    src = os.path.join(KB_DIR, tactic_file)
    if not os.path.exists(src):
        return f"知识库中没有这份战术文档: {tactic_file}"
    try:
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        return f"读取战术文档失败: {e}"
    mark = os.path.join(KB_DIR, "_current_tactic.md")
    try:
        with open(mark, "w", encoding="utf-8") as f:
            f.write(f"# 当前战术: {tactic_file}\n\n来自: {tactic_file}\n\n{content[:2000]}")
    except OSError as e:
        return f"写入当前战术标记失败: {e}"
    return f"已切换当前战术为: {tactic_file}"


# ---------------------------------------------------------------------------
# 内置使用手册（M3）
# ---------------------------------------------------------------------------
# 目的：本服务是「装到别的 Agent 上的能力包」，外部模型不一定读得到仓库 README。
# 所以它必须能自助回答「你有什么能力 / 该怎么用」——工具清单从运行时动态取，永不写死、不会漂移。

_GUIDE_CHAINS = """推荐调用链（可直接照抄）：

1) 摸清局面
   perceive_game() → predict_all_entities() → kb_search(keyword=当前最强敌人)

2) 打一局
   perceive_game → predict_all_entities → 自行评估打/跑 → game_action(action_type, x, y)
   → 每若干轮 kb_append(战术/观察) → 结束 kb_write(本局总结)

3) 学一轮
   kb_search(关键词) → 发现缺口 → kb_write(学到的战术) → 下一局 switch_tactic 引用
"""

_GUIDE_NOTES = """注意事项：

- 默认 dry-run（环境变量 UGF_DRY_RUN=1）：game_action / switch_set 只校验参数并返回描述，
  不会真的动键鼠。只有在获得明确授权的环境里才关闭 dry-run。
- 感知服务不是必须的：没有 YOLO/感知服务时 perceive_game 会降级为进程内合成帧，
  返回值带 _fallback 标记，整条链路照样能跑通，方便先联调再上真机。
- predict_all_entities 需要至少 3 帧 perceive_game 历史才有效；confidence < 0.65 时
  prediction_trusted=false，此时不要相信预判坐标。
- 切局 / 重生后先 reset_predictor()，避免用旧轨迹误判。
- 合规：仅用于本地 / 自建 / 已授权环境，不提供任何绕过他人服务条款的手段。
"""


def _runtime_tools() -> list:
    """从运行时的 tool manager 取工具清单（名称 + 描述首行），取不到则退化为空列表。"""
    out = []
    try:
        tm = getattr(mcp, "_tool_manager", None)
        if tm is None:
            return out
        res = tm.list_tools()
        if inspect.isawaitable(res):  # mcp 1.x 部分版本是协程
            res = asyncio.run(res)
        for t in res:
            name = getattr(t, "name", "") or ""
            desc = (getattr(t, "description", "") or "").strip().splitlines()
            out.append((name, desc[0] if desc else ""))
    except Exception:
        return []
    return [x for x in out if x[0]]


@mcp.tool()
def ugf_guide(section: str = "all") -> str:
    """返回本服务的使用手册（给刚接进来的 Agent 看，不用读仓库也能上手）。

    用途：第一次连接时先调用它，了解能力边界、工具清单和推荐调用顺序。
    入参：section 取 all（默认，全部）/ quick（一屏速览）/ tools（工具清单）/
          chains（调用链）/ notes（注意事项与常见坑）。
    返回：Markdown 文本手册。工具清单由运行时动态生成，与实际注册的工具始终一致。
    下一步：按手册里的调用链开始 perceive_game → predict_all_entities → game_action。
    """
    tools = _runtime_tools()
    tool_block = "\n".join(f"- `{n}`：{d}" for n, d in tools) if tools else \
        "- （运行时工具清单不可用，请改用客户端的 tools/list 查看）"

    sec = (section or "all").strip().lower()
    parts = []
    if sec in ("all", "quick"):
        parts.append(
            "# Universal-Game-Framework · 游戏能力包\n\n"
            "给 Agent 用的 MCP 服务：看画面 → 预判 → 查资料 → 出动作 → 复盘学习。\n"
            f"当前共 {len(tools)} 个工具，见 section=tools。\n"
        )
    if sec in ("all", "tools"):
        parts.append("## 工具清单\n\n" + tool_block + "\n")
    if sec in ("all", "chains"):
        parts.append("## " + _GUIDE_CHAINS)
    if sec in ("all", "notes"):
        parts.append("## " + _GUIDE_NOTES)
    if not parts:
        return f"未知章节: {section}，可选 all/quick/tools/chains/notes"
    return "\n".join(parts)


# 资源形式（部分客户端支持 resources；注册失败不影响工具可用性）
try:
    @mcp.resource("ugf://guide")
    def _ugf_guide_resource() -> str:
        return ugf_guide("all")
except Exception:  # pragma: no cover - 取决于 SDK 版本是否支持 resource
    pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _run_args():
    """命令行参数：默认按 config.yaml 的 mcp.streamable_http 决定传输方式。"""
    parser = argparse.ArgumentParser(description="Universal-Game-Framework MCP 服务")
    default_transport = "streamable-http" if config.get("mcp.streamable_http", False) else "stdio"
    parser.add_argument("--transport", default=default_transport,
                        choices=["stdio", "streamable-http", "sse"],
                        help=f"传输方式（默认取自 config.yaml: {default_transport}）")
    parser.add_argument("--host", default=config.get("mcp.host", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=config.get("mcp.streamable_port", 5050))
    parser.add_argument("--version", action="store_true", help="打印版本号并退出")
    args = parser.parse_args()
    if args.version:
        print(f"Universal-Game-Framework {VERSION}")
        raise SystemExit(0)
    return args


def console_main() -> int:
    """控制台入口（`ugf-mcp` 命令 / `python mcp_server.py` 都走这里）。"""
    _stderr(f"[MCP] Universal-Game-Framework 服务启动 v{VERSION}")
    _stderr(f"[MCP] 知识库目录: {KB_DIR}")
    _stderr(f"[MCP] 向量检索: {'开启' if USE_VECTOR_SEARCH else '关闭(默认)'}")
    _stderr(f"[MCP] dry-run: {'开启(不执行真实键鼠)' if dry_run() else '关闭'}")
    args = _run_args()
    if args.transport == "stdio":
        _stderr("[MCP] 传输: stdio")
        mcp.run()
    else:
        _stderr(f"[MCP] 传输: {args.transport} @ http://{args.host}:{args.port}/mcp")
        mcp.run(transport=args.transport, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(console_main())
