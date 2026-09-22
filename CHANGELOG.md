# 更新日志

## v2.1.0-mcp（2026-09-22）—— 定位变更：从「一个 Agent」变成「装到别的 Agent 上的 MCP 能力包」

**定位**
- 项目不再自称 Agent，而是给任意支持 MCP 的客户端提供游戏能力的**服务端**。
- 新增一键安装器 `tools/install_mcp.py`，支持 WorkBuddy / OpenCode / Claude Desktop / VS Code / 自定义路径，`--dry-run` / `--remove` / `--online`。
- 新增 `docs/MCP_INSTALL.md`（接入指南）、`docs/MCP_EXAMPLES.md`（可照抄的调用链）。

**工具**
- 15 个工具的说明全部重写为「外部模型可读」格式：做什么 / 入参 / 返回 / 下一步。
- 新增第 16 个工具 `ugf_guide`：返回内置使用手册（工具清单由运行时动态生成，永不漂移），
  同时以资源 `ugf://guide` 暴露。
- `--version` 输出版本，握手返回的 `serverInfo.version` 亦携带版本。

**传输**
- 除 stdio 外支持 `streamable-http`（`--transport streamable-http --host --port`，默认端口 5050），
  便于多客户端同时接入；两种传输的工具清单一致，由测试锁死。

## v2.0 —— 通用游戏流水线（detect → research → ensure → play → report）

- 全实体运动预判 `predictor.py`（威胁排序 + 置信度，低置信不输出坐标）。
- MD 知识库读写检索 + 归档 + 导出导入。
- 多游戏档案 `game_profiles/`，稀有度体系，战役框架。
- 离线 dry-run：无 GUI / 无感知服务时全链路可跑通（结果带 `_fallback` 标记）。
- 934 项自动化测试。
