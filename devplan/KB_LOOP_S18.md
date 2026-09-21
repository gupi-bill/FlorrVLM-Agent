# S18 · 知识闭环实证（学 → 检索 → 决策 → 复盘 → 回写）

> 执行时间：2026-09-22 05:28~05:5x（F 线） ｜ 环境：dry-run + 进程内 mock，无 LLM/VLM 密钥
> 交付：`knowledge_loop.py`、`tests/test_knowledge_loop.py`（32 用例）、本文

## 1. 结论先行

「越打越强」此前是文档措辞：链路能跑，但**闭环是断的**。本阶段把断点补上，并给出首组
可查询的量化指标。

| 指标 | 数值 | 来源 |
|---|---|---|
| 检索次数 | 14 | `agent_main.py --rounds 14` 实跑 |
| 命中次数 | 14 | 同上 |
| **命中率** | **100%** | 同上（florr，补种 seed 后） |
| 引用次数 | 14 | 同上 |
| **引用率** | **100%** | 同上 |
| 补种 seed 前 demo_arcade 命中率 | **0%**（检索「战术」0 命中） | 实测定量，见 §3 |
| 修复前「boss」检索命中文件数 | 87（跨全部游戏 + 根目录） | 实测定量，见 §3 |
| 修复后「boss」检索命中文件数（florr 分区） | 13 | 同上 |
| 测试用例 | 835 全绿（803 + 32 新增） | `pytest tests/ -q` |
| 门禁 | `bash scripts/check.sh` 退出码 0 | 见 §6 |

## 2. 修的三个真实缺陷

### D1 · 读取不分区，命中"别人家的经验"（严重）

S15 已把**写入**按游戏分区，但主循环第 6 步的 `kb_search` 仍不带 `game_name`：

```python
kb_result = await session.call_tool("kb_search", {"keyword": keyword})   # 修复前
```

于是检索扫的是整个 `knowledge_md/`，包括根目录旧模板与**其它游戏**的复盘。退出码 0、
日志格式完全正常，只有断言"命中的是不是本游戏的文档"才能暴露。现补上 `"game_name": _kb_game()`。

### D2 · 无 LLM 时知识完全不进决策（严重，本机正是这种环境）

`_fallback_decide(game_state, combat_eval)` **只收两个参数**，`llm_decide` 拿到的
`kb_tactics` 在无 API key 时被直接丢弃。也就是说：在没有任何密钥的环境里，知识检索得再准，
也只是写进日志，一个动作都影响不了 —— "知识闭环"在这个环境里等于不存在。

现为 `_fallback_decide` 增加 `kb_tactics` 参数，命中条目经 `extract_tactics` →
`apply_tactics` 翻译成动作倾向，并在动作上打 `source: "kb"` 标记供回归测试锁定。

### D3 · 指标只有文本流水，不可查询

原实现把命中情况写进 `learn_stats` 列表，定期 append 成一行 md 文本
（`knowledge_md/learning_stats.md`），只能人读、不能机查，也没有"引用"这一维。
现改为 `LearningStats` 结构化计数器（检索 / 命中 / 引用 + 按关键词下钻），
持久化到 `run_logs/learning_stats.json`，并新增 CLI `kb_stats` 查询。

## 3. 实测口径对比（修复前 vs 修复后）

```
[修复前 全库]   战术: hit=True,  命中文件 10 个
[修复前 全库]   boss: hit=True,  命中文件 87 个   ← 绝大多数是别的游戏的复盘
[修复后 florr]          战术: 命中 3  ；boss: 命中 13
[修复后 space_invaders] 战术: 命中 3  ；boss: 命中 43
[修复后 demo_arcade]    战术: 命中 0  ← 未补种 seed，命中率为 0
[demo_arcade 执行 kb_seed 后] 战术: 命中 True ；boss: 命中 True
```

