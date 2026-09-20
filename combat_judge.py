#!/usr/bin/env python3
"""
Universal-Game-Framework 战斗评估模块 combat_judge.py
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
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import config

# ---------------------------------------------------------------------------
# 常量（v0.5：全部来自 config.yaml，改参数不用改源码）
# 热加载：agent_main 检测到 config.yaml 变化后调用 reload_config()
# ---------------------------------------------------------------------------
def reload_config():
    """从 config.yaml 重新读取全部常量（热加载入口）。"""
    global JITTER_BASE, JITTER_MAX, CHASE_MAX_DISTANCE, CHASE_MIN_CATEGORY
    global EVAL_DEBOUNCE_INTERVAL, CATEGORY_THREAT, RETREAT_RATIO
    global SAFE_ZONE_MARGIN, SAFE_ZONE_W, SAFE_ZONE_H
    global FLEE_DISTANCE, STRAFE_DISTANCE

    JITTER_BASE = config.get("combat.jitter_base", 8)
    JITTER_MAX = config.get("combat.jitter_max", 15)
    CHASE_MAX_DISTANCE = config.get("combat.chase_max_distance", 400)
    CHASE_MIN_CATEGORY = config.get("combat.chase_min_category", "elite")
    EVAL_DEBOUNCE_INTERVAL = config.get("combat.eval_debounce_interval", 0.7)
    RETREAT_RATIO = config.get("combat.retreat_ratio", 1.0)  # v1.0 自动调参
    SAFE_ZONE_MARGIN = config.get("combat.safe_zone_margin", 100)
    SAFE_ZONE_W = config.get("combat.safe_zone_w", 1920)
    SAFE_ZONE_H = config.get("combat.safe_zone_h", 1080)
    # v2.0：避险走位的两段距离原先硬编码在 calc_retreat_position 里，
    # 与 config.yaml 脱节，提到配置层（缺省值与原硬编码一致，行为不漂移）。
    FLEE_DISTANCE = config.get("combat.flee_distance", 300)
    STRAFE_DISTANCE = config.get("combat.strafe_distance", 150)

    CATEGORY_THREAT = dict(config.get("predictor.threat", {
        "highest_boss": 1000, "boss": 400, "elite": 120, "normal": 15,
        "player_enemy": 150, "player_ally": 0, "unknown": 5,
    }))


reload_config()  # 首次加载

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

# 心态模式
MINDSET_CONSERVATIVE = "conservative"   # 保守：血量偏低就跑
MINDSET_BALANCED = "balanced"           # 均衡：中等血量可冒险
MINDSET_AGGRESSIVE = "aggressive"       # 激进：低血也搏输出

# 分类档位（v2.0）：供 chase_min_category 做「至少多高的档次才追」比较。
# 原先 should_chase 把 boss/elite 写死在代码里，combat.chase_min_category
# 这个配置项是死的，改配置不生效。
CATEGORY_RANK = {
    "unknown": 0,
    "player_ally": 0,
    "normal": 1,
    "player_enemy": 1,
    "elite": 2,
    "boss": 3,
    "highest_boss": 4,
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
def _safe_float(value, default: float = 0.0) -> float:
    """
    把可能是 None / 字符串 / NaN / Inf 的输入安全转成有限 float。

    v2.0：上游（感知层 JSON、LLM 回填）脏数据会直接让 `None <= 0` 抛
    TypeError 或让 NaN 污染整条决策链，这里统一收敛到 default。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def calc_enemy_threat(enemies: list) -> float:
    """计算周围敌人总威胁分数。"""
    total = 0.0
    for e in enemies:
        cat = e.get("category", "unknown") if isinstance(e, dict) else "unknown"
        total += _safe_float(CATEGORY_THREAT.get(cat, 5), 5.0)
    return total


def calc_threat_ratio(player_power: float, enemy_threat: float) -> float:
    """敌方威胁 / 自身实力，比值越大越危险。"""
    power = _safe_float(player_power, 0.0)
    if power <= 0:
        return 999.0
    return enemy_threat / power


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
    top_cat = top_enemy.get("category", "normal") if isinstance(top_enemy, dict) else "normal"
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

    has_highest = any(
        (e.get("category") == "highest_boss" if isinstance(e, dict) else False)
        for e in context.enemies
    )
    hp = _safe_float(context.player.hp, 0.0)
    max_hp = _safe_float(context.player.max_hp, 0.0)
    hp_ratio = hp / max(max_hp, 1.0)

    decision = DECISION_FIGHT
    recommended_set = SET_COMBAT
    retreat_reason = ""

    # ---- highest_boss 动态避险 ----
    if has_highest:
        if ratio > RETREAT_RATIO:
            # 实力不足，全力避险
            decision = DECISION_RETREAT
            recommended_set = SET_RETREAT
            retreat_reason = "highest_boss 出现且实力不足，全力避险"
        elif ratio > RETREAT_RATIO * 0.6:
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
    elif ratio >= RETREAT_RATIO * 1.4:
        decision = DECISION_RETREAT
        recommended_set = SET_RETREAT
        power_show = _safe_float(context.player.power_score, 0.0)
        retreat_reason = f"敌方威胁({enemy_threat:.0f})远超自身实力({power_show:.0f})"
    elif ratio >= RETREAT_RATIO * 0.8:
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
    # v2.0：原实现无条件覆盖 recommended_set，导致「已经在跑路了却被队友
    # 的套装配置改成辅助套」，逃生决策被静默吞掉。逃生优先级高于协同。
    if context.teammates and decision != DECISION_RETREAT:
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


def _team_set_adjust(teammates: list, current_rec: str,
                     decision: str = None) -> str:
    """
    组队套装协同：
    - 队友输出套多 → 我方推荐辅助套
    - 队友抗伤套多 → 我方推荐输出套

    decision 为逃生(DECISION_RETREAT)时直接返回原推荐，不再参与协同
    （v2.0：逃生是最高优先级，协同不能把它改掉）。decision=None 保持旧行为。
    """
    if not teammates:
        return current_rec
    if decision == DECISION_RETREAT:
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

    def __init__(self, debounce_interval: float = None):
        # v2.0：默认参数在 import 时就被绑定，config 热加载后新建的评估器
        # 仍拿旧间隔。改为 None → 运行时再取当前配置值。
        self.interval = (EVAL_DEBOUNCE_INTERVAL
                         if debounce_interval is None else debounce_interval)
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
def should_chase(entity: dict, player: PlayerState = None,
                 chased_distance: float = 0) -> bool:
    """
    判断是否追杀跑出屏幕的怪物。
    - 至少 elite 级别才追杀
    - 追杀距离不超过 CHASE_MAX_DISTANCE
    - highest_boss 不主动追杀（避险优先）
    """
    cat = entity.get("category", "normal") if isinstance(entity, dict) else "normal"
    # highest_boss 一律不主动追（避险优先），与档位配置无关
    if cat == "highest_boss":
        return False

    # v2.0：按 combat.chase_min_category 动态取最低可追档位，配置真正生效
    min_cat = CHASE_MIN_CATEGORY if isinstance(CHASE_MIN_CATEGORY, str) else "elite"
    min_rank = CATEGORY_RANK.get(min_cat, CATEGORY_RANK["elite"])
    if CATEGORY_RANK.get(cat, 0) < min_rank:
        return False

    if _safe_float(chased_distance, 0.0) >= _safe_float(CHASE_MAX_DISTANCE, 400.0):
        return False
    return True


# ---------------------------------------------------------------------------
# 安全区钳制（v0.3；边距/尺寸由 config.yaml 提供）
# ---------------------------------------------------------------------------
def clamp_to_safe_zone(x: float, y: float,
                       screen_w: int = None,
                       screen_h: int = None,
                       margin: int = None) -> tuple:
    """
    把走位目标点限制在安全区内，防止无脑贴墙/贴四角卡死。
    距离屏幕边缘小于 margin 的坐标会被拉回安全区。
    默认取 config.yaml 里的 combat.safe_zone_*。

    v2.0：当屏幕比安全区还小（screen - 2*margin < 0）时，原来的
    max(margin, min(screen-margin, x)) 会退化成恒返回 margin —— 而这个
    margin 可能已经在屏幕外（例如 800x600 配 100 边距不会出问题，但
    200x150 配 100 边距就会把点钉死在 (100,100) 这条越界线上）。
    此时退化为钉在屏幕中心，保证结果始终落在屏幕内。
    """
    screen_w = _safe_float(screen_w if screen_w is not None else SAFE_ZONE_W, 1920.0)
    screen_h = _safe_float(screen_h if screen_h is not None else SAFE_ZONE_H, 1080.0)
    margin = _safe_float(margin if margin is not None else SAFE_ZONE_MARGIN, 100.0)
    x = _safe_float(x, screen_w / 2.0)
    y = _safe_float(y, screen_h / 2.0)

    def _axis(v: float, size: float) -> float:
        lo, hi = margin, size - margin
        if hi < lo:          # 安全区退化 → 钉中心
            return size / 2.0
        return max(lo, min(hi, v))

    return round(_axis(x, screen_w), 1), round(_axis(y, screen_h), 1)


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
    px = _safe_float(context.player.x, 0.0)
    py = _safe_float(context.player.y, 0.0)
    te = threat_entity if isinstance(threat_entity, dict) else {}
    ex = _safe_float(te.get("x_now", px), px)
    ey = _safe_float(te.get("y_now", py), py)

    ratio = calc_threat_ratio(context.player.power_score,
                              calc_enemy_threat(context.enemies))

    # 远离方向
    dx = px - ex
    dy = py - ey
    dist = (dx ** 2 + dy ** 2) ** 0.5
    if dist < 1:
        dx, dy = 1, 0
        dist = 1

    # v2.0：边距 / 距离改为读配置（原硬编码 100 / 300 / 150 与 safe_zone_margin 脱节）
    margin = _safe_float(SAFE_ZONE_MARGIN, 100.0)
    screen_w = _safe_float(context.screen_width, SAFE_ZONE_W)
    screen_h = _safe_float(context.screen_height, SAFE_ZONE_H)

    def _limit(v: float, size: float) -> float:
        lo, hi = margin, size - margin
        if hi < lo:
            return size / 2.0
        return max(lo, min(hi, v))

    if ratio > 1.0:
        # 全力逃跑：往远离方向走 FLEE_DISTANCE 像素，不贴边缘
        flee_dist = _safe_float(FLEE_DISTANCE, 300.0)
        tx = px + (dx / dist) * flee_dist
        ty = py + (dy / dist) * flee_dist
        # 限制在屏幕内，不触发角落暂停
        tx = _limit(tx, screen_w)
        ty = _limit(ty, screen_h)
        return {"x": round(tx, 1), "y": round(ty, 1), "strategy": "flee"}
    else:
        # 实力可周旋：侧向移动，保持距离
        strafe_dist = _safe_float(STRAFE_DISTANCE, 150.0)
        # 垂直于威胁方向
        tx = px + (-dy / dist) * strafe_dist
        ty = py + (dx / dist) * strafe_dist
        tx = _limit(tx, screen_w)
        ty = _limit(ty, screen_h)
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
