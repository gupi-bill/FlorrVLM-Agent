#!/usr/bin/env python3
"""
FlorrVLM-Agent 预判模块 predictor.py
=====================================
纯内存运算，不写任何磁盘文件。

功能：
- 同时预判 BOSS + 精英 + 全部普通小怪的未来 1.2 秒位置
- 输出 0~1 置信度，帧数少/移动过快置信度降低
- 实体消失后保留 0.4 秒历史，抵抗 YOLO 漏检抖动
- 非法/越界/负数坐标直接丢弃，不参与预判
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

# 稀有度 -> 分类
RARITY_HIGHEST_BOSS = {"Unique", "Eternal"}
RARITY_BOSS = {"Super"}
RARITY_ELITE = {"Ultra", "Mythic", "Legendary", "Epic"}
RARITY_NORMAL = {"Rare", "Unusual", "Common"}

# 分类 -> 威胁分数（用于排序）
CATEGORY_THREAT = {
    "highest_boss": 1000,
    "boss": 400,
    "elite": 120,
    "normal": 15,
    "unknown": 5,
}


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
    用 raw_id 作为唯一标识；raw_id 相同时按出现顺序区分。
    """

    def __init__(self, raw_id: str, rarity: str):
        self.raw_id = raw_id
        self.rarity = rarity
        self.category = classify_by_rarity(rarity)
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

        return {
            "raw_id": self.raw_id,
            "rarity": self.rarity,
            "category": self.category,
            "threat_score": CATEGORY_THREAT.get(self.category, 5),
            "x_now": round(latest["x"], 1),
            "y_now": round(latest["y"], 1),
            "x_predict": round(pred_x, 1),
            "y_predict": round(pred_y, 1),
            "vx_per_sec": round(vx, 2),
            "vy_per_sec": round(vy, 2),
            "confidence": confidence,
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
    entity_list 格式：
      [{"raw_id":"wasp","rarity":"Super","x":520,"y":330}, ...]
    """
    seen_uids = set()

    for ent in entity_list:
        raw_id = ent.get("raw_id", "unknown")
        rarity = ent.get("rarity", "Common")
        x = ent.get("x")
        y = ent.get("y")

        # 过滤非法坐标
        if not _is_valid_coord(x, y):
            continue

        # 查找或创建追踪器
        uid = None
        for existing_uid, tracker in _trackers.items():
            if tracker.raw_id == raw_id and existing_uid not in seen_uids:
                uid = existing_uid
                break
        if uid is None:
            uid = _make_uid(raw_id)
            _trackers[uid] = EntityTracker(raw_id, rarity)

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
                    "threat_score": CATEGORY_THREAT.get(tracker.category, 5),
                    "x_now": round(latest["x"], 1),
                    "y_now": round(latest["y"], 1),
                    "x_predict": None,
                    "y_predict": None,
                    "vx_per_sec": 0,
                    "vy_per_sec": 0,
                    "confidence": 0.0,
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
    }
