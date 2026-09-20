# S7 · 主循环 dry-run 冒烟记录

> 执行时间：2026-09-21 05:11 ~ 05:34（B 线 / 整点错峰副本）
> 运行环境：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`
> 硬约束：无 `.env`（无 LLM 密钥）、无 X server、无 YOLO、无感知服务常驻、`/tmp` 仅 10M

---

## 1. 目标与验收

让 `detect → predict → judge → decide → act → report` 全链路在**完全离线**下跑 N 轮不崩，
且退出码 0、产出状态文件与日志。

**验收命令**（PLAN.md S7 定义）：

```bash
UGF_DRY_RUN=1 python agent_main.py --rounds 5
```

实测结果：**exit 0**，5 轮全部走完，产出 `run_logs/agent_snapshot.json`、
`run_logs/dryrun_actions.log`、`run_logs/progress_report.md`、`run_logs/agent_YYYYMMDD.log`，
知识库写入 `boss_behavior_log.md` / `player_tactics.md` / `review_*.md`。

---

## 2. dry-run 开关语义

`UGF_DRY_RUN=1`（取值 `1/true/yes/on`）时：

| 环节 | 正常模式 | dry-run 模式 |
|---|---|---|
| 感知 | 请求 `http://127.0.0.1:<port>/perceive` | 请求失败则**进程内直接合成一帧 mock**，结果带 `_fallback: inproc-mock` |
| 键鼠动作 `game_action` | `pyautogui` 真实输入 | 只记录，返回 `[dry-run] 动作已记录（未真实执行）` |
| 套装切换 `switch_set` | 按数字键 | 只记录，返回 `[dry-run] 套装切换已记录` |
| LLM 决策 | 调外部 API | 无密钥时本来就走 `_fallback_decide` 规则决策（不变） |
| 落盘 | 同左 | 额外写 `run_logs/dryrun_actions.log`（时间 / 类型 / 明细） |

开关透传：MCP stdio 客户端只向子进程转发 `HOME/PATH/SHELL/TERM/USER/LOGNAME` 六个白名单变量，
`UGF_*` 一律丢弃。S7 新增 `_mcp_server_env()` 显式透传全部 `UGF_*`，
否则会出现「父进程开了 dry-run、子进程没收到」的假象。

**测试用环境变量**（仅在本轮验证中使用，不改变仓库配置）：

- `UGF_REPORT_EVERY=N` —— 覆盖 `agent.report_every`，验证局中汇报心跳
- `UGF_LEARN_EVERY=N` —— 覆盖 `agent.learning_stats_interval`，验证命中率汇总与自动调参

---

## 3. 本轮修复的缺陷（7 项）

| 编号 | 严重度 | 位置 | 问题 | 修复 |
|---|---|---|---|---|
| **A1** | 阻断 | `mcp_server.py` | `kb_append` 从未被 `@mcp.tool()` 注册，但 `agent_main` 的 BOSS 记忆 / 战术记忆 / 学习汇总三处都在调它。`call_tool` 不抛异常、只把错误塞进返回内容，导致**日志说「已写入 N 条」、实际一个字节都没写** | 补 `@mcp.tool()`；`agent_main` 侧新增 `_tool_error()` 软失败检测，写失败改为显式报错 |
| **A2** | 阻断 | `mcp_server.py` | 启动 banner 与知识库模板提示 `print` 到 **stdout**，而 stdio 传输把 stdout 当 JSON-RPC 通道，客户端每帧解析报 `ValidationError` | 新增 `_stderr()`，全部改走 stderr |
| **A3** | 高 | `perception_server.py` | mock 实体位移用「上一帧到这一帧」的增量 `dt`，位置恒等于 `start + v×帧间隔`，**实体原地不动** → predictor 算出速度恒为 0 → 预判置信度永远上不去（dry-run 实测：5 帧 `x_now` 完全相同） | 改为累计时间基准 `t0`（`_MOCK_STATE`），实体按真实速度持续往返；`reset_mock()` 一并清 `t0` |
| **A4** | 中 | `agent_main.py` | 回合计数先自增再判定，达到上限时日志/汇总多报 1 轮（`--rounds 5` 显示「回合=6」） | 改为先判定再自增 |
| **A5** | 中 | `agent_main.py` | 监控快照按 `x/y/name` 取预判字段，而 predictor 输出的是 `x_now/y_now/raw_id`，大盘上威胁坐标恒为 `(0,0)`、名字恒为空 | 改为 `x_now`/`y_now`/`raw_id` 优先、旧键兜底 |
| **A6** | 中 | `agent_main.py` | 感知跳过/异常只打印「跳过本帧」，看不到 `_reason`/`_error`（S6 遗留项） | 新增 `_json_fields()`，把原因打进日志；新增跳过帧计数 |
| **A7** | 中 | `agent_main.py` | MCP 返回解析直接下标 `result.content[0].text`，不同 SDK 形状或空 content 时抛异常打断主循环 | 新增 `_tool_text()` 统一兜底；退出前 BOSS 记忆与复盘包 try/except，保证退出码 0 |

附带修正：模块 docstring 中「连续 2 帧判定死亡」与配置 `agent.death_frame_threshold: 8` 不符，改为指向配置。

---

## 4. 实测输出样例