关键点：**修复前的「命中率高」是假的**。87 个命中文件里绝大多数属于别的游戏，
agent 学的是别人的经验；修复后数字下降但语义正确。demo_arcade 的 0 命中则说明
seed 是闭环的必要前置 —— 这正是一条可执行的运维规则：**接入新游戏后先跑 `kb_seed`。**

## 4. 闭环五段与对应落点

| 环节 | 实现 | 验收 |
|---|---|---|
| 学 | `seed_knowledge(game)` 按档案 `combat.tactics` / `predictor` 档位生成 `tactics.md`、`boss_guide.md` | 幂等（不覆盖复盘积累），`force=True` 可强制刷新 |
| 检索 | `retrieve(game, keyword)`，限定 `knowledge_md/<game>/` | 别的游戏的独门口诀**不命中**（用例锁定） |
| 决策 | `extract_tactics` → `apply_tactics` → `_fallback_decide` | 同一状态、有/无知识**动作必须不同** |
| 复盘 | `review_round` → `kb_write`（带 game_name） | 用例断言笔记落盘 |
| 回写 | 下一轮 `retrieve` | 用例断言第二轮能检索到第一轮写的内容 |

主循环开局自动补种 seed（幂等，不覆盖已有文档），退出前落盘指标。

## 5. 新增能力

- `knowledge_loop.py`：`seed_knowledge` / `retrieve` / `extract_tactics` / `apply_tactics` /
  `decide_with_knowledge` / `LearningStats` / `save` / `query_stats` / `stats_summary`
- CLI：`kb_seed [游戏]`（补种 seed）、`kb_stats [游戏]`（查询检索/命中/引用 + 按关键词下钻）
- `agent_cli.py` 帮助清单同步，保证「帮助清单 ⊆ 命令表」

## 6. 验收记录

```
$ python -m pytest tests/test_knowledge_loop.py -q      32 passed
$ python -m pytest tests/ -q                            835 passed in 110s
$ UGF_DRY_RUN=1 python agent_main.py --rounds 14
  [知识] 已补种 2 份 seed 知识到 knowledge_md/florr/
  [汇总] 回合=14 | 死亡=0 | 跳过帧=0 | 换套=1 | 动作=defendx14
  [知识] 闭环指标已落盘: run_logs/learning_stats.json ｜
         [florr] 检索 14 次 / 命中 14 次 (命中率 100%) / 引用 14 次 (引用率 100%)
```

## 7. 遗留与风险

1. **知识优先级过硬**（实测暴露）：14 轮动作全部是 `defend`。florr 档案的战术含"撤退/保持距离"，
   而 `apply_tactics` 对 `cautious_fight` 一律降级为防守，覆盖了战斗评估的 `fight` 判断。
   需要在 S20 决策场景矩阵里引入权重（例如仅在低血量/高威胁比时生效），否则空场也会一直防守。
2. **引用率 100% 偏乐观**：当前定义是"命中即引用"。更严格的口径应是"该条知识改变了动作"，
   需要对照组才能算出增量，S20 补。
3. seed 只覆盖两个检索词（"战术" / "boss"），与主循环一致；主循环若新增检索词，
   `build_seed_docs` 需同步（已由用例 `test_retrieve_keywords_cover_main_loop` 兜底）。
4. `knowledge_md/nope/`、`knowledge_md/template/` 为历史测试残留，未清理（不属本阶段范围）。

## 8. 经验

1. **分区要读写成对修**。S15 只修了写入，读取漏了，于是出现"分区已生效"的假象 —— 凡是
   存储分片的改造，必须同时验证读路径，否则分片等于只对写入有效。
2. **降级路径不是"不重要路径"**。无 key 环境里兜底决策才是主力路径，知识闭环断在这里就等于
   整体断裂。评估覆盖度时要按"实际会走哪条"而不是"主路径写了什么"来判断。
3. **命中率要区分"真命中"与"命中了不该命中的"**。修复前 87 个命中文件是噪声，修复后 13 个
   才是信号；指标设计必须绑定语义边界，否则数字越大越危险。
