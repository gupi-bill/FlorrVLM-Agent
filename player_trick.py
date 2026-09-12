#!/usr/bin/env python3
"""
FlorrVLM-Agent 玩家套路检测 player_trick.py
==============================================
v2.0 —— 识破敌方玩家套路：诱骗 / 假撤退 / 埋伏。

纯本地逻辑（不联网、不调 LLM），喂入每帧的敌方玩家实体流，
用滑动窗口轨迹判断三种常见套路，供决策层/LLM 参考：

  1. fake_retreat(假撤退)：玩家向我冲 → 半路突然折返跑（勾引追击，回头反打）
  2. lure(诱骗)：一个弱玩家在近处晃动勾引，而远处潜伏着高威胁玩家（做饵）
  3. ambush(包围)：两个及以上敌方玩家分居两侧且相互间夹角≈180°（左右夹击）

用法:
  dt = PlayerTrickDetector()
  dt.update(my_x, my_y, enemy_players)   # 每帧调用
  dt.detect()  # 返回 [{"tactic": ..., "detail": ..., "advice": ...}, ...]
"""
import math
import time


# 检测阈值（单位：像素 / 秒 / 角度）
_CLOSE_DIST = 180.0      # "近处"判距
_FAR_DIST = 260.0        # "远处潜伏"判距
_AMBUSH_ANGLE = 140.0    # 两玩家相对我夹角 >= 此值视为包夹
_MIN_FRAMES = 4           # 至少观察几帧才开始判定（防单帧抖动）


class PlayerTrickDetector:
    """维护每个敌方玩家的近期轨迹，输出套路检测。"""

    def __init__(self, max_frames: int = 8):
        self.max_frames = max_frames
        # uid -> deque of dict(x, y, t, dist_to_me)
        self._tracks: dict[str, list] = {}
        self._last_detect: dict = {}

    # -- 数据入口 -----------------------------------------------------
    def update(self, my_x: float, my_y: float, enemy_players: list) -> dict:
        """每帧喂入。enemy_players 为感知/预判输出的玩家实体列表。
        返回本帧检测结果（同 update 调用可反复取，detect() 也可单独调）。"""
        now = time.time()
        # 先按 uid 归组
        for ent in enemy_players:
            uid = ent.get("uid") or ent.get("raw_id") or "p"
            x = ent.get("x_now")
            if x is None:
                x = ent.get("x")
            y = ent.get("y_now")
            if y is None:
                y = ent.get("y")
            if x is None or y is None:
                continue
            dist = math.hypot(x - my_x, y - my_y)
            tr = self._tracks.setdefault(uid, [])
            tr.append({"x": x, "y": y, "t": now, "d": dist,
                       "threat": ent.get("threat_score", 0)})
            if len(tr) > self.max_frames:
                tr.pop(0)
        # 清理很久没更新的玩家
        for uid in [u for u, t in self._tracks.items() if t and now - t[-1]["t"] > 8]:
            self._tracks.pop(uid, None)
        self._last_detect = self.detect(my_x, my_y, enemy_players)
        return self._last_detect

    # -- 检测 ---------------------------------------------------------
    def detect(self, my_x: float = None, my_y: float = None,
               enemy_players: list = None) -> list:
        """组合检测三类套路。可独立调用（用最近轨迹）。
        返回: [{"tactic": str, "detail": str, "advice": str}, ...]"""
        finds = []
        if not self._tracks:
            return finds
        # 需要我方坐标：从最近一条轨迹(任意玩家)反推被忽略，要求显式传入
        if my_x is None or my_y is None:
            return finds

        players = [t for uid, t in self._tracks.items() if t]
        # 各玩家当前坐标
        cur_pos = {uid: (t[-1]["x"], t[-1]["y"]) for uid, t in self._tracks.items() if t}

        # 1) 假撤退：轨迹中出现"先靠近(< _CLOSE_DIST) 后又变远"的折返
        for uid, tr in self._tracks.items():
            if len(tr) < _MIN_FRAMES:
                continue
            min_d = min(p["d"] for p in tr)
            last = tr[-1]
            came_close = min_d < _CLOSE_DIST * 0.9          # 确实贴脸过
            now_far = last["d"] > _CLOSE_DIST and last["d"] > min_d + 60  # 现在又拉开
            if came_close and now_far:
                finds.append({
                    "tactic": "fake_retreat",
                    "detail": f"玩家[{uid}]先靠近到 {min_d:.0f}px 又折返到 {last['d']:.0f}px",
                    "advice": "疑似诱骗追击，勿追，保持距离",
                })

        # 2) 诱骗：近处一个弱的 + 远处有高威胁另一个玩家
        near_weak, far_strong = [], []
        for uid, tr in self._tracks.items():
            if not tr:
                continue
            d = tr[-1]["d"]
            threat = tr[-1].get("threat", 0)
            if d < _CLOSE_DIST and threat < 30:
                near_weak.append((uid, d))
            if d > _FAR_DIST and threat >= 100:
                far_strong.append((uid, d))
        if near_weak and far_strong:
            w, wd = near_weak[0]
            s, sd = far_strong[0]
            finds.append({
                "tactic": "lure",
                "detail": f"弱玩家[{w}]在 {wd:.0f}px 处勾引，高威胁玩家[{s}]潜伏在 {sd:.0f}px 处",
                "advice": "可能是诱饵，先处理远处高威胁再收拾近处",
            })

        # 3) 包围：两个玩家夹击（夹角≈180°）
        uid_list = [u for u, t in self._tracks.items() if t]
        for i in range(len(uid_list)):
            for j in range(i + 1, len(uid_list)):
                a, b = uid_list[i], uid_list[j]
                ax, ay = cur_pos[a]
                bx, by = cur_pos[b]
                ang = _angle_between(my_x, my_y, (ax, ay), (bx, by))
                da = math.hypot(ax - my_x, ay - my_y)
                db = math.hypot(bx - my_x, by - my_y)
                if da < 400 and db < 400 and ang >= _AMBUSH_ANGLE:
                    finds.append({
                        "tactic": "ambush",
                        "detail": f"玩家[{a}] 与玩家[{b}] 对我夹角 {ang:.0f}°（左右夹击）",
                        "advice": "两面受敌，避免被夹到角落，向空旷方向突围",
                    })
                    break  # 一对即可，避免重复
        return finds

    def reset(self):
        self._tracks.clear()


