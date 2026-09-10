#!/usr/bin/env python3
"""
FlorrVLM-Agent 预判模块 predictor.py
=====================================
纯内存运算，不写任何磁盘文件。

功能：
- 同时预判 BOSS + 精英 + 全部普通小怪的未来 1.2 秒位置
- 输出 0~1 置信度，帧数少/移动过快置信度降低
- 置信度阈值锁：低于 CONFIDENCE_THRESHOLD 时标记 prediction_trusted=False
  并置空预判坐标，下游不再采信，只参考当前画面真实位置
- 实体消失后保留 0.4 秒历史，抵抗 YOLO 漏检抖动
- 非法/越界/负数坐标直接丢弃，不参与预判
- 同屏多怪最近距离匹配（v0.2 修复：防止同名怪跟踪错乱、优先级排序混乱）
- 输出时按威胁等级排序，只返回最高前 8 个实体，节省 Token

稀有度体系（Florr.io 原生）：
  Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal
分类：
  highest_boss : Unique, Eternal  （最高威胁，紧急避险）
  boss         : Super             （普通 BOSS）
  elite        : Ultra, Mythic, Legendary, Epic
  normal       : Rare, Unusual, Common
"""
import time
from collections import deque
from typing import Optional

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
PREDICT_SECONDS = 1.2       # 预判未来 1.2 秒
MIN_FRAMES = 3              # 至少 3 帧才算速度
ENTITY_TIMEOUT = 0.4        # 实体消失后保留 0.4 秒历史
MAX_OUTPUT_ENTITIES = 8     # 最多输出前 8 个威胁最高实体
HISTORY_MAXLEN = 10         # 每实体最多保留 10 帧
CONFIDENCE_THRESHOLD = 0.65 # 置信度阈值锁：低于此值不采信预判

# 稀有度 -> 分类
RARITY_HIGHEST_BOSS = {"Unique", "Eternal"}
RARITY_BOSS = {"Super"}
RARITY_ELITE = {"Ultra", "Mythic", "Legendary", "Epic"}
RARITY_NORMAL = {"Rare", "Unusual", "Common"}

# 分类 -> 威胁分数（用于排序；可按游戏替换）
CATEGORY_THREAT = {
    "highest_boss": 1000,
    "boss": 400,
    "elite": 120,
    "normal": 15,
    "player_enemy": 150,   # 玩家敌对：威胁较高、难预判
    "player_ally": 0,      # 队友：不作威胁
    "unknown": 5,
}

# v0.4 玩家实体识别标记（数据驱动，换游戏时改这份即可）：
PLAYER_ENEMY_MARKERS = ("player_enemy", "enemy_player", "hostile", "enemy")
PLAYER_ALLY_MARKERS = ("player_ally", "ally", "teammate", "friend", "party")


def detect_role(raw_id: str, explicit: Optional[str] = None) -> str:
    """
    判断实体角色：monster / player_enemy / player_ally。
    优先信任感知层给的 explicit role，否则按 raw_id 里的标识词匹配。
    匹配标记在 PLAYER_*_MARKERS 常量里集中配置，避免散落硬编码。
    """
    if explicit in ("player_enemy", "player_ally", "monster"):
        return explicit
    rid = (raw_id or "").lower()
    if any(m in rid for m in PLAYER_ENEMY_MARKERS):
        return "player_enemy"
    if any(m in rid for m in PLAYER_ALLY_MARKERS):
        return "player_ally"
    return "monster"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def classify_by_rarity(rarity: str) -> str:
    """根据游戏原生稀有度返回实体类别。"""
    if not rarity:
        return "unknown"
    r = rarity.strip().capitalize()
    if r in RARITY_HIGHEST_BOSS:
        return "highest_boss"
    if r in RARITY_BOSS:
        return "boss"
    if r in RARITY_ELITE:
        return "elite"
    if r in RARITY_NORMAL:
        return "normal"
    return "unknown"


def _is_valid_coord(x, y) -> bool:
    """过滤非法坐标：None、负数、非数字。"""
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return False
    if x < 0 or y < 0:
        return False
    if x > 100000 or y > 100000:
        return False
    return True


