#!/usr/bin/env python3
"""
FlorrVLM-Agent 主程序 agent_main.py
=====================================
MCP Client 主循环，串联全部模块：

  感知(perceive_game) → 预判(predict_all_entities) → 战斗评估(combat_judge)
  → LLM 决策 → 执行(game_action，带移动抖动) → 循环

附加功能：
- 死亡防抖：连续 2 帧 alive=false 才判定真实死亡
- 复盘过滤：只有 highest_boss / boss / 组队对局才生成复盘 md
- 统一复盘模板（v0.2）：结果 / 面对怪物 / 自身套装 / 死亡原因 / 可改进点
- 崩溃兜底清理（v0.2）：启动时清理上次残留的临时帧目录与截图
- BOSS 习惯记忆：每 12 秒批量追加写入 knowledge_md
- 鼠标角落安全暂停：鼠标碰到屏幕四角自动暂停
- 滚动日志：run_logs/ 最大 500KB 自动截断
- 随机抖动：移动坐标加固定小范围偏移，模拟真人
- highest_boss 动态避险：实力强可周旋，弱全力逃跑
- 组队协同：读取队友花瓣套装，调整我方推荐套装
- 实力评估防抖（v0.2）：CombatEvaluator 每 0.7s 重算一次

v0.3 基础战术扩充：
- 多套装自动切换：按战斗评估结果调用 switch_set，实际切换
- 战术记忆：每次换套写入 player_tactics.md（什么情况用什么套）
- BOSS 习性记忆增强：不只记坐标，归纳移动模式/追踪距离/攻击接近
- 简单组队协同：识别队友 → 分工 → 保持距离跟随
- 安全区检测：走位目标钳制在安全区内，防贴墙卡死
- 随机停顿：偶发 100~300ms 停顿 + 移动路径微扰（拟人）
"""
import argparse
import asyncio
import json
import math
import os
import random
import shutil
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
LLM_API_URL = os.getenv("LLM_API_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_SERVER_SCRIPT = os.path.join(BASE_DIR, "mcp_server.py")
LOG_DIR = os.path.join(BASE_DIR, "run_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 死亡防抖
DEATH_FRAME_THRESHOLD = 2     # 连续 N 帧死亡才判定
# BOSS 记忆写入间隔
BOSS_MEMORY_INTERVAL = 12     # 每 12 秒批量写一次
# 日志上限
LOG_MAX_SIZE = 500 * 1024     # 500KB
# 鼠标角落安全暂停
CORNER_MARGIN = 20            # 距离边缘 20 像素内触发暂停

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("错误: 请先安装 mcp: pip install mcp")
    sys.exit(1)

# 本地模块
import combat_judge

SERVER_PARAMS = StdioServerParameters(command=sys.executable, args=[MCP_SERVER_SCRIPT])


# ---------------------------------------------------------------------------
# 滚动日志
# ---------------------------------------------------------------------------
def log(msg: str):
    """写滚动日志，超过 500KB 自动截断旧内容。"""
    log_file = os.path.join(LOG_DIR, "agent.log")
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"
    try:
        # 检查大小，超限就截断
        if os.path.exists(log_file) and os.path.getsize(log_file) > LOG_MAX_SIZE:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # 保留后半部分
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[len(lines) // 2:])
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(line.rstrip())


# ---------------------------------------------------------------------------
# 崩溃兜底清理（v0.2）
# ---------------------------------------------------------------------------
def startup_cleanup():
    """
    启动时清理上次可能残留的临时文件：
    - video_frames/ 临时帧目录
    - /tmp/florr_frame.png 临时截图
    """
    frame_dir = os.path.join(BASE_DIR, "video_frames")
    if os.path.isdir(frame_dir):
        try:
            shutil.rmtree(frame_dir, ignore_errors=True)
            log(f"[清理] 已删除残留临时帧目录 {frame_dir}")
        except Exception as e:
            log(f"[清理] 删除临时帧目录失败: {e}")

    tmp_shot = "/tmp/florr_frame.png"
    if os.path.exists(tmp_shot):
        try:
            os.remove(tmp_shot)
            log("[清理] 已删除残留临时截图 /tmp/florr_frame.png")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# LLM 决策
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是 FlorrVLM-Agent，一个玩 florr.io 的游戏智能体，目标是优先保命、持续作战。
可调用工具：perceive_game, kb_search, predict_all_entities, game_action, kb_write, handle_afk, reset_predictor。
套装切换(switch_set)由战斗评估自动执行，无需你手动调用。
决策规则：
- afk_popup=true 优先处理验证
- 遇 highest_boss(Unique/Eternal) 时，根据自身实力评估：实力不足全力避险，实力充足可谨慎周旋
- 预判置信度<0.6 时，降低对预判坐标的依赖，更多参考当前画面
- 有队友时注意保持安全距离，配合分工
- 每步只输出一个动作 JSON：{"action":"move","x":100,"y":200}
动作：move(x,y) / attack / defend / synthesize / idle。"""


def llm_decide(game_state: str, predictions: str, combat_eval: str,
               kb_tactics: str) -> dict:
    """调用 LLM 决策，无 API 时走兜底逻辑。"""
    if not LLM_API_URL or not LLM_API_KEY:
        return _fallback_decide(game_state, combat_eval)

    headers = {"Authorization": f"Bearer {LLM_API_KEY}",
               "Content-Type": "application/json"}
    user_content = (
        f"当前游戏状态:\n{game_state}\n\n"
        f"实体预判(未来1.2秒):\n{predictions}\n\n"
        f"战斗评估:\n{combat_eval}\n\n"
        f"知识库战术:\n{kb_tactics}\n\n"
        "请输出下一步动作的 JSON。"
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 150,
        "temperature": 0.3,
    }
    try:
        resp = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        log(f"[LLM] 决策失败，使用兜底: {e}")
        return _fallback_decide(game_state, combat_eval)


def _fallback_decide(game_state_str: str, combat_eval_str: str) -> dict:
    """无 LLM 时的兜底决策。"""
    try:
        state = json.loads(game_state_str)
    except Exception:
        return {"action": "idle"}
    try:
        ev = json.loads(combat_eval_str)
    except Exception:
        ev = {}

    if state.get("afk_popup"):
        return {"action": "idle"}

    decision = ev.get("decision", "fight")
    if decision == "retreat":
        # 跑路：往远离最高威胁的方向移动
        return {"action": "defend"}
    if decision == "cautious_fight":
        return {"action": "attack"}
    return {"action": "attack"}


# ---------------------------------------------------------------------------
# 复盘与记忆
# ---------------------------------------------------------------------------
def _should_review(state_data: dict, has_teammate: bool) -> bool:
    """复盘过滤：只有 highest_boss / boss / 组队对局才生成复盘。"""
    entities = state_data.get("entities", [])
    has_boss = any(e.get("category") in ("highest_boss", "boss") for e in entities)
    # 注意：perceive 返回的 entities 还没经过 predictor 分类，
    # 这里用 rarity 粗判
    has_boss = has_boss or any(
        e.get("rarity", "").capitalize() in ("Super", "Unique", "Eternal")
        for e in entities
    )
    return has_boss or has_teammate


async def review_round(session, survived: bool, note: str, state: str):
    """对局复盘，按统一模板写入知识库 md（v0.2）。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outcome = "存活" if survived else "死亡"

    # 从最终画面状态尽力提取字段
    monster_info, set_info, cause = "未知", "未知", note
    try:
        s = json.loads(state)
        p = s.get("player", {})
        set_info = p.get("petal_set", "未知")
        ents = s.get("entities", [])
        if ents:
            monster_info = "、".join(
                f"{e.get('raw_id','?')}({e.get('rarity','?')})" for e in ents[:5]
            )
        if not survived:
            cause = f"死亡。当时面对怪物: {monster_info}，自身套装: {set_info}"
    except Exception:
        pass

    content = (
        f"# 对局复盘 — {timestamp}\n\n"
        f"- 结果: {outcome}\n"
        f"- 面对怪物: {monster_info}\n"
        f"- 自身套装: {set_info}\n"
        f"- 死亡原因: {cause}\n"
        f"- 可改进点: {note}\n"
    )
    await session.call_tool("kb_write", {
        "filename": f"review_{timestamp}",
        "markdown_content": content,
    })
    await session.call_tool("reset_predictor")
    log(f"[复盘] 对局结束，结果={outcome}，经验已写入知识库，预判历史已清空")


# ---------------------------------------------------------------------------
# BOSS 习惯记忆（v0.3 增强：归纳行为模式）
# ---------------------------------------------------------------------------
BOSS_SAMPLE_MAX = 120       # 每种 BOSS 最多保留多少个坐标样本（防内存膨胀）
BOSS_CLOSE_DIST = 120       # 距离玩家多少像素内视为"接近/攻击"


def _analyze_boss_behavior(samples: list) -> str:
    """
    从坐标样本归纳 BOSS 行为模式。
    samples: [(ex, ey, px, py), ...]（BOSS 位置 + 玩家位置）
    返回一句话：移动模式 + 追踪距离 + 攻击接近倾向。
    """
    n = len(samples)
    if n < 3:
        return "样本不足，暂无法归纳"
    # 移动模式：平均每次转角大小决定 绕圈/直线/徘徊
    turns = []
    for i in range(1, n - 1):
        ax = samples[i][0] - samples[i - 1][0]
        ay = samples[i][1] - samples[i - 1][1]
        bx = samples[i + 1][0] - samples[i][0]
        by = samples[i + 1][1] - samples[i][1]
        da = (ax * ax + ay * ay) ** 0.5
        db = (bx * bx + by * by) ** 0.5
        if da < 1 or db < 1:
            continue
        cos_t = max(-1.0, min(1.0, (ax * bx + ay * by) / (da * db)))
        turns.append(math.degrees(math.acos(cos_t)))
    avg_turn = sum(turns) / len(turns) if turns else 0.0
    if avg_turn > 30:
        pattern = "绕圈/游走"
    elif avg_turn < 15:
        pattern = "直线移动"
    else:
        pattern = "缓行徘徊"

    dists = [((px - ex) ** 2 + (py - ey) ** 2) ** 0.5
             for ex, ey, px, py in samples]
    avg_dist = sum(dists) / len(dists)
    close_cnt = sum(1 for d in dists if d < BOSS_CLOSE_DIST)
    return (f"{pattern}；平均距离玩家约 {avg_dist:.0f}px；"
            f"近距离接近 {close_cnt} 次（越接近越凶/仇恨越强）")


async def write_boss_memory(session, boss_observations: list, boss_samples: dict = None):
    """每 12 秒批量写入 BOSS 行为习惯记忆（轨迹 + 行为归纳）。"""
    if not boss_observations:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    content = f"# BOSS 行为观察 — {timestamp}\n\n"
    for obs in boss_observations:
        content += f"- {obs}\n"
    # v0.3：多次遭遇累计的行为共性归纳
    if boss_samples:
        content += "\n## 行为归纳（多次遭遇累计共性）\n"
        for uid, samples in boss_samples.items():
            if len(samples) >= 3:
                content += f"- {uid}: {_analyze_boss_behavior(samples)}\n"
    await session.call_tool("kb_append", {
        "filename": "boss_behavior_log",
        "markdown_content": content,
    })
    log(f"[记忆] 已写入 {len(boss_observations)} 条 BOSS 行为观察")


# ---------------------------------------------------------------------------
# 鼠标角落安全检查
# ---------------------------------------------------------------------------
def _is_mouse_in_corner(screen_w: int = 1920, screen_h: int = 1080) -> bool:
    """检查鼠标是否在屏幕四角（安全暂停触发）。"""
    try:
        import pyautogui
        x, y = pyautogui.position()
        return (x < CORNER_MARGIN or x > screen_w - CORNER_MARGIN or
                y < CORNER_MARGIN or y > screen_h - CORNER_MARGIN)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
async def run_agent(interval: float = 0.5, max_rounds: int = 0):
    log("=" * 55)
    log("  FlorrVLM-Agent 启动 (MCP Client + 预判 + 战斗评估)")
    log("=" * 55)

    # v0.2 崩溃兜底：启动时清理残留临时文件
    startup_cleanup()

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            log(f"[MCP] 已连接，可用工具: {[t.name for t in tools.tools]}")

            kb_result = await session.call_tool("kb_list")
            log(f"[知识库] 当前文档: {kb_result.content[0].text[:150]}")

            # 运行状态
            round_count = 0
            game_state = "{}"
            death_streak = 0          # 连续死亡帧数
            last_boss_memory_time = 0
            boss_observations = []
            boss_samples = {}         # v0.3：BOSS 坐标样本，累积归纳习性
            current_set = "combat"    # 当前套装，用于换套去抖
            paused = False
            evaluator = combat_judge.CombatEvaluator()  # v0.2 评估防抖

            log("\n[Agent] 进入游戏主循环...\n")

            try:
                while True:
                    round_count += 1
                    if max_rounds and round_count > max_rounds:
                        log("[Agent] 达到最大轮数，退出")
                        break

                    # 鼠标角落安全暂停
                    if _is_mouse_in_corner():
                        if not paused:
                            log("[安全] 鼠标在屏幕角落，暂停 Agent")
                            paused = True
                        await asyncio.sleep(1)
                        continue
                    if paused:
                        log("[安全] 鼠标离开角落，恢复 Agent")
                        paused = False

                    # 1. 感知
                    perceive_result = await session.call_tool("perceive_game")
                    game_state = perceive_result.content[0].text

                    if '"_skipped"' in game_state:
                        log("[感知] YOLO 超时或截图失败，跳过本帧")
                        await asyncio.sleep(interval)
                        continue
                    if '"error"' in game_state:
                        log(f"[感知] 异常: {game_state[:100]}")
                        await asyncio.sleep(2)
                        continue

                    state_data = json.loads(game_state)
                    player = state_data.get("player", {})

                    # 2. 死亡防抖检测
                    if not player.get("alive", True):
                        death_streak += 1
                        if death_streak >= DEATH_FRAME_THRESHOLD:
                            # 判定真实死亡，复盘（过滤普通小怪局）
                            has_teammate = bool(state_data.get("teammates", []))
                            if _should_review(state_data, has_teammate):
                                await review_round(session, False,
                                                   "玩家死亡，复盘本局",
                                                   game_state)
                            else:
                                log("[复盘] 普通小怪局，不生成复盘 md（节省硬盘）")
                                await session.call_tool("reset_predictor")
                            death_streak = 0
                            evaluator.invalidate()  # 死亡后强制重算
                            await asyncio.sleep(2)
                            continue
                    else:
                        death_streak = 0

                    # 3. 预判
                    pred_result = await session.call_tool("predict_all_entities")
                    predictions = pred_result.content[0].text

                    # 4. 战斗评估（v0.2 防抖：0.7s 内命中缓存不重算）
                    pred_data = json.loads(predictions) if predictions.startswith("[") else []
                    # v0.3 组队识别：perceive 已返回队友列表
                    teammates = [
                        combat_judge.Teammate(
                            raw_id=t.get("raw_id", "ally"),
                            petal_set=t.get("petal_set", "combat"),
                            x=t.get("x", 0),
                            y=t.get("y", 0),
                        )
                        for t in state_data.get("teammates", [])
                    ]
                    ctx = combat_judge.CombatContext(
                        player=combat_judge.PlayerState(
                            hp=player.get("hp", 100),
                            max_hp=player.get("max_hp", 100),
                            power_score=player.get("power_score", 100),
                            current_set=current_set,
                            talent=player.get("talent", "none"),
                            x=player.get("x", 0),
                            y=player.get("y", 0),
                        ),
                        enemies=pred_data if isinstance(pred_data, list) else [],
                        teammates=teammates,
                    )
                    combat_eval = evaluator.evaluate(ctx)
                    combat_eval_str = json.dumps(combat_eval, ensure_ascii=False)

                    # 5. 套装自动切换 + 战术记忆（v0.3）
                    recommended_set = combat_eval.get("recommended_set")
                    if recommended_set and recommended_set != current_set:
                        await session.call_tool("switch_set", {"set_name": recommended_set})
                        await session.call_tool("kb_append", {
                            "filename": "player_tactics",
                            "markdown_content": (
                                f"- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                                f"决策={combat_eval.get('decision')} "
                                f"心态={combat_eval.get('mindset')} "
                                f"威胁比={combat_eval.get('threat_ratio')} "
                                f"→ 换 {recommended_set} 套"
                            ),
                        })
                        log(f"[套装] {current_set} → {recommended_set}，已记入 player_tactics.md")
                        current_set = recommended_set

                    # 6. 检索知识库
                    keyword = "boss" if combat_eval.get("has_highest_boss") else "战术"
                    kb_result = await session.call_tool("kb_search", {"keyword": keyword})
                    kb_tactics = kb_result.content[0].text

                    # 7. LLM 决策
                    action = llm_decide(game_state, predictions, combat_eval_str, kb_tactics)
                    if not action:
                        action = {"action": "idle"}

                    # 8. 移动抖动 + 安全区钳制（v0.3 防贴墙卡死）
                    action_type = action.get("action", "idle")
                    action_args = {"action_type": action_type}
                    if action_type == "move":
                        tx = action.get("x", 400)
                        ty = action.get("y", 300)
                        tx, ty = combat_judge.clamp_to_safe_zone(tx, ty)
                        tx, ty = combat_judge.apply_jitter(tx, ty)
                        action_args["x"] = int(tx)
                        action_args["y"] = int(ty)

                    # 9. 执行
                    exec_result = await session.call_tool("game_action", action_args)

                    # 10. BOSS 行为观察收集（v0.3 累积坐标样本，归纳习性）
                    if combat_eval.get("has_highest_boss") or any(
                        e.get("category") == "boss" for e in pred_data
                    ):
                        px, py = player.get("x", 0), player.get("y", 0)
                        for e in pred_data:
                            if e.get("category") not in ("boss", "highest_boss"):
                                continue
                            uid = f"{e.get('raw_id','?')}({e.get('rarity','?')})"
                            obs = (f"{datetime.now().strftime('%H:%M:%S')} "
                                   f"{uid} 位置({e.get('x_now')},{e.get('y_now')}) "
                                   f"预判({e.get('x_predict')},{e.get('y_predict')}) "
                                   f"决策={combat_eval.get('decision')}")
                            boss_observations.append(obs)
                            # 累积坐标样本（用于行为归纳），限制数量防内存膨胀
                            samples = boss_samples.setdefault(uid, [])
                            if len(samples) >= BOSS_SAMPLE_MAX:
                                samples.pop(0)
                            samples.append((e.get("x_now", 0), e.get("y_now", 0),
                                            px, py))

                    now = time.time()
                    if now - last_boss_memory_time > BOSS_MEMORY_INTERVAL:
                        await write_boss_memory(session, boss_observations, boss_samples)
                        boss_observations = []
                        last_boss_memory_time = now

                    # 偶发 100~300ms 停顿，模拟人类反应（v0.3）
                    if random.random() < 0.05:
                        await asyncio.sleep(random.uniform(0.1, 0.3))

                    # 日志
                    log(f"[回合 {round_count}] HP={player.get('hp')} "
                        f"敌人={len(pred_data) if isinstance(pred_data, list) else 0} "
                        f"队友={len(teammates)} "
                        f"决策={combat_eval.get('decision')} "
                        f"套装={current_set} "
                        f"心态={combat_eval.get('mindset')} "
                        f"→ {action_type}")

                    await asyncio.sleep(interval)

            except KeyboardInterrupt:
                log("\n[Agent] 收到中断信号")
            finally:
                # 退出前写剩余 BOSS 记忆
                if boss_observations:
                    await write_boss_memory(session, boss_observations, boss_samples)
                await review_round(session, True, "Agent 正常退出", game_state)

    log("[Agent] 已断开 MCP 连接")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 主程序")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="决策循环间隔秒数，默认 0.5")
    parser.add_argument("--max-rounds", type=int, default=0,
                        help="最大运行回合数，0=无限")
    args = parser.parse_args()

    if not os.path.exists(MCP_SERVER_SCRIPT):
        print(f"错误: 找不到 MCP 服务端 {MCP_SERVER_SCRIPT}")
        sys.exit(1)

    asyncio.run(run_agent(interval=args.interval, max_rounds=args.max_rounds))


if __name__ == "__main__":
    main()
