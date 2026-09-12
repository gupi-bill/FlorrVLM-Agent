#!/usr/bin/env python3
"""
FlorrVLM-Agent 配置加载 config.py
==================================
所有阈值/路径集中到 yaml，改参数不用改源码。

加载优先级（低 → 高）：
  1. 代码内置 DEFAULT（兜底）
  2. config.yaml（通用项）
  3. 游戏档案 game_profiles/<agent.game>.yaml（游戏专属项）
  4. tuned_overrides.yaml（v1.0 自动调参产生的覆盖，最优先）

特色：
- 配置以"嵌套 dict 树"保存
- get("a.b.c", default) 按点分路径在树里查，坏键沿途回退到 default
- reload_if_changed()：检测 config.yaml 与当前档案的 mtime，变了就重载，
  供 agent_main 每轮调用 →"改完保存即热加载"
"""
import copy
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
PROFILE_DIR = os.path.join(os.path.dirname(CONFIG_PATH), "game_profiles")
TUNED_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "tuned_overrides.yaml")

# 兜底默认值（扁平点分键）。仅当 yaml 一路都没有时使用。
DEFAULT = {
    "server.perception_port": 5001,
    "server.panel_port": 5002,

    "predictor.predict_seconds": 1.2,
    "predictor.min_frames": 3,
    "predictor.entity_timeout": 0.4,
    "predictor.max_output_entities": 8,
    "predictor.history_maxlen": 10,
    "predictor.confidence_threshold": 0.65,
    "predictor.rarity_highest_boss": ["Unique", "Eternal"],
    "predictor.rarity_boss": ["Super"],
    "predictor.rarity_elite": ["Ultra", "Mythic", "Legendary", "Epic"],
    "predictor.rarity_normal": ["Rare", "Unusual", "Common"],
    "predictor.threat": {
        "highest_boss": 1000, "boss": 400, "elite": 120, "normal": 15,
        "player_enemy": 150, "player_ally": 0, "unknown": 5,
    },

    "combat.eval_debounce_interval": 0.7,
    "combat.jitter_base": 8,
    "combat.jitter_max": 15,
    "combat.chase_max_distance": 400,
    "combat.chase_min_category": "elite",
    "combat.retreat_ratio": 1.0,        # v1.0 自动调参：越高越敢打，越低越早跑
    "combat.safe_zone_margin": 100,
    "combat.safe_zone_w": 1920,
    "combat.safe_zone_h": 1080,

    "agent.loop_interval": 0.5,
    "agent.game": "florr",
    "agent.webhook_url": "",
    "agent.death_frame_threshold": 8,
    "agent.boss_memory_interval": 12,
    "agent.boss_sample_max": 120,
    "agent.boss_close_dist": 120,
    "agent.learning_stats_interval": 24,
    "agent.kb_max_mb": 50,
    "agent.kb_archive_dir": "knowledge_archive",

    "mcp.streamable_http": False,
    "mcp.streamable_port": 5050,

    "paths.knowledge_md": "knowledge_md",
    "paths.frames": "video_frames",
    "paths.run_logs": "run_logs",

    "logs.retention_days": 7,
    "logs.max_size_mb": 20,

    "resource.enabled": True,
    "resource.check_interval": 30,
    "resource.mem_limit_mb": 500,
    "resource.cpu_limit_pct": 80,
    "resource.mem_hard_mb": 1000,
}

_CFG: dict = {}


def _merge(dst: dict, src: dict) -> dict:
    """把 src 深度合并进 dst（原地），dict 递归合并，其余覆盖。"""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def _read_yaml(path: str) -> dict:
    """读 yaml 为嵌套 dict；无文件/解析失败返回 {}。"""
    try:
        import yaml
    except ImportError:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _flatten_default() -> dict:
    """把 DEFAULT 的扁平点分键转成嵌套树。"""
    tree = {}
    for key, val in DEFAULT.items():
        parts = key.split(".")
        cur = tree
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = copy.deepcopy(val)
    return tree


def _reload():
    """按优先级合并（低→高）：DEFAULT < config.yaml < 游戏档案 < tuned_overrides。"""
    tree = _flatten_default()
    _merge(tree, _read_yaml(CONFIG_PATH))
    game = tree.get("agent", {}).get("game", "florr")
    profile_path = os.path.join(PROFILE_DIR, f"{game}.yaml")
    _merge(tree, _read_yaml(profile_path))
    _merge(tree, _read_yaml(TUNED_PATH))  # v1.0 自动调参覆盖
    global _CFG
    _CFG = tree


def get(path: str, default=None):
    """按点分路径在配置树中读取；坏键沿途回退 default。"""
    if not path:
        return default
    parts = path.split(".")
    cur = _CFG
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def all() -> dict:
    return copy.deepcopy(_CFG)


_reload()  # 导入即加载一次


def reload_if_changed() -> bool:
    """检测 config.yaml 或当前游戏档案是否变化，变了就热加载。"""
    last = getattr(reload_if_changed, "_mtime", None)
    game = _CFG.get("agent", {}).get("game", "florr")
    paths = [CONFIG_PATH, os.path.join(PROFILE_DIR, f"{game}.yaml"), TUNED_PATH]
    mtimes = []
    for p in paths:
        try:
            mtimes.append(os.path.getmtime(p))
        except OSError:
            mtimes.append(None)
    stamp = tuple(mtimes)
    if last is not None and stamp != last:
        _reload()
        reload_if_changed._mtime = stamp
        return True
    if last is None:
        reload_if_changed._mtime = stamp
    return False


if __name__ == "__main__":
    print("game:", get("agent.game"))
    print("threat:", get("predictor.threat"))
    print("chase_min_category:", get("combat.chase_min_category"))
    print("game.name:", get("game.name"))
    print("game.description:", get("game.description"))