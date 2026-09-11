#!/usr/bin/env python3
"""
FlorrVLM-Agent 游戏档案自检器  game_profile_check.py  (v1.8)
============================================================
投 bo / 换游戏之前，先校验 game_profiles/<name>.yaml 是否完整、字段是否合法，
避免"格式写错 → 启动才报错"的低级问题。

用法：
  python game_profile_check.py            # 校验 config.yaml 当前激活的游戏
  python game_profile_check.py <name>     # 校验指定档案（如 florr）
  python game_profile_check.py --all      # 校验 game_profiles/ 下全部档案

返回码：0=全部通过；1=至少一处问题。
"""
import os
import sys

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(BASE_DIR, "game_profiles")

# 各分类的威胁分必须有这几个键
REQUIRED_THREATS = [
    "highest_boss", "boss", "elite", "normal", "player_enemy", "player_ally", "unknown",
]
# 稀有度回退优先级（低档可空，但至少有一类有效）
VALID_CHASE = {"highest_boss", "boss", "elite", "normal", "player_enemy"}


def _profile_path(name: str) -> str:
    return os.path.join(PROFILE_DIR, f"{name}.yaml")


def check_one(name: str) -> tuple:
    """校验单个档案，返回 (ok: bool, problems: list)。"""
    path = _profile_path(name)
    problems = []
    if not os.path.exists(path):
        return False, [f"档案不存在: {path}（可用 tools/add_game.py 生成）"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        return False, [f"YAML 语法错误: {e}"]

    game = data.get("game") or {}
    if not game.get("name"):
        problems.append("缺少 game.name")
    pred = data.get("predictor") or {}
    # 稀有度字段
    for key in ("rarity_highest_boss", "rarity_boss", "rarity_elite", "rarity_normal"):
        val = pred.get(key)
        if val is None:
            problems.append(f"缺少 predictor.{key}（建议至少填一种）")
        elif not isinstance(val, list) or not val:
            problems.append(f"predictor.{key} 应为非空列表")
    # 威胁分
    threats = pred.get("threat") or {}
    for key in REQUIRED_THREATS:
        if key not in threats:
            problems.append(f"缺少 predictor.threat.{key}")
        elif not isinstance(threats[key], (int, float)):
            problems.append(f"predictor.threat.{key} 应为数字")
    # 追击档
    chase = (data.get("combat") or {}).get("chase_min_category")
    if not chase:
        problems.append("缺少 combat.chase_min_category")
    elif chase not in VALID_CHASE:
        problems.append(f"combat.chase_min_category 值非法: {chase}（可用: {sorted(VALID_CHASE)}）")

    return (len(problems) == 0), problems


def report_all() -> str:
    """校验全部档案，返回人类可读文本。"""
    if not os.path.isdir(PROFILE_DIR):
        files = []
    else:
        files = sorted(f for f in os.listdir(PROFILE_DIR) if f.endswith(".yaml"))
    if not files:
        return "⚠ 未找到任何游戏档案(game_profiles/ 为空)"
    lines = []
    all_ok = True
    for fn in files:
        name = fn[:-5]
        ok, problems = check_one(name)
        all_ok = all_ok and ok
        lines.append(f"[{'✅' if ok else '❌'}] {name}")
        lines += [f"     - {p}" for p in problems]
    lines.append("")
    lines.append("✅ 全部档案通过" if all_ok else "❌ 存在需修复的问题(见上)")
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:]]
    if "--all" in args:
        text = report_all()
        ok = "❌" not in text.split("\n")[-2]  # 看倒数第二行结论
        print(text)
        return 0 if ok else 1
    # 默认校验当前激活游戏；也可指定名字
    name = ""
    for a in args:
        if not a.startswith("-"):
            name = a
    if not name:
        try:
            import config
            name = config.get("agent.game", "florr")
        except Exception:
            name = "florr"
    ok, problems = check_one(name)
    head = f"[{'✅' if ok else '❌'}] 游戏档案自检: {name}"
    print(head)
    for p in problems:
        print(f"   - {p}")
    print("   ✓ 档案完整，可以 play" if ok else "   ✗ 请先修复上述问题（或用 tools/add_game.py 重新登记）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())