#!/usr/bin/env python3
"""
Universal-Game-Framework 游戏档案自检器  game_profile_check.py  (v1.8 → S10 语义版)
================================================================================
投 bo / 换游戏之前，先校验 game_profiles/<name>.yaml 是否完整、字段是否合法，
避免"格式写错 → 启动才报错"的低级问题。

S10 升级：从"字段在不在"升级到"语义对不对"。
  ERROR（阻断，退出码 1）：
    - 必填字段缺失 / 类型错误（沿用旧版）
    - 同一个稀有度字符串出现在两个不同档位（分档自相矛盾）
    - 威胁分不满足 highest_boss ≥ boss ≥ elite ≥ normal（金字塔倒置）
    - 威胁分为负数
    - game.name 与文件名不一致
    - 出现未知顶层键（拼写错误 / 抄错结构）
    - combat.sets 存在但不是非空字符串列表
    - combat.default_set 不在 combat.sets 里
    - perception.mock.entities 里的 rarity 不属于任何已声明档位
  WARN（建议，不阻断）：
    - 缺 game.description / server.perception_port / combat.sets / combat.tactics

用法：
  python game_profile_check.py            # 校验 config.yaml 当前激活的游戏
  python game_profile_check.py <name>     # 校验指定档案（如 florr）
  python game_profile_check.py --all      # 校验 game_profiles/ 下全部档案（跳过 _ 开头的模板）
  python game_profile_check.py --strict   # 建议项也算错误（用于 CI 门禁）

返回码：0=通过；1=存在 ERROR（--strict 时 WARN 也算）。
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

# 允许的顶层键（其余视为拼写错误）
KNOWN_TOP_LEVEL = {"game", "predictor", "combat", "perception", "server", "agent", "mcp", "paths"}
# 稀有度四档 → 用于查重与金字塔校验
RARITY_TIERS = ["rarity_highest_boss", "rarity_boss", "rarity_elite", "rarity_normal"]
# 威胁分金字塔顺序（前者必须 ≥ 后者）
THREAT_LADDER = ["highest_boss", "boss", "elite", "normal"]

WARN_PREFIX = "[建议] "


def _profile_path(name: str) -> str:
    return os.path.join(PROFILE_DIR, f"{name}.yaml")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_detail(name: str) -> dict:
    """校验单个档案，返回 {'ok':bool,'errors':[...],'warnings':[...]}。"""
    res = {"ok": False, "errors": [], "warnings": []}
    path = _profile_path(name)
    if not os.path.exists(path):
        res["errors"].append(f"档案不存在: {path}（可用 tools/add_game.py 生成）")
        return res
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        res["errors"].append(f"YAML 语法错误: {e}")
        return res
    if not isinstance(data, dict):
        res["errors"].append("档案根节点必须是映射（key: value 结构）")
        return res

    # —— 未知顶层键 ——
    for key in data:
        if key not in KNOWN_TOP_LEVEL:
            res["errors"].append(
                f"未知顶层键: {key}（允许: {sorted(KNOWN_TOP_LEVEL)}，多为拼写错误）")

    # —— game 元信息 ——
    game = data.get("game") or {}
    if not isinstance(game, dict):
        res["errors"].append("game 段必须是映射")
        game = {}
    else:
        if not game.get("name"):
            res["errors"].append("缺少 game.name")
        elif str(game["name"]) != name:
            res["errors"].append(
                f"game.name='{game['name']}' 与文件名 '{name}' 不一致（切换游戏会读不到）")
        if not game.get("description"):
            res["warnings"].append("缺少 game.description（大盘与 brief 会显示为空）")

    # —— 稀有度分档 ——
    pred = data.get("predictor") or {}
    if not isinstance(pred, dict):
        res["errors"].append("predictor 段必须是映射")
        pred = {}
    tier_values = {}
    for key in RARITY_TIERS:
        val = pred.get(key)
        if val is None:
            res["errors"].append(f"缺少 predictor.{key}（建议至少填一种）")
            continue
        if not isinstance(val, list) or not val:
            res["errors"].append(f"predictor.{key} 应为非空列表")
            continue
        if not all(isinstance(x, str) and x.strip() for x in val):
            res["errors"].append(f"predictor.{key} 列表元素应均为非空字符串")
            continue
        tier_values[key] = [x.strip() for x in val]

    # 同一稀有度串出现在两个档位 → 分档自相矛盾
    seen = {}
    for tier, vals in tier_values.items():
        for v in vals:
            if v in seen and seen[v] != tier:
                res["errors"].append(
                    f"稀有度 '{v}' 同时出现在 {seen[v]} 与 {tier}（分档自相矛盾，分类结果不确定）")
            seen.setdefault(v, tier)

    # —— 威胁分 ——
    threats = pred.get("threat") or {}
    if not isinstance(threats, dict):
        res["errors"].append("predictor.threat 段必须是映射")
        threats = {}
    for key in REQUIRED_THREATS:
        if key not in threats:
            res["errors"].append(f"缺少 predictor.threat.{key}")
        elif not _is_num(threats[key]):
            res["errors"].append(f"predictor.threat.{key} 应为数字")
        elif threats[key] < 0:
            res["errors"].append(f"predictor.threat.{key} 为负数({threats[key]})")
    # 金字塔单调性
    for hi, lo in zip(THREAT_LADDER, THREAT_LADDER[1:]):
        if _is_num(threats.get(hi)) and _is_num(threats.get(lo)) and threats[hi] < threats[lo]:
            res["errors"].append(
                f"威胁分金字塔倒置: {hi}({threats[hi]}) < {lo}({threats[lo]})，应为 {hi} ≥ {lo}")

    # —— combat ——
    combat = data.get("combat") or {}
    if not isinstance(combat, dict):
        res["errors"].append("combat 段必须是映射")
        combat = {}
    chase = combat.get("chase_min_category")
    if not chase:
        res["errors"].append("缺少 combat.chase_min_category")
    elif chase not in VALID_CHASE:
        res["errors"].append(
            f"combat.chase_min_category 值非法: {chase}（可用: {sorted(VALID_CHASE)}）")
    sets = combat.get("sets")
    if sets is None:
        res["warnings"].append("缺少 combat.sets（套装清单，切换套装与大盘展示会用到）")
    elif not isinstance(sets, list) or not sets or not all(isinstance(s, str) for s in sets):
        res["errors"].append("combat.sets 应为非空字符串列表")
        sets = None
    default_set = combat.get("default_set")
    if default_set is not None and sets and default_set not in sets:
        res["errors"].append(f"combat.default_set='{default_set}' 不在 combat.sets 里: {sets}")
    if not combat.get("tactics"):
        res["warnings"].append("缺少 combat.tactics（战术模板，写进知识库供决策引用）")

    # —— 感知端口 ——
    server = data.get("server") or {}
    if not isinstance(server, dict) or server.get("perception_port") is None:
        res["warnings"].append(
            "缺少 server.perception_port（多游戏并行时会都挤在 5001，建议每款游戏一个端口）")

    # —— mock 实体与稀有度档位一致性 ——
    mock = ((data.get("perception") or {}).get("mock") or {})
    entities = mock.get("entities")
    if entities is not None:
        if not isinstance(entities, list):
            res["errors"].append("perception.mock.entities 应为列表")
        else:
            known = set(seen) | {"unknown"}
            for i, ent in enumerate(entities):
                if not isinstance(ent, dict):
                    res["errors"].append(f"perception.mock.entities[{i}] 应为映射")
                    continue
                rar = ent.get("rarity")
                if rar is not None and rar not in known:
                    res["errors"].append(
                        f"perception.mock.entities[{i}].rarity='{rar}' 不属于任何已声明档位"
                        f"（已声明: {sorted(seen)}）")

    res["ok"] = not res["errors"]
    return res


def check_one(name: str) -> tuple:
    """向后兼容入口：返回 (ok, problems)。建议项以 '[建议] ' 前缀附在 problems 里。"""
    detail = check_detail(name)
    problems = list(detail["errors"]) + [WARN_PREFIX + w for w in detail["warnings"]]
    return detail["ok"], problems


def check_all(strict: bool = False) -> tuple:
    """校验全部档案（跳过 _ 开头的模板），返回 (ok, [(name, detail), ...])。"""
    if not os.path.isdir(PROFILE_DIR):
        files = []
    else:
        files = sorted(f for f in os.listdir(PROFILE_DIR)
                       if f.endswith(".yaml") and not f.startswith("_"))
    results = []
    ok = True
    for fn in files:
        name = fn[:-5]
        detail = check_detail(name)
        ok = ok and detail["ok"] and not (strict and detail["warnings"])
        results.append((name, detail))
    return ok, results


def report_all(strict: bool = False) -> str:
    """校验全部档案，返回人类可读文本。"""
    ok, results = check_all(strict=strict)
    if not results:
        return "⚠ 未找到任何游戏档案(game_profiles/ 为空)"
    lines = []
    warn_count = 0
    for name, detail in results:
        one_ok = detail["ok"] and not (strict and detail["warnings"])
        warn_count += len(detail["warnings"])
        lines.append(f"[{'✅' if one_ok else '❌'}] {name}")
        lines += [f"     ✗ {p}" for p in detail["errors"]]
        lines += [f"     ⚠ {p}" for p in detail["warnings"]]
    lines.append("")
    if ok:
        tail = "✅ 全部档案通过" + ("" if warn_count == 0 else f"（{warn_count} 条建议）")
    else:
        tail = "❌ 存在需修复的问题(见上)"
    lines.append(tail)
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:]]
    strict = "--strict" in args
    positional = [a for a in args if not a.startswith("-")]
    if "--all" in args or (strict and not positional):
        print(report_all(strict=strict))
        return 0 if check_all(strict=strict)[0] else 1
    # 默认校验当前激活游戏；也可指定名字
    name = positional[0] if positional else ""
    if not name:
        try:
            import config
            name = config.get("agent.game", "florr")
        except Exception:
            name = "florr"
    detail = check_detail(name)
    ok = detail["ok"] and not (strict and detail["warnings"])
    head = f"[{'✅' if ok else '❌'}] 游戏档案自检: {name}"
    print(head)
    for p in detail["errors"]:
        print(f"   ✗ {p}")
    for p in detail["warnings"]:
        print(f"   ⚠ {p}")
    if ok:
        print("   ✓ 档案完整，可以 play")
    else:
        print("   ✗ 请先修复上述问题（或用 tools/add_game.py 重新登记）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