# ---------------------------------------------------------------------------
# 实体历史追踪
# ---------------------------------------------------------------------------
class EntityTracker:
    """
    追踪单个实体的坐标历史。
    用 raw_id 作为唯一标识；raw_id 相同时按距离匹配区分多只。
    """

    def __init__(self, raw_id: str, rarity: str, role: str = "monster"):
        self.raw_id = raw_id
        self.rarity = rarity
        self.role = role
        # 玩家按角色分类，怪物按稀有度分类
        self.category = role if role != "monster" else classify_by_rarity(rarity)
        self.history = deque(maxlen=HISTORY_MAXLEN)
        self.last_seen = time.time()

    def update(self, x: float, y: float):
        """更新一帧坐标。"""
        self.history.append({
            "timestamp": time.time(),
            "x": float(x),
            "y": float(y),
        })
        self.last_seen = time.time()

    def is_expired(self) -> bool:
        """超过 ENTITY_TIMEOUT 没更新，视为消失。"""
        return (time.time() - self.last_seen) > ENTITY_TIMEOUT

    def predict(self) -> Optional[dict]:
        """
        计算该实体的预判位置和置信度。
        返回 None 表示帧数不足或无法计算。
        置信度低于 CONFIDENCE_THRESHOLD 时置空预判坐标并标记不可信。
        """
        if len(self.history) < MIN_FRAMES:
            return None

        oldest = self.history[0]
        latest = self.history[-1]
        delta_t = latest["timestamp"] - oldest["timestamp"]
        if delta_t <= 0:
            return None

        vx = (latest["x"] - oldest["x"]) / delta_t
        vy = (latest["y"] - oldest["y"]) / delta_t

        pred_x = latest["x"] + vx * PREDICT_SECONDS
        pred_y = latest["y"] + vy * PREDICT_SECONDS

        # 置信度：帧数越多越高；速度越快（瞬移）越低
        frame_conf = min(1.0, len(self.history) / 8.0)
        speed = (vx ** 2 + vy ** 2) ** 0.5
        speed_penalty = max(0.3, 1.0 - speed / 2000.0)
        confidence = round(frame_conf * speed_penalty, 3)

        # 置信度阈值锁：低于阈值不采信预判，置空坐标
        trusted = confidence >= CONFIDENCE_THRESHOLD
        out_x = round(pred_x, 1) if trusted else None
        out_y = round(pred_y, 1) if trusted else None

        return {
            "raw_id": self.raw_id,
            "rarity": self.rarity,
            "category": self.category,
            "role": self.role,
            "threat_score": CATEGORY_THREAT.get(self.category, 5),
            "x_now": round(latest["x"], 1),
            "y_now": round(latest["y"], 1),
            "x_predict": out_x,
            "y_predict": out_y,
            "vx_per_sec": round(vx, 2),
            "vy_per_sec": round(vy, 2),
            "confidence": confidence,
            "prediction_trusted": trusted,
        }


# ---------------------------------------------------------------------------
# 全局预判管理器
# ---------------------------------------------------------------------------
_trackers = {}  # {entity_uid: EntityTracker}
_uid_counter = 0


def _make_uid(raw_id: str) -> str:
    """为同 raw_id 的多个实体生成唯一 ID。"""
    global _uid_counter
    _uid_counter += 1
    return f"{raw_id}_{_uid_counter}"


def update_frame_entities(entity_list: list):
    """
    每帧调用，传入 perception 输出的 entities 数组。
    自动过滤非法坐标，更新追踪器。
    同屏多个同名怪时，用上一帧坐标最近距离匹配，防止跟踪错乱。
    entity_list 格式：
      [{"raw_id":"wasp","rarity":"Super","x":520,"y":330}, ...]
    """
    seen_uids = set()

    for ent in entity_list:
        raw_id = ent.get("raw_id", "unknown")
        rarity = ent.get("rarity", "Common")
        x = ent.get("x")
        y = ent.get("y")
        # v0.4 玩家识别：优先用感知层给的 role，否则按 raw_id 匹配
        role = detect_role(raw_id, ent.get("role"))

        # 过滤非法坐标
        if not _is_valid_coord(x, y):
            continue

        # 查找或创建追踪器（v0.2：最近距离匹配，修复多怪同屏优先级错乱）
        uid = None
        candidates = [
            (existing_uid, tracker)
            for existing_uid, tracker in _trackers.items()
            if tracker.raw_id == raw_id and existing_uid not in seen_uids
        ]
        if candidates:
            # 选上一帧坐标距离最近的那个 tracker
            best_uid, best_t = min(
                candidates,
                key=lambda it: ((it[1].history[-1]["x"] - x) ** 2 +
                                (it[1].history[-1]["y"] - y) ** 2)
            )
            uid = best_uid
        else:
            uid = _make_uid(raw_id)
            _trackers[uid] = EntityTracker(raw_id, rarity, role)

        # 更新角色（玩家身份可能变化，逐帧刷新）
        _trackers[uid].role = role
        _trackers[uid].category = role if role != "monster" else _trackers[uid].category
        _trackers[uid].update(x, y)
        seen_uids.add(uid)

    # 清理过期实体
    expired = [uid for uid, t in _trackers.items() if t.is_expired()]
    for uid in expired:
        del _trackers[uid]


def predict_all_entities() -> list:
    """
    返回全部实体的预判结果，按威胁分数降序，只取前 MAX_OUTPUT_ENTITIES 个。
    """
    results = []
    for tracker in _trackers.values():
        pred = tracker.predict()
        if pred is not None:
            results.append(pred)
        else:
            # 帧数不足时也返回当前位置（无预判）
            if tracker.history:
                latest = tracker.history[-1]
                results.append({
                    "raw_id": tracker.raw_id,
                    "rarity": tracker.rarity,
                    "category": tracker.category,
                    "role": tracker.role,
                    "threat_score": CATEGORY_THREAT.get(tracker.category, 5),
                    "x_now": round(latest["x"], 1),
                    "y_now": round(latest["y"], 1),
                    "x_predict": None,
                    "y_predict": None,
                    "vx_per_sec": 0,
                    "vy_per_sec": 0,
                    "confidence": 0.0,
                    "prediction_trusted": False,
                })

    results.sort(key=lambda e: e["threat_score"], reverse=True)
    return results[:MAX_OUTPUT_ENTITIES]


def get_highest_threat() -> Optional[dict]:
    """返回当前威胁最高的实体（用于紧急避险判断）。"""
    all_pred = predict_all_entities()
    return all_pred[0] if all_pred else None


def reset():
    """清空全部追踪器（对局结束/新对局开始时调用）。"""
    global _uid_counter
    _trackers.clear()
    _uid_counter = 0


def get_status() -> dict:
    """调试用：返回当前追踪状态。"""
    return {
        "tracked_entities": len(_trackers),
        "predict_seconds": PREDICT_SECONDS,
        "entity_timeout": ENTITY_TIMEOUT,
        "max_output": MAX_OUTPUT_ENTITIES,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