```
$ UGF_DRY_RUN=1 UGF_REPORT_EVERY=2 python agent_main.py --rounds 5
[dry-run] 已开启：不做真实键鼠动作、不调用外部 LLM、感知缺失时走进程内 mock
[05:19:24]   Universal-Game-Framework 启动 (MCP Client + 预判 + 战斗评估)
[05:19:24]   模式: DRY-RUN —— 无真实键鼠 / 无外部 LLM / 感知走进程内 mock
[05:19:29] [MCP] 已连接，可用工具: [ ... 15 个，含 kb_append ... ]
[05:19:30] [套装] combat → retreat，已记入 player_tactics.md
[05:19:30] [记忆] 已写入 1 条 BOSS 行为观察
[05:19:30] [回合 1] HP=100.0 敌人=5 队友=1 决策=retreat 套装=retreat 心态=conservative → defend
[05:19:30] [汇报] 局中进度(回合 2, 死亡 0): 进度已更新: .../run_logs/progress_report.md
...
[05:19:32] [汇总] 回合=5 | 死亡=0 | 跳过帧=0 | 换套=1 | 动作=defendx5
[05:19:33] [Agent] 已断开 MCP 连接
exit 0
```

修复 A3 后的实体漂移（`agent_snapshot.json`）：

```json
{"cat":"normal","name":"hornet","threat":15,"x":622.7,"y":300.0}
{"cat":"elite","name":"beetle","threat":120,"x":1416.5,"y":266.5}
```

`run_logs/dryrun_actions.log`：

```
2026-09-21 05:19:30	perceive	inproc-mock entities=5
2026-09-21 05:19:30	switch_set	retreat (按键 3)
2026-09-21 05:19:30	action	defend
```

---

## 5. 验证矩阵

| # | 场景 | 命令 / 方法 | 结果 |
|---|---|---|---|
| 1 | 验收命令 | `UGF_DRY_RUN=1 python agent_main.py --rounds 5` | ✅ exit 0，5 轮，产物齐全 |
| 2 | 参数别名 | `--rounds`（等价 `--max-rounds`） | ✅ |
| 3 | 感知降级 | 无感知服务时 `perceive_game` | ✅ 返回 `_fallback=inproc-mock` + 5 实体 |
| 4 | 非 dry-run 对照 | 无感知服务且不开开关 | ✅ 返回 `{"error":"感知服务未启动..."}`，不伪装成空场景 |
| 5 | 键鼠隔离 | dry-run 下 `game_action` / `switch_set` | ✅ 无 pyautogui 调用，仅落盘记录 |
| 6 | 汇报心跳 | `UGF_REPORT_EVERY=4` 跑 14 轮 | ✅ 回合 4/8/12 各上报一次，写 `progress_report.md` |
| 7 | 命中率 + 自动调参 | `UGF_LEARN_EVERY=6` 跑 14 轮 | ✅ 回合 6/12 汇总，写 `learning_stats.md`；`auto_tuner.tune` 返回「无需调整」 |
| 8 | BOSS 记忆 | 每轮收集 + 退出前 flush | ✅ `boss_behavior_log.md` 含轨迹与行为归纳 |
| 9 | 死亡分支 | 临时把 `perception.mock.player.alive` 置 false 跑 10 轮（阈值 8） | ✅ 第 8 轮判定死亡、写复盘「结果=死亡」、`total_deaths=1`、exit 0；配置已还原 |
| 10 | 热加载 | 运行中 `touch config.yaml` | ✅ 打印「config.yaml 已变更，热加载完成」 |
| 11 | 日志滚动 / 清理 | 单测 `_maybe_rotate` / `_log_cleanup` | ✅ 超限压缩为 `.gz`、超期 `agent_*.log` 被删 |
| 12 | 工具注册回归锁 | `mcp.list_tools()` | ✅ 15 个工具，主循环依赖的 9 个全部在列 |
| 13 | 全量测试 | `python -m pytest tests/ -q` | ✅ **457 passed**（S7 新增 87） |

---

## 6. 遗留（未在本轮处理）

1. **`auto` 后端在无头机上的语义**：本机有 ImageMagick `import`，`auto` 之所以落到 mock 靠的是「无 YOLO 检测脚本」。
   若将来放入检测脚本，`auto` 会切 http 并在无 X server 时每帧 `screenshot_failed`。
   **dry-run 与后续离线演示仍应显式设 `UGF_DRY_RUN=1`**（感知走进程内 mock，不受此影响）。
2. **`_fallback_decide` 不会移动**：无 LLM 时只输出 `attack`/`defend`/`idle`，`move` 分支（含安全区钳制与抖动）在 dry-run 中未被覆盖。
   真实策略需 LLM 或更完整的规则决策器，建议 **S13** 前补一个规则化 move 策略。
3. **`kb_search` 的 `_text_search`** 在 `return` 之后还有 3 行不可达代码（`if not results: ...`）。
   行为无影响（空结果已正确返回「未找到相关内容」），待 **S13** 清理。
4. **死亡防抖阈值 8 帧** 与 README 描述的「2 帧」不符，文档侧统一移交 **S13**。
5. `review_*.md` 与 `learning_stats.md` 会随每次 dry-run 累积在 `knowledge_md/`（已被 `.gitignore` 忽略），
   长跑场景建议由 **S12** 的运维脚本按保留期清理。
