#!/usr/bin/env python3
"""
FlorrVLM-Agent 战斗评估模块 combat_judge.py
=============================================
纯逻辑运算，不写磁盘，不调用外部 API。

功能：
- 自身实力评分 vs 敌方总威胁，判断 fight / cautious_fight / retreat
- 套装推荐（只输出名称，实际切换由外部工具完成）
- 组队协同：队友输出套 → 我方辅助；队友抗伤套 → 我方输出
- 有限追杀：高等级怪物出屏追一段就回撤
- 移动抖动：固定小范围随机偏移，模拟真人手操
- 动态心态：面对不同怪物 + 自身实力，自动切换保守/均衡/激进
- highest_boss 动态避险：实力强可周旋，实力弱全力逃跑
- 实力评估防抖（v0.2）：CombatEvaluator 每 0.7s 才重算一次，降低 J1900 CPU 压力
"""
import random
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# 决策结果
DECISION_FIGHT = "fight"
DECISION_CAUTIOUS = "cautious_fight"
DECISION_RETREAT = "retreat"

# 套装类型（只推荐名称，由 game_action 的 switch_set 实际切换）
SET_COMBAT = "combat"           # 输出战斗套
SET_TANK = "tank"               # 抗伤套
SET_RETREAT = "retreat"         # 跑路逃生套
SET_CHASE = "chase"             # 追击套（v0.3：追杀高价值目标时用）
SET_TEAM_SUPPORT = "team"       # 组队辅助套

# 追击判定：至少精英级才追杀（复用下方有限追杀常量）
CHASE_MIN_CATEGORY = "elite"

# 心态模式
MINDSET_CONSERVATIVE = "conservative"   # 保守：血量偏低就跑
MINDSET_BALANCED = "balanced"           # 均衡：中等血量可冒险
MINDSET_AGGRESSIVE = "aggressive"       # 激进：低血也搏输出

# 移动抖动参数（固定小范围，模拟真人）
JITTER_BASE = 8              # 基础抖动像素
JITTER_MAX = 15              # 最大抖动像素

# 有限追杀参数
CHASE_MAX_DISTANCE = 400     # 最多追杀距离（像素）
CHASE_MIN_CATEGORY = "elite"  # 至少精英级才追杀

# 评估防抖间隔（秒）
EVAL_DEBOUNCE_INTERVAL = 0.7  # v0.2：实力评估每 0.7s 一次

