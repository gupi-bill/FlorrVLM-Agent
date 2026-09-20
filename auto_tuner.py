#!/usr/bin/env python3
"""
Universal-Game-Framework 基础自动调参 auto_tuner.py
========================================
v1.0 —— 多次对局后根据"战损统计"自动微调阈值，不用手动改配置。

原理：
  - 每次统计周期(learning_stats)把命中率/死亡等喂给 tune()。
  - tune() 在边界内调整两个可调量：
      combat.retreat_ratio         越高越敢打，越低越早跑（被打疼就调低）
      predictor.confidence_threshold 越高越信预判（预判不准就调低采信线）
  - 结果写入 tuned_overrides.yaml，config.py 以最高优先级合并 → 热加载生效。
  - 用 hold 计数避免频繁抖动：每次调整后一段时间内不再乱动。

用法（通常由 agent_main 自动调用）：
  import auto_tuner
  auto_tuner.tune(hits=10, attempts=20, deaths_extra=1)
"""
import os

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TUNED_PATH = config.TUNED_PATH

# 可调范围
RETREAT_RATIO_MIN, RETREAT_RATIO_MAX = 0.5, 1.5
CONF_THRESH_MIN, CONF_THRESH_MAX = 0.30, 0.90
CONF_DEFAULT = config.DEFAULT.get("predictor.confidence_threshold", 0.65)

# 每调一次后"冷静"几个周期，避免来回震荡
HOLD = 3


def _read() -> dict:
    try:
        import yaml
        if os.path.exists(TUNED_PATH):
            with open(TUNED_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _write(data: dict):
    try:
        import yaml
        with open(TUNED_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception:      # v2.0：原来只捕 OSError，yaml 缺失/序列化失败会直接抛穿
        pass


def _section(data: dict, name: str) -> dict:
    """
    取一个子段，保证返回 dict。

    v2.0：tuned_overrides.yaml 被手写坏（例如 `combat: "x"`）时，
    原来的 `o.get("combat", {}).get(...)` 会抛 AttributeError 并一路
    炸到 agent_main 的调参调用点。这里统一兜底成空 dict。
    """
    sec = data.get(name)
    return sec if isinstance(sec, dict) else {}


def _clamp(value, lo: float, hi: float, default: float) -> float:
    """安全转 float 并夹到 [lo, hi]；坏值回退 default。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):   # NaN / Inf
        return default
    return max(lo, min(hi, v))


def current() -> dict:
    """
    当前生效的调参覆盖（无则用默认值）。

    v2.0：返回值一律过 _clamp —— 文件里被写坏的越界值（如 retreat_ratio: 99）
    原来会被原样报给 status() 并参与下一轮计算，直到下次 tune 才被纠正。
    """
    o = _read()
    return {
        "combat.retreat_ratio": _clamp(
            _section(o, "combat").get("retreat_ratio",
                     config.get("combat.retreat_ratio", 1.0)),
            RETREAT_RATIO_MIN, RETREAT_RATIO_MAX, 1.0),
        "predictor.confidence_threshold": _clamp(
            _section(o, "predictor").get(
                "confidence_threshold",
                config.get("predictor.confidence_threshold", CONF_DEFAULT)),
            CONF_THRESH_MIN, CONF_THRESH_MAX, CONF_DEFAULT),
    }


def tune(hits: int = 0, attempts: int = 0, deaths_extra: int = 0) -> str:
    """
    根据一批统计调整阈值。返回改动说明；没改动返回提示。
      hits/attempts: 知识库命中统计（命中率低 → 预判也别太自信）
      deaths_extra : 本周期新增的死亡次数（多 → 调低 retreat_ratio 更早跑）
    """
    o = _read()
    changed = []

    # hold：上次调整后的冷静期。原实现只累加 `_hold` 计数却从不消费，
    # 与模块文档「每次调整后一段时间内不再乱动」不符，实测会持续震荡。
    try:
        cooldown = int(o.get("_cooldown", 0))
    except (TypeError, ValueError):
        cooldown = 0
    if cooldown > 0:
        o["_cooldown"] = cooldown - 1
        _write(o)
        return f"[调参] 冷静期(剩 {cooldown - 1} 周期)，本轮不调整"

    # 1) 死亡多 → 更保守（更早跑）
    if deaths_extra > 0:
        cur = _clamp(_section(o, "combat").get("retreat_ratio",
                              config.get("combat.retreat_ratio", 1.0)),
                     RETREAT_RATIO_MIN, RETREAT_RATIO_MAX, 1.0)
        step = 0.1 * max(int(deaths_extra), 0)
        nxt = max(RETREAT_RATIO_MIN, cur - step)
        if nxt < cur:
            o.setdefault("combat", {})
            if not isinstance(o["combat"], dict):
                o["combat"] = {}
            o["combat"]["retreat_ratio"] = round(nxt, 2)
            changed.append(f"retreat_ratio {cur}→{nxt:.2f}(死亡增多，更早跑)")

    # 2) 知识库命中率低 → 调低置信度采信线（别太信预判）
    if attempts > 0 and hits / attempts < 0.5:
        cur = _clamp(_section(o, "predictor").get(
            "confidence_threshold",
            config.get("predictor.confidence_threshold", CONF_DEFAULT)),
            CONF_THRESH_MIN, CONF_THRESH_MAX, CONF_DEFAULT)
        nxt = max(CONF_THRESH_MIN, cur - 0.05)
        if nxt < cur:
            o.setdefault("predictor", {})
            if not isinstance(o["predictor"], dict):
                o["predictor"] = {}
            o["predictor"]["confidence_threshold"] = round(nxt, 2)
            changed.append(f"confidence {cur}→{nxt:.2f}(命中率低，采信线下调)")

    # 真调整过 → 进入冷静期；没调整 → 立即允许下一轮评估
    o["_cooldown"] = HOLD if changed else 0
    _write(o)
    if not changed:
        return "[调参] 本轮统计无需调整(阈值已在合理区间)"
    return "[调参] " + "；".join(changed)


def reset():
    """清空调参覆盖，回到默认。"""
    try:
        os.remove(TUNED_PATH)
    except OSError:
        pass
    return "[调参] 已重置为默认阈值"


def status() -> str:
    c = current()
    return (f"[调参] 当前阈值: 敢打度={c['combat.retreat_ratio']} "
            f"置信线={c['predictor.confidence_threshold']}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        print(reset())
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print(status())
    else:
        print(tune(hits=8, attempts=20, deaths_extra=2))  # 演示
        print(status())