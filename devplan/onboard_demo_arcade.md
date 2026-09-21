# 接入报告 · demo_arcade

> 由 `tools/onboard_game.py` 自动生成于 2026-09-22 04:22:39 ｜ 总耗时 16.45s ｜ ✅ 接入成功

## 一、结论

- 接入环节通过：4/4（跳过 0，不含最后的报告环节）
- 试跑轮数：2 ｜ 校验口径：strict（建议项也算问题）
- 档案：`game_profiles/demo_arcade.yaml`（已存在，复用）
- 接入方式：全程未修改核心代码，仅新增/复用一份 YAML 档案

## 二、环节明细

| # | 环节 | 结果 | 耗时(s) | 说明 |
|---|---|---|---|---|
| 1 | 生成档案 | ✅ | 0.0 | 档案已存在，直接复用: /home/g-bill/文档/Default Project/Universal-Game-Framework/game_profiles/demo_arcade.yaml |
| 2 | 档案校验 | ✅ | 0.02 | ERROR 0 / WARN 0（口径: strict） |
| 3 | 感知冒烟 | ✅ | 2.22 | 自检 2 帧，输出实体条目 4 个，退出码 0 |
| 4 | dry-run 试跑 | ✅ | 14.18 | 试跑 2 轮，退出码 0，知识库文件 4 个 |

## 三、档案摘要

| 字段 | 值 |
|---|---|
| `game.name` | demo_arcade |
| `game.description` | demo_arcade 游戏档案 |
| `server.perception_port` | 5021 |
| `combat.default_set` | combat |
| `combat.sets` | combat, tank, retreat, chase, team |
| `combat.tactics` | 3 |
| `predictor.threat.boss` | 400 |
| `perception.mock.entities` | 4 |

## 四、发现的问题

- 无。生成、校验、冒烟、试跑四个环节均未发现异常。

## 五、后续建议

- 链路已打通。下一步：在 mock 下多跑几轮观察决策分布，确认无误后再切真实感知后端（YOLO/HTTP）上真机。
- 若要把这款游戏设为默认，执行 `python tools/add_game.py demo_arcade` 或在 config.yaml 的 agent.game 手动切换。
- 上真机前请先确认目标环境的合规性：仅在本地/自建/已授权环境运行自动化程序。

---

复现命令：

```bash
python tools/onboard_game.py demo_arcade --rounds 2
```
