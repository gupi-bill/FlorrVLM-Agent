# 定位变更：从「一个 Agent」改为「装在其他 Agent 上的 MCP 能力包」

> 变更时间：2026-09-22 23:20 ｜ 依据：用户明确指令
> 影响：本表**取代** `PLAN_PHASE2.md` 中尚未执行的 S22~S26；S22~S26 暂缓。

## 定位（新的第一性原理）

**Universal-Game-Framework 不是 Agent，是给别的 Agent 装的游戏能力 MCP 服务。**

消费方是**别的 LLM**（Kilo / Codex / OpenCode / WorkBuddy / Claude Desktop …），它们通过 MCP 调用本项目的 15 个工具来获得「看画面、预判、评估战力、出动作、查知识库、写复盘」的能力。

由此推出三条硬准则：

1. **工具即产品**：外部模型只看得到工具名 + 描述 + 入参 schema。描述写不清楚 = 功能不存在。自述文档、CLI、监控大盘都是**附属调试件**，不是门面。
2. **装上就能用**：从"拿到仓库"到"在任意客户端里能调用"必须 ≤ 3 步，且失败要有可读原因。
3. **无状态、可并发**：服务可以被多个客户端同时拉起，不能依赖某个终端、某个 UI、某个交互会话。

---

## 阶段清单（M1 ~ M10）

### M1 · 定位改写与一键安装器
- 目标：让"装到别的 Agent 上"变成一条命令。
- 任务：README / PROJECT_SUMMARY 顶部定位改写（不自称 Agent）；新增 `docs/MCP_INSTALL.md`（概念 + 各客户端配置样例 + 验证步骤 + 工具清单与调用示例）；新增 `tools/install_mcp.py`（支持 workbuddy / opencode / kilo / codex / claude-desktop / 自定义路径，支持 `--list` / `--dry-run` / `--remove`）。
- 交付物：`docs/MCP_INSTALL.md`、`tools/install_mcp.py`、`tests/test_install_mcp.py`、文档改写。
- 验收：`python tools/install_mcp.py --list` 列出可写入目标；`--dry-run` 不落盘且输出将要写入的 JSON；测试用例全绿。

### M2 · 工具描述"外部模型可读"改造
- 目标：把 15 个工具的 docstring 从"给自己看的注释"改成"给陌生 LLM 看的使用说明"。
- 任务：每个工具描述统一四段：**做什么 / 什么时候用 / 返回什么（含结构）/ 下一步该调什么**；入参补类型与取值约束；补 3~5 个跨工具调用链示例。
- 交付物：`mcp_server.py` 15 处描述改写、`tests/test_mcp_descriptions.py`（断言每个工具描述 ≥ 阈值长度、含"返回"字样、无内部绝对路径泄漏）。
- 验收：测试全绿；用 `tools/mcp_tools_check.py --strict` 复核清单一致。

### M3 · 内置使用手册（让外部 Agent 一次性学会）
- 目标：外部模型不需要读仓库 README 也能上手。
- 任务：新增 MCP 资源 `ugf://guide`（或工具 `ugf_guide`），返回精简版使用手册：能力边界、推荐调用顺序、参数含义、dry-run 说明、常见错误。
- 交付物：资源/工具实现 + `tests/test_mcp_guide.py`。
- 验收：调用返回结构化手册，含全部 15 个工具名与推荐调用链。

### M4 · 传输与并发
- 目标：stdio 之外支持 HTTP，且多客户端可并发。
- 任务：打通 `mcp.streamable_http`（默认 5050），校验 stdio / http 两种传输的工具清单一致；验证两个客户端并发调用互不干扰（知识库写入加锁或幂等）。
- 交付物：`mcp_server.py` 传输分支、`devplan/MCP_TRANSPORT.md`、并发测试。
- 验收：两种传输工具清单一致（15/15）；并发写知识库无损坏。

### M5 · 安装契约与版本化
- 目标：别人升级/回滚不出意外。
- 任务：`mcp_server.py` 输出版本号与能力清单；工具清单变更需同步 `docs/MCP_INSTALL.md` 与 README（用测试锁死）；`--version`。
- 交付物：版本常量、一致性测试。
- 验收：改动任一工具名而未同步文档时，测试失败。

### M6 · 安全边界（面向"被别的 Agent 调用"）
- 目标：被外部模型调用时不能越界。
- 任务：知识库读写继续限制在项目目录内；禁止通过工具参数触发任意命令/路径；`game_action` 在 dry-run 下必须拒绝真实键鼠；所有错误返回可读文本而非 traceback。
- 交付物：`tests/test_mcp_security.py`、必要加固。
- 验收：越界/注入类用例全部被拒且返回可读错误。

### M7 · 无头与冷启动体验
- 目标：客户端拉起即用，不需要人先开感知服务。
- 任务：感知服务不可用时自动降级到进程内 mock（已部分实现），并在返回里明确标注 `_fallback`；冷启动自愈说明写入返回文本。
- 交付物：降级路径测试、`docs/MCP_INSTALL.md` 补充说明。
- 验收：无感知服务时 15 个工具仍可调用且不抛异常。

### M8 · 示例与模板调用链
- 目标：给外部 Agent 可抄的"套路"。
- 任务：提供 3 段标准调用链（新手上手 / 打一局 / 复盘学习），写成 JSON 示例放 `docs/MCP_EXAMPLES.md`，并让 M3 的手册引用。
- 交付物：`docs/MCP_EXAMPLES.md` + 手册引用 + 示例可执行性测试。
- 验收：示例里的每一步工具名与参数都在实际工具 schema 中存在（测试校验）。

### M9 · 文档体系按新定位重写
- 目标：README 第一屏就说清"这是装到别的 Agent 上的 MCP"。
- 任务：README 重写（定位 → 三分钟装上 → 工具表 → 调用链 → 自己的 CLI/大盘作为调试件 → 合规 → 已知限制）；PROJECT_SUMMARY / ROADMAP 同步。
- 交付物：三份文档 + 文档一致性测试更新。
- 验收：`tests/test_docs.py` 全绿，且 README 首屏不含"本 Agent 会自己玩游戏"类表述。

### M10 · 发布与归档
- 目标：一个可对外分发的能力包。
- 任务：CHANGELOG、版本号统一、`v2.1.0-mcp` tag、结项报告写入 `devplan/FINAL_REPORT_MCP.md` 与 Obsidian。
- 交付物：CHANGELOG / tag / 报告。
- 验收：`install_mcp.py` 对全新目标 dry-run 输出完整配置；报告含工具清单与遗留风险。

---

## 执行约定

- 每周期从第一个未完成阶段开始，完成后若时间预算（25 分钟）仍有剩余则继续下一阶段。
- 每阶段结束更新 `devplan/PROGRESS.md`（新增「M 阶段」分区）并 `git commit`。
- 硬约束同 `PLAN.md`（隔离 venv、`TMPDIR=/home/g-bill/.workbuddy/tmp`、磁盘上限、离线 mock、不提问）。
- 方向判断以 `devplan/DIRECTION.md` + 本表为准。
