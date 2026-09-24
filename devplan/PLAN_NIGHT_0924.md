# 今晚窗口计划（2026-09-23 23:40 ~ 2026-09-24 07:00，30 分钟一格）

> 前置：用户要求「拟定计划交给定时任务，半小时一次，现在开始」。
> 现状：`automation_update` 调度工具**不在当前会话工具集**（已两次确认），无法真正创建定时任务。
> 因此：本文件即执行表（每格开工第一步读本表 + `devplan/DIRECTION.md`），由我按 30 分钟节奏人工推进；
> 工具一旦恢复，按文末「铺开规格」照抄即可，无需重新设计。
>
> 大背景：定位已是「装到别的 Agent 上的 MCP 能力包」，上一轮「大改」已作废，
> 结构拆分回滚，只保留改名（→ Universal-Game-Framework）与 pyproject/三个命令行入口。

## 通用约束（每格都要遵守）

- Python：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`（pip 同目录 `bin/pip`），禁止全局 pip。
- 命令前置 `TMPDIR=/home/g-bill/.workbuddy/tmp`（`/tmp` 只有 10M）。
- 推 GitHub 必须绕代理：`env -u http_proxy -u https_proxy -u HTTPS_PROXY git push ...`。
- 无 GUI / 无 X server：键鼠只能 dry-run 验证。
- 每格结束：跑相关测试 → `git commit` → 更新 `devplan/PROGRESS.md` 与本表进度。
- 不提问，直接做；做完给出一两条硬数据（测试数、耗时、体积）。

## 执行表

| # | 时间 | 任务 | 验收 |
|---|---|---|---|
| S1 | 23:40 | 发布 GitHub Release `v2.1.0-mcp`（notes 取自 CHANGELOG）+ 仓库 About/topics 更新 | Release 页面可访问；topics 含 mcp / game-ai |
| S2 | 00:10 | README 徽章与全部链接改成新仓库名，检查死链 | 全文无 `FlorrVLM`；链接 200 |
| S3 | 00:40 | 新增 `SECURITY.md`（被外部 Agent 调用的安全边界：dry-run / 路径 / HTTP 鉴权） | README 与 MCP_INSTALL 互引 |
| S4 | 01:10 | 新增 GitHub Actions CI（pytest + `check.sh --fast`） | workflow 语法正确，本地可 dry 校验 |
| S5 | 01:40 | 构建产物验证：`python -m build` 出 sdist/wheel，确认 py-modules 齐全 | 装 wheel 到干净 venv 能 `ugf-mcp --version` |
| S6 | 02:10 | 工具错误文案统一 + 空结果给「下一步」引导 | 新增测试锁死 |
| S7 | 02:40 | MCP 契约再加固：客户端视角 initialize → tools/list → tools/call 三连测试 | 测试全绿 |
| S8 | 03:10 | 冷启动耗时测量与优化（懒加载重依赖） | 冷启动 ≤ 基准，记录前后耗时 |
| S9 | 03:40 | 文档对拍：MCP_INSTALL / EXAMPLES / FAQ 与实际返回逐条核对 | 不一致处修正并 commit |
| S10 | 04:10 | CHANGELOG 补全（改名 + 打包 + 三个入口）+ PROGRESS 归档 | 文档测试全绿 |
| S11 | 04:40 | 备份与体积：`kb_export` 往返验证、检查仓库大文件、`.gitignore` 复核 | 仓库无新增大文件 |
| S12 | 05:10 | 新机器模拟：干净 venv 跑完整门禁 7 环节 | 全过 |
| S13 | 05:40 | 全量测试 + `mcp_tools_check --strict` | 全绿，工具 16/16 |
| S14 | 06:10 | Obsidian 归档 + 结项报告更新 | 笔记已建 |
| S15 | 06:40 | 最终汇报：做了什么 / 遗留风险 / 下一步建议 | 报告落 `devplan/` |

## 铺开规格（工具恢复后照抄）

- 23:xx 的格子用 `scheduleType=once`（规避 `validFrom` 23 点被顺延到次日 00:00 的已知问题）；
  00:00 之后可用两条 `FREQ=HOURLY;INTERVAL=1` 线（整点线 / 半点线）错峰，或继续用 once。
- 每条 `validUntil=2026-09-24T07:00`；一条任务 = 表格里的一格，不搞「读计划自己挑」的复读机。
- prompt = 本表对应任务 + 通用约束 + 「开工先读 devplan/PLAN_NIGHT_0924.md 与 devplan/DIRECTION.md」。

## 进度

- 23:35 计划落盘；工具不可用，转人工按格执行。
