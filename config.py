#!/usr/bin/env python3
"""
FlorrVLM-Agent 配置加载 config.py
==================================
v0.5：所有阈值/路径集中到 config.yaml，改参数不用改源码。

特色：
- get("a.b.c", default) 点分路径读取，运行期实时查表
- 代码内置 DEFAULT（兜底），yaml 覆盖 DEFAULT
- reload_if_changed()：检测文件 mtime，变了就重载并返回 True，
  供 agent_main 每轮调用，实现"改完保存即热加载"
- 1.0 之后，这份 yaml + 相关的 Florr 常量可整体作为第一张"游戏档案"抽走
"""
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

# 兜底默认值（代码内置，yaml 缺失时才用）。键用点分路径，扁平存放。
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
    "combat.safe_zone_margin": 100,
    "combat.safe_zone_w": 1920,
    "combat.safe_zone_h": 1080,

    "agent.loop_interval": 0.5,
    "agent.death_frame_threshold": 8,
    "agent.boss_memory_interval": 12,
    "agent.boss_sample_max": 120,
    "agent.boss_close_dist": 120,
    "agent.learning_stats_interval": 24,

    "mcp.streamable_http": False,
    "mcp.streamable_port": 5050,

    "paths.knowledge_md": "knowledge_md",
    "paths.frames": "video_frames",
    "paths.run_logs": "run_logs",

    "logs.retention_days": 7,
    "logs.max_size_mb": 20,
}

_CFG = dict(DEFAULT)  # 运行期字典，get() 读它，热加载时重填


def _load_yaml_flat() -> dict:
    """读 config.yaml，拍平为 {点分键: 值}；失败则返回空（全走默认）。"""
    try:
        import yaml
    except ImportError:
        return {}
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}

    flat = {}

    def _walk(prefix: str, node):
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(f"{prefix}.{k}" if prefix else str(k), v)
        else:
            flat[prefix] = node

    _walk("", data)
    return flat


def _reload():
    """重载：yaml 覆盖默认，写入运行期字典。"""
    overrides = _load_yaml_flat()
    _CFG.clear()
    _CFG.update(DEFAULT)
    _CFG.update(overrides)


def get(path: str, default=None):
    """读取配置：点分路径。实时查运行期字典，热加载后自动读到新值。"""
    return _CFG.get(path, default)


def all() -> dict:
    return dict(_CFG)


# 导入即加载一次
_reload()


def reload_if_changed() -> bool:
    """
    检测 config.yaml 是否变化，变了就热加载。
    返回 True 表示重载了，调用方可据此刷新各模块常量。
    """
    last_mtime = getattr(reload_if_changed, "_mtime", None)
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return False
    if last_mtime is not None and mtime != last_mtime:
        _reload()
        reload_if_changed._mtime = mtime
        return True
    # 首次记录
    if last_mtime is None:
        reload_if_changed._mtime = mtime
    return False


if __name__ == "__main__":
    # 自检：打印当前生效配置，缺失键有默认值
    print("perception_port:", get("server.perception_port"))
    print("predict_seconds:", get("predictor.predict_seconds"))
    print("threat:", get("predictor.threat"))
    print("confidence_threshold:", get("predictor.confidence_threshold"))
    print("重载测试:", reload_if_changed())