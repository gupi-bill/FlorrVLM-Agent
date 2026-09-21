# S20 · 决策场景矩阵（战斗 / 组队 / 心态 / 边界）

> 执行时间：2026-09-22 05:58~06:2x（F 线） ｜ 交付：`tests/test_decision_scenarios.py`（38 用例）、本文
> 下表每一行均为**实测值**（由 `combat_judge.judge_combat` / `knowledge_loop` 真实调用导出），非预期值。

## 1. 战斗场景实测表

| # | 场景 | 构造 | decision | recommended_set | mindset | threat_ratio | 撤退原因 |
|---|---|---|---|---|---|---|---|
| 1 | 势均力敌单挑 | power=100, 1×normal | fight | combat | aggressive | 0.15 | — |
| 2 | 以少打多 | power=50, 12×normal | **retreat** | retreat | balanced | 3.60 | 敌方威胁(180)远超自身实力(50) |
| 3 | 被包围（四面精英） | power=60, 4×elite 环绕 | **retreat** | retreat | balanced | 8.00 | 敌方威胁(480)远超自身实力(60) |
| 4 | 血量极低遇多 BOSS | hp=10/100, 3×boss | **retreat** | retreat | conservative | 12.00 | 敌方威胁(1200)远超自身实力(100) |
| 5 | highest_boss 实力不足 | power=100 | **retreat** | retreat | conservative | 10.00 | highest_boss 出现且实力不足 |
| 6 | highest_boss 实力充足 | power=100000 | cautious_fight | tank | balanced | 0.01 | 实力充足，可对抗 |
| 7 | 精英在场可追击 | power=5000, 1×elite | fight | **chase** | aggressive | 0.024 | — |
| 8 | 空场无敌人 | power=100 | fight | combat | balanced | 0.00 | — |
| 9 | 实力为 0（感知未就绪） | power=0 | retreat | retreat | balanced | **999.0** | 威胁比取极大值兜底 |
| 10 | 坐标全 NaN | x/y=NaN | fight | combat | aggressive | 0.15 | NaN 未污染决策链 |
| 11 | 未知档位 | category 不存在 | fight | combat | aggressive | 0.05 | 按 unknown 兜底 |

## 2. 组队场景实测表

| # | 场景 | decision | recommended_set | 说明 |
|---|---|---|---|---|
| 12 | 队友输出型（combat 套） | fight | **team** | 我方转辅助，符合协同预期 |
| 13 | 队友抗伤型（tank 套） | fight | **combat** | 我方补输出，符合协同预期 |
| 14 | 跑路时被队友干扰 | **retreat** | **retreat** | 回归：逃生优先级高于协同，未被改成辅助套 |
| 15 | 空队友列表 | fight | combat | 协同不生效 |

## 3. 心态档位矩阵（实测）

| 最高威胁档位 | 威胁比 | mindset |
|---|---|---|
| normal | 0.2（power=100000） | aggressive |
| normal | 0.4（power=50） | balanced |
| elite | 0.01（power=100000） | aggressive |
| boss | 0.004（power=100000） | aggressive |
| boss | 4.0（power=100） | conservative |
| highest_boss | 10.0（power=100） | conservative |
| 无敌人 | — | balanced |

## 4. 知识闸门矩阵（S18 遗留① 的修复）

S18 实测发现「14 轮动作全是 defend」，当时记为「知识优先级过硬」。**本阶段复测修正了归因**：
真实原因是 dry-run 的 mock 场景里存在 `mantis`（boss 档，威胁 400），
快照显示 `decision=retreat / mindset=conservative / set=retreat` —— **决策本就是撤退，动作正确**。
但闸门仍然必要：它可以防止「空场却因为知识里写了撤退而一路防守」这类真实风险，
现由 `knowledge_gate` + 用例矩阵锁定。

`knowledge_gate(decision, tactics=[retreat, keep_distance], hp_ratio, threat_ratio)`：

| decision | hp=1.0, threat=0.0 | hp=0.3, threat=0.5 | hp=1.0, threat=2.0 | hp=1.0, threat=0.4 |
|---|---|---|---|---|
| fight | False | True（→ 无规则产出） | False | True（→ 无规则产出） |
| cautious_fight | **False**（空场不干预） | True → defend | True → defend | False（优势局不干预） |
| retreat | False（无威胁） | True → defend | True → defend | True → defend |

规则：场上无威胁一律不干预；`retreat` 放行；`cautious_fight` 需低血量(<0.6)或高威胁(>1.0)；
`fight` 仅在占优(threat<1.0)时放行。注意 `fight` 放行但 `apply_tactics` 未产出动作
（retreat 类知识不应把进攻改写成防守），属于预期行为。

## 5. 端到端（场景 → 动作）

`_fallback_decide` 在 `cautious_fight` 下的实测：

| hp_ratio | threat_ratio | 知识是否生效 | 动作 |
|---|---|---|---|
| 1.0 | 0.0 | 否 | attack |
| 0.2 | 2.0 | 是 | defend |
| 1.0 | 2.0 | 是 | defend |
| 1.0 | 0.5 | 否 | attack |

AFK 弹窗场景下无论知识如何一律 `idle`（最高优先级，已单测锁定）。

## 6. 本阶段改动

- `knowledge_loop.py`：新增 `KB_GATE_HP` / `KB_GATE_THRESHOLD`（`KB_GATE_THREAT`）、
  `knowledge_gate()`、`decide_action()`。
- `agent_main.py`：`_fallback_decide` 从「知识无条件优先」改为「先过局面闸门」，
  血量/威胁比从 `state.player` 与 `combat_eval.threat_ratio` 现读。
- `tests/test_knowledge_loop.py`：补充「空场/优势局不应用知识」回归断言。

## 7. 验收记录

```
$ python -m pytest tests/test_decision_scenarios.py -q     38 passed
$ python -m pytest tests/ -q                              <全量，见 PROGRESS>
$ bash scripts/check.sh                                    ✅ 全部门禁通过
```

## 8. 遗留

1. 场景期望值目前是「与当前实现一致」的基线快照（characterization test），
   若后续认为某场景的结论不合理（如被包围应优先找缺口而非直接撤退），需先改实现再改本表。
2. 组队协同只按队友**套装数量**判断，未考虑队友血量/距离，S22 后可增强。
3. `fight` 决策下闸门放行但无规则产出的情况未记入统计（引用计数不受影响）。