# 威胁分数（与 predictor 保持一致）
CATEGORY_THREAT = {
    "highest_boss": 1000,
    "boss": 400,
    "elite": 120,
    "normal": 15,
    "unknown": 5,
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class PlayerState:
    """玩家自身状态。"""
    hp: float = 100.0
    max_hp: float = 100.0
    power_score: float = 100.0      # 自身综合实力评分
    current_set: str = SET_COMBAT   # 当前花瓣套装
    talent: str = "none"            # 当前天赋
    x: float = 0.0
    y: float = 0.0


@dataclass
class Teammate:
    """队友信息。"""
    raw_id: str = ""
    petal_set: str = SET_COMBAT     # 队友花瓣套装
    x: float = 0.0
    y: float = 0.0


@dataclass
class CombatContext:
    """战斗上下文，传入评估函数。"""
    player: PlayerState = field(default_factory=PlayerState)
    enemies: list = field(default_factory=list)       # predictor 输出的实体列表
    teammates: list = field(default_factory=list)     # Teammate 列表
    screen_width: int = 1920
    screen_height: int = 1080


# ---------------------------------------------------------------------------
# 核心评估
# ---------------------------------------------------------------------------
def calc_enemy_threat(enemies: list) -> float:
    """计算周围敌人总威胁分数。"""
    total = 0.0
    for e in enemies:
        cat = e.get("category", "unknown")
        total += CATEGORY_THREAT.get(cat, 5)
    return total


def calc_threat_ratio(player_power: float, enemy_threat: float) -> float:
    """敌方威胁 / 自身实力，比值越大越危险。"""
    if player_power <= 0:
        return 999.0
    return enemy_threat / player_power


def decide_mindset(context: CombatContext) -> str:
    """
    动态心态：根据面对的最高威胁敌人 + 自身实力决定。
    - 面对 highest_boss 且实力不足 → 保守
    - 面对 normal 且实力充足 → 激进
    - 其他 → 均衡
    """
    if not context.enemies:
        return MINDSET_BALANCED

    top_enemy = context.enemies[0]  # 已按威胁排序
    top_cat = top_enemy.get("category", "normal")
    ratio = calc_threat_ratio(context.player.power_score,
                              calc_enemy_threat(context.enemies))

    if top_cat == "highest_boss":
        if ratio > 1.2:
            return MINDSET_CONSERVATIVE
        return MINDSET_BALANCED
    if top_cat == "boss":
        if ratio > 1.5:
            return MINDSET_CONSERVATIVE
        if ratio < 0.5:
            return MINDSET_AGGRESSIVE
        return MINDSET_BALANCED
    if top_cat == "elite":
        if ratio < 0.4:
            return MINDSET_AGGRESSIVE
        return MINDSET_BALANCED
    # normal
    if ratio < 0.3:
        return MINDSET_AGGRESSIVE
    return MINDSET_BALANCED


def judge_combat(context: CombatContext) -> dict:
    """
    综合评估，返回决策结果。
    返回：
    {
      "decision": "fight" / "cautious_fight" / "retreat",
      "recommended_set": "combat" / "tank" / "retreat" / "team",
      "mindset": "conservative" / "balanced" / "aggressive",
      "enemy_threat": float,
      "threat_ratio": float,
      "has_highest_boss": bool,
      "retreat_reason": str,
    }
    """
    enemy_threat = calc_enemy_threat(context.enemies)
    ratio = calc_threat_ratio(context.player.power_score, enemy_threat)
    mindset = decide_mindset(context)

    has_highest = any(e.get("category") == "highest_boss" for e in context.enemies)
    hp_ratio = context.player.hp / max(context.player.max_hp, 1)

    decision = DECISION_FIGHT
    recommended_set = SET_COMBAT
    retreat_reason = ""

    # ---- highest_boss 动态避险 ----
    if has_highest:
        if ratio > 1.0:
            # 实力不足，全力避险
            decision = DECISION_RETREAT
            recommended_set = SET_RETREAT
            retreat_reason = "highest_boss 出现且实力不足，全力避险"
        elif ratio > 0.6:
            # 实力接近，谨慎周旋
            decision = DECISION_CAUTIOUS
            recommended_set = SET_TANK
            retreat_reason = "highest_boss 出现，实力接近，谨慎周旋"
        else:
            # 实力充足，可以对抗
            decision = DECISION_CAUTIOUS
            recommended_set = SET_TANK
            retreat_reason = "highest_boss 出现但实力充足，可对抗"

    # ---- 普通威胁评估 ----
    elif ratio >= 1.4:
        decision = DECISION_RETREAT
        recommended_set = SET_RETREAT
        retreat_reason = f"敌方威胁({enemy_threat:.0f})远超自身实力({context.player.power_score:.0f})"
    elif ratio >= 0.8:
        decision = DECISION_CAUTIOUS
        recommended_set = SET_TANK
    else:
        decision = DECISION_FIGHT
        # v0.3：实力充足且场上有精英/BOSS 值得追 → 追击套
        chaseable = [e for e in context.enemies
                     if e.get("category") in ("boss", "elite")]
        recommended_set = SET_CHASE if chaseable else SET_COMBAT

    # ---- 心态修正 ----
    if mindset == MINDSET_CONSERVATIVE and hp_ratio < 0.5:
        if decision == DECISION_FIGHT:
            decision = DECISION_CAUTIOUS
            recommended_set = SET_TANK
    if mindset == MINDSET_AGGRESSIVE and hp_ratio > 0.3:
        if decision == DECISION_CAUTIOUS:
            decision = DECISION_FIGHT
            recommended_set = SET_COMBAT

    # ---- 组队协同修正 ----
    if context.teammates:
        recommended_set = _team_set_adjust(context.teammates, recommended_set)

    return {
        "decision": decision,
        "recommended_set": recommended_set,
        "mindset": mindset,
        "enemy_threat": round(enemy_threat, 1),
        "threat_ratio": round(ratio, 3),
        "has_highest_boss": has_highest,
        "retreat_reason": retreat_reason,
    }


def _team_set_adjust(teammates: list, current_rec: str) -> str:
    """
    组队套装协同：
    - 队友输出套多 → 我方推荐辅助套
    - 队友抗伤套多 → 我方推荐输出套
    """
    if not teammates:
        return current_rec

    output_count = sum(1 for t in teammates if t.petal_set == SET_COMBAT)
    tank_count = sum(1 for t in teammates if t.petal_set == SET_TANK)

    if output_count > tank_count:
        return SET_TEAM_SUPPORT
    if tank_count > output_count:
        return SET_COMBAT
    return current_rec


# ---------------------------------------------------------------------------
# 实力评估防抖（v0.2）
# ---------------------------------------------------------------------------
class CombatEvaluator:
    """
    带防抖缓存的战斗评估器。
    默认 0.7 秒内重复评估直接返回上次结果，不重算，降低 J1900 CPU 压力。
    """

    def __init__(self, debounce_interval: float = EVAL_DEBOUNCE_INTERVAL):
        self.interval = debounce_interval
        self._last_time = 0.0
        self._cache = None

    def evaluate(self, context: CombatContext) -> dict:
        """返回评估结果，0.7 秒内命中缓存。"""
        now = time.time()
        if self._cache is not None and (now - self._last_time) < self.interval:
            return self._cache
        self._cache = judge_combat(context)
        self._last_time = now
        return self._cache

    def invalidate(self):
        """对局结束 / 状态大变化时调用，强制下一次重算。"""
        self._cache = None


# ---------------------------------------------------------------------------
# 有限追杀
# ---------------------------------------------------------------------------
def should_chase(entity: dict, player: PlayerState,
                 chased_distance: float = 0) -> bool:
    """
    判断是否追杀跑出屏幕的怪物。
    - 至少 elite 级别才追杀
    - 追杀距离不超过 CHASE_MAX_DISTANCE
    - highest_boss 不主动追杀（避险优先）
    """
    cat = entity.get("category", "normal")
    if cat == "highest_boss":
        return False
    if cat not in ("boss", "elite"):
        return False
    if chased_distance >= CHASE_MAX_DISTANCE:
        return False
    return True


# ---------------------------------------------------------------------------
# 安全区钳制（v0.3）
# ---------------------------------------------------------------------------
SAFE_ZONE_MARGIN = 100   # 距离屏幕边缘 100 像素内视为安全区外（避开四角暂停区）
SAFE_ZONE_W = 1920
SAFE_ZONE_H = 1080


def clamp_to_safe_zone(x: float, y: float,
                       screen_w: int = SAFE_ZONE_W,
                       screen_h: int = SAFE_ZONE_H,
                       margin: int = SAFE_ZONE_MARGIN) -> tuple:
    """
    把走位目标点限制在安全区内，防止无脑贴墙/贴四角卡死。
    距离屏幕边缘小于 margin 的坐标会被拉回安全区。
    """
    x = max(margin, min(screen_w - margin, float(x)))
    y = max(margin, min(screen_h - margin, float(y)))
    return round(x, 1), round(y, 1)


# ---------------------------------------------------------------------------
# 移动抖动（模拟真人）
# ---------------------------------------------------------------------------
def apply_jitter(x: float, y: float) -> tuple:
    """
    给目标坐标加固定小范围随机抖动，消除机器完美直线感。
    抖动幅度全程统一，不随血量变化。
    """
    jx = random.uniform(-JITTER_BASE, JITTER_BASE)
    jy = random.uniform(-JITTER_BASE, JITTER_BASE)
    # 偶尔来一次稍大的抖动，更像人手
    if random.random() < 0.15:
        jx = random.uniform(-JITTER_MAX, JITTER_MAX)
        jy = random.uniform(-JITTER_MAX, JITTER_MAX)
    return round(x + jx, 1), round(y + jy, 1)


# ---------------------------------------------------------------------------
# 避险走位（highest_boss）
# ---------------------------------------------------------------------------
def calc_retreat_position(context: CombatContext,
                          threat_entity: dict) -> dict:
    """
    计算避险目标位置。
    - 实力弱：往远离威胁的方向跑，不贴屏幕边缘
    - 实力强：往侧面周旋，保持距离
    返回 {"x": target_x, "y": target_y, "strategy": "flee" / "strafe"}
    """
    px, py = context.player.x, context.player.y
    ex = threat_entity.get("x_now", px)
    ey = threat_entity.get("y_now", py)

    ratio = calc_threat_ratio(context.player.power_score,
                              calc_enemy_threat(context.enemies))

    # 远离方向
    dx = px - ex
    dy = py - ey
    dist = (dx ** 2 + dy ** 2) ** 0.5
    if dist < 1:
        dx, dy = 1, 0
        dist = 1

    if ratio > 1.0:
        # 全力逃跑：往远离方向走 300 像素，不贴边缘
        flee_dist = 300
        tx = px + (dx / dist) * flee_dist
        ty = py + (dy / dist) * flee_dist
        # 限制在屏幕内，不触发角落暂停
        margin = 100
        tx = max(margin, min(context.screen_width - margin, tx))
        ty = max(margin, min(context.screen_height - margin, ty))
        return {"x": round(tx, 1), "y": round(ty, 1), "strategy": "flee"}
    else:
        # 实力可周旋：侧向移动，保持距离
        strafe_dist = 150
        # 垂直于威胁方向
        tx = px + (-dy / dist) * strafe_dist
        ty = py + (dx / dist) * strafe_dist
        margin = 100
        tx = max(margin, min(context.screen_width - margin, tx))
        ty = max(margin, min(context.screen_height - margin, ty))
        return {"x": round(tx, 1), "y": round(ty, 1), "strategy": "strafe"}


# ---------------------------------------------------------------------------
# 成就（仅内存，不持久化）
# ---------------------------------------------------------------------------
_achievements = set()


def unlock_achievement(name: str):
    """解锁成就，仅内存记录，程序退出清空。"""
    _achievements.add(name)


def get_achievements() -> list:
    return sorted(_achievements)


def clear_achievements():
    _achievements.clear()
