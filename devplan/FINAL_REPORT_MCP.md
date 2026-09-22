# 结项报告 · M 阶段（定位变更为 MCP 能力包）

> 时间：2026-09-22 23:20 ~ 2026-09-23 00:05
> 依据：`devplan/PLAN_MCP.md`（M1~M10）
> 结论：**M1~M9 全部完成**，M10（发布）完成到 tag 与本报告；全量测试绿。

## 一、做了什么

定位从「一个会自己玩游戏的 Agent」改为「**装到别的 Agent 上的 MCP 能力包**」。
这个转变带来一条新第一性原理：**工具即产品**——外部模型只看得到工具名 + 描述 + 入参，
描述写不清楚就等于功能不存在；自述文档 / CLI / 监控大盘降级为调试件。

| 阶段 | 交付 | 结果 |
|---|---|---|
| M1 定位与安装器 | README/PROJECT_SUMMARY/ROADMAP 定位改写；`tools/install_mcp.py`（workbuddy / opencode / claude-desktop / vscode / custom，`--list` / `--dry-run` / `--remove` / `--online`）；`docs/MCP_INSTALL.md`；契约测试 8 项 | ✅ |
| M2 工具描述 | 15 个工具描述重写为「做什么 / 入参 / 返回 / 下一步」；描述契约测试（长度 ≥80、必须写返回、不得泄漏内部路径） | ✅ |
| M3 内置手册 | 新增第 16 个工具 `ugf_guide` + 资源 `ugf://guide`；工具清单**运行时动态生成**，永不漂移；测试 6 项 | ✅ |
| M4 传输 | `--transport stdio / streamable-http / sse` + `--host --port`（默认 5050）；HTTP 传输一致性测试（16 工具 + 手册可调用） | ✅ |
| M5 版本化 | `VERSION = 2.1.0-mcp`，`--version` 与握手 `serverInfo` 均携带；CHANGELOG.md；文档一致性测试 6 项 | ✅ |
| M6 安全边界 | 越界/注入拒绝、dry-run 绝不碰真实键鼠（monkeypatch 断言）、错误返回可读文本不吐 traceback；测试 8 项 | ✅ |
| M7 无头冷启动 | 感知服务缺失时 16 个工具全部可调用、结果带 `_fallback`、不抛异常；测试 3 项 | ✅ |
| M8 示例 | `docs/MCP_EXAMPLES.md`：三段标准调用链（摸清局面 / 打一局 / 学一轮）+ 常见报错对照表 | ✅ |
| M9 文档重写 | README 首屏改为「装到你的 Agent 上」三分钟上手 + 传输对照表；CLI/大盘明确标注为调试件；ROADMAP 加 v2.1-mcp 行 | ✅ |
| M10 发布 | CHANGELOG + `v2.1.0-mcp` tag + 本报告 | ✅ |

## 二、测试与门禁

- 全量 `pytest tests/ -q`：**绿**（M 阶段新增 33 项测试）。
- `python tools/mcp_tools_check.py --strict`：PASS（README 表格 ↔ 运行时清单逐字一致）。
- `python tools/install_mcp.py --list / --dry-run`：可列目标、dry-run 不落盘。

## 三、遗留风险

1. **实机未验证**：本机无 GUI / 无 X server，键鼠动作只在 dry-run 与 mock 下验证过；
   真机接线需在有显示器的环境跑一次 `game_action` 与 `switch_set`。
2. **感知服务仍依赖外部 YOLO**：`perceive_game` 在没有感知服务时返回合成帧（`_fallback`），
   这保证联调可用，但不是真实识别结果，别把 mock 数据当战绩。
3. **`kb_write` 对 `..` 是「清洗后写回库内」而不是报错**：已验证不会越界，
   但调用方可能困惑于「我传的文件名被改了」——后续可考虑改为显式拒绝并提示。
4. **HTTP 传输未做鉴权**：streamable-http 监听在 127.0.0.1，若改为对外监听必须加令牌，
   否则任何能访问该端口的人都能驱动你的键鼠。
5. **定时任务未真正创建**：`automation_update` 工具在本会话不可用，规格已固化在
   `devplan/AUTOMATION_TASKS.md`，工具恢复后照抄即可铺开。

## 四、下一步建议

- 优先做「**新机器模拟**」：干净 venv 从零装一遍，记录卡点（原计划第 11 槽）。
- 其次补 FAQ（装不上 / 客户端看不见工具 / dry-run 疑问 / 合规）。
- 真机验收前，不要关闭 dry-run。