def _angle_between(px, py, pa, pb) -> float:
    """我方在 p，玩家 a、b 相对我方向的夹角(度)。"""
    ax, ay = pa[0] - px, pa[1] - py
    bx, by = pb[0] - px, pb[1] - py
    dot = ax * bx + ay * by
    na = math.hypot(ax, ay) or 1.0
    nb = math.hypot(bx, by) or 1.0
    cos = max(-1.0, min(1.0, dot / (na * nb)))
    return math.degrees(math.acos(cos))


# ---------------------------------------------------------------------------
# 便捷单例（供 agent_main / MCP 共用）
# ---------------------------------------------------------------------------
_default = None


def get_detector() -> "PlayerTrickDetector":
    global _default
    if _default is None:
        _default = PlayerTrickDetector()
    return _default


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="玩家套路检测自测")
    ap.add_argument("--demo", action="store_true", help="跑内置三组演示数据")
    args = ap.parse_args()

    if args.demo:
        dt = PlayerTrickDetector()
        # 假撤退：玩家 A 靠近后折返
        print("== 假撤退演示 ==")
        for i, (x, y) in enumerate([(100, 0), (120, 20), (150, 50), (120, 40), (300, 90)]):
            dt.update(0, 0, [{"uid": "A", "x_now": x, "y_now": y}])
            time.sleep(0.05)
        for r in dt.detect(0, 0):
            print("🔍", r["tactic"], "|", r["detail"])
        print("== 诱骗演示 ==")
        dt2 = PlayerTrickDetector()
        for _ in range(4):
            dt2.update(0, 0, [
                {"uid": "weak", "x_now": 80, "y_now": 0, "threat_score": 10},
                {"uid": "boss", "x_now": 300, "y_now": 0, "threat_score": 400},
            ])
        for r in dt2.detect(0, 0):
            print("🔍", r["tactic"], "|", r["detail"])
        print("== 包围演示 ==")
        dt3 = PlayerTrickDetector()
        for k in range(4):
            dt3.update(0, 0, [
                {"uid": "L", "x_now": -150, "y_now": 0},
                {"uid": "R", "x_now": 150, "y_now": 0},
            ])
        for r in dt3.detect(0, 0):
            print("🔍", r["tactic"], "|", r["detail"])
        print("== 演示完毕 ==")
    else:
        dt = get_detector()
        print(dt.detect())