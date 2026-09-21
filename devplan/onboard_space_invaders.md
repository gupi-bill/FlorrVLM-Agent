# 接入报告 · space_invaders

> 由 `tools/onboard_game.py` 自动生成于 2026-09-22 04:19:54 ｜ 总耗时 15.82s ｜ ✅ 接入成功

## 一、结论

- 接入环节通过：4/4（跳过 0，不含最后的报告环节）
- 试跑轮数：2 ｜ 校验口径：strict（建议项也算问题）
- 档案：`game_profiles/space_invaders.yaml`（已存在，复用）
- 接入方式：全程未修改核心代码，仅新增/复用一份 YAML 档案

## 二、环节明细

| # | 环节 | 结果 | 耗时(s) | 说明 |
|---|---|---|---|---|
| 1 | 生成档案 | ✅ | 0.0 | 档案已存在，直接复用: /home/g-bill/文档/Default Project/Universal-Game-Framework/game_profiles/space_invaders.yaml |
| 2 | 档案校验 | ✅ | 0.02 | ERROR 0 / WARN 0（口径: strict） |
| 3 | 感知冒烟 | ✅ | 2.15 | 自检 2 帧，输出实体条目 6 个，退出码 0 |
| 4 | dry-run 试跑 | ✅ | 13.62 | 试跑 2 轮，退出码 0，知识库文件 13 个 |

## 三、档案摘要

| 字段 | 值 |
|---|---|
| `game.name` | space_invaders |
| `game.description` | 经典街机射击，控制光子炮台消灭层层下压的外星人编队，母舰出现时高分高威胁。 |
| `server.perception_port` | 5011 |
| `combat.default_set` | shoot |
| `combat.sets` | shoot, dodge, focus_mothership |
| `combat.tactics` | 4 |
| `predictor.threat.boss` | 800 |
| `perception.mock.entities` | 6 |

## 四、发现的问题

- 无。生成、校验、冒烟、试跑四个环节均未发现异常。

## 五、后续建议

- 链路已打通。下一步：在 mock 下多跑几轮观察决策分布，确认无误后再切真实感知后端（YOLO/HTTP）上真机。
- 若要把这款游戏设为默认，执行 `python tools/add_game.py space_invaders` 或在 config.yaml 的 agent.game 手动切换。
- 上真机前请先确认目标环境的合规性：仅在本地/自建/已授权环境运行自动化程序。

---

复现命令：

```bash
python tools/onboard_game.py space_invaders --rounds 2
```
