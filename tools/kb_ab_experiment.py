#!/usr/bin/env python3
"""S27 · P2 知识闭环 A/B 实证（离线代理指标）。

背景：FUTURE.md 核心命题 P2「进化闭环」要求证明「学过 vs 没学过，效果可测」。
纯离线 mock 环境**没有真实游戏胜负**，无法测真实胜率。本实验改测一个
**离线可测、且语义指向存活率的代理指标**：

    在「需要谨慎」的局面下，决策是否采取保守动作（defend）。

机制依据（读源码得出，非臆测）：
  - 知识唯一能改变动作的落点在 `knowledge_loop.decide_action`：
      decision==cautious_fight 且（hp<0.6 或 threat>1.0）且命中 retreat/keep_distance → "defend"
  - 无知识时，`agent_main._fallback_decide` 对 cautious_fight 返回 "attack"（激进）

因此：
  - 对照组 baseline（无知识）：危险局面下倾向 attack
  - 实验组 learned（有知识）：危险局面下转为 defend

本实验量化这一差异并做 Bootstrap 显著性检验。

**重要边界（诚实声明）**：这证明的是「知识确实改变动作」（机制成立），
不是「改变的动作真的提升了胜率」（效果成立）。后者需真机，见报告遗留项。

用法：
  python tools/kb_ab_experiment.py                 # 默认 2000 次 bootstrap
  python tools/kb_ab_experiment.py --json out.json

退出码：0=达标（知识组保守率显著更高）；1=未达标。
"""
import argparse
import json
import os
import random
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import knowledge_loop  # noqa: E402

# 知识命中后抽取的战术规则（对应 space_invaders 档案 combat.tactics）
KNOWLEDGE_TACTICS = ["retreat", "keep_distance"]


def fallthrough_action(decision: str) -> str:
    """无知识时 agent_main._fallback_decide 的动作（复刻其尾部三段）。"""
    if decision == "retreat":
        return "defend"
    if decision == "cautious_fight":
        return "attack"
    return "attack"


def learned_action(decision: str, hp_ratio: float, threat_ratio: float) -> str:
    """有知识时：先试知识路径，未通过闸门则落回 fallthrough。"""
    kb = knowledge_loop.decide_action(
        decision, KNOWLEDGE_TACTICS, hp_ratio=hp_ratio, threat_ratio=threat_ratio)
    return kb if kb else fallthrough_action(decision)


def build_scenarios():
    """扫描矩阵：decision × hp_ratio × threat_ratio。"""
    rows = []
    for decision in ("fight", "cautious_fight", "retreat"):
        for hp in (1.0, 0.8, 0.5, 0.3):
            for threat in (0.0, 0.5, 1.0, 1.5, 2.0):
                rows.append((decision, hp, threat))
    return rows


def is_dangerous(decision: str, hp_ratio: float, threat_ratio: float) -> bool:
    """是否属于「需要谨慎」的局面。"""
    return (decision == "retreat"
            or hp_ratio < knowledge_loop.KB_GATE_HP
            or threat_ratio > knowledge_loop.KB_GATE_THREAT)


def run_ab():
    base_cons = []   # 对照组：每个危险局面是否保守（1/0）
    learn_cons = []  # 实验组
    rows = []
    for decision, hp, threat in build_scenarios():
        if not is_dangerous(decision, hp, threat):
            continue
        b = fallthrough_action(decision)
        l = learned_action(decision, hp, threat)
        base_cons.append(1 if b == "defend" else 0)
        learn_cons.append(1 if l == "defend" else 0)
        rows.append({"decision": decision, "hp_ratio": hp,
                     "threat_ratio": threat, "baseline": b, "learned": l})
    return base_cons, learn_cons, rows


def bootstrap_diff_ci(a, b, n=2000, seed=42):
    """两样本 Bootstrap：learned - baseline 均值差的 95% CI。"""
    rng = random.Random(seed)
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return None, None, None
    diffs = []
    for _ in range(n):
        ma = sum(rng.choice(a) for _ in range(na)) / na
        mb = sum(rng.choice(b) for _ in range(nb)) / nb
        diffs.append(mb - ma)
    diffs.sort()
    lo = diffs[int(0.025 * n)]
    hi = diffs[int(0.975 * n) - 1]
    mean_diff = sum(b - a for a, b in zip(a, b)) / min(na, nb)
    return round(mean_diff, 4), round(lo, 4), round(hi, 4)


def main():
    ap = argparse.ArgumentParser(description="S27 知识闭环 A/B 实证")
    ap.add_argument("--json", default=None)
    ap.add_argument("--bootstrap", type=int, default=2000)
    args = ap.parse_args()

    base, learn, rows = run_ab()
    n = len(base)
    base_rate = sum(base) / n if n else 0.0
    learn_rate = sum(learn) / n if n else 0.0
    diff, lo, hi = bootstrap_diff_ci(base, learn, n=args.bootstrap)
    significant = (lo is not None and lo > 0)

    result = {
        "metric": "dangerous-situation conservative(defend) rate",
        "n_dangerous_scenarios": n,
        "baseline_conservative_rate": round(base_rate, 4),
        "learned_conservative_rate": round(learn_rate, 4),
        "diff": diff,
        "diff_ci95": [lo, hi],
        "significant_positive": significant,
        "knowledge_tactics": KNOWLEDGE_TACTICS,
        "sample_rows": rows[:8],
        "caveat": "代理指标；真胜率需真机（见 devplan/KB_AB_S27.md）",
    }

    print("===== S27 知识闭环 A/B 实证 =====")
    print(f"危险局面样本数       : {n}")
    print(f"对照组 保守率        : {base_rate:.2%}")
    print(f"实验组 保守率        : {learn_rate:.2%}")
    print(f"差值 (learned-base)  : {diff}  95%CI=[{lo}, {hi}]")
    print(f"显著为正             : {'✅ 是' if significant else '❌ 否'}")
    print("结论                 : " + ("✅ 知识确实改变动作（机制成立）"
                                        if significant else "❌ 未见差异"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 报告: {args.json}")
    return 0 if significant else 1


if __name__ == "__main__":
    sys.exit(main())
