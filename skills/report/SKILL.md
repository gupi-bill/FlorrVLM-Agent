# 技能包：汇报(report)

description: 生成一段"当前进度与战况"汇报文字
entry: report_run

## 数据来源

| 字段 | 来源 |
|---|---|
| 游戏 / 会话状态 / 累计场次 / 已装技能 | `agent_state.json`（经 `session.load()`） |
| 回合 / 死亡 / HP / 决策 / 心态 / 套装 / 威胁 | `run_logs/agent_snapshot.json`（主循环每 N 轮写入） |

读不到任一来源时走降级分支，字段显示「未知 / 暂无」，并在末行标注离线，不抛异常。

## 用法

- `agent_cli`：`load report` → `run_skill report`
- 一次性执行：`python agent_cli.py -c "run_skill report"`
- 代码内：`SkillManager().call("report", game="florr", note="第 3 局")`

## 入口签名

```python
report_run(game: str = None, note: str = "", **kw) -> str
```

- `game` 为 `None` 时自动取快照/会话档案中的当前游戏。
- 返回多行纯文本（可直接进报告或推送 Webhook）。

## 示例输出

```
[skill:report] 当前游戏: florr
  会话状态 : playing
  累计场次 : 3
  最近回合 : 42
  累计死亡 : 1
  HP       : 78/100
  战斗决策 : cautious / 心态 steady / 套装 tank
  威胁预判 : 最高威胁 Super Hornet（威胁分 400）
  已装技能 : report
  （离线/dry-run：无 LLM/VLM 密钥，数值取自本地快照）
```

## 约束

- 严禁在本文件内调用真实 LLM / VLM / 网络接口；本技能必须能在离线环境跑通。
- 修改 `skill.py` 后可用 `SkillManager().reload("report")` 热重载。
