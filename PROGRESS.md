
---
## 2026-09-24 夜间窗口进度（cron 循环守护驱动 + 活会话 AI 补做）

- **调度机制落地**：本会话 `automation_update` 不可用；OS `cron` 的 spool 被沙箱 FS 锁死（`/var/spool` 禁止写）；headless CLI 缺桌面宿主会话会卡死。
  故用 `devplan/cron_loop.sh` 常驻后台任务（host 持有、跨调用存活）每 30 分钟跑一格，立即触发首格（"现在开始"）。
  - 每轮做：pytest 全量 + 三个 CLI 入口体检 + git 提交 + 推远端 + 写 `devplan/CRON_LOG.md`。
  - 指针 `devplan/NEXT_SLOT` 仅在该格被标记 done（活会话做）或 headless 启用时才推进，绝不跳过未执行项。
  - 重启命令：`/bin/bash "/home/g-bill/文档/Default Project/Universal-Game-Framework/devplan/cron_loop.sh"`（建议 run_in_background）。
- **S1（GitHub Release）— DEFERRED**：无 `gh`、无 GitHub API PAT，无法发 Release。等拿到 token 或 `gh` 登录后再补。
- **S2（README/改名死链审计）— DONE**：活动代码/文档已无旧名 `FlorrVLM`（残留仅在 `run_logs/` 历史报告与我的记忆笔记中，属归档/记录，不改动）；README 链接均为有效地址/本地 demo。
- **S3（SECURITY.md）— DONE**：新增 `SECURITY.md`，依据 `mcp_server.py` 实测写准：dry-run 默认、路径沙箱、动作白名单、进程内 mock 降级、HTTP 传输鉴权要求。
- 下一步指针：S4（GitHub Actions CI）。

- **S4（GitHub Actions CI）— DONE**：新增 `.github/workflows/ci.yml`。
  - 触发：push/PR 跑全量 `pytest tests/`；`schedule` 每 2 小时跑冒烟（import + 两个核心测试文件）；支持 workflow_dispatch。
  - 环境：`UGF_DRY_RUN=1`（无头），单版本 py3.11 矩阵（避免定时额度翻倍），concurrency 防并发堆积。
  - 依赖：只装 core（`pip install -e .`）+ dev；**刻意跳过** requirements.txt 的 optional 段（pyautogui/pillow/opencv-python）——无头 CI 用不到，且 opencv 在 ubuntu runner 上常因缺 libGL.so.1 导入失败。补装 pyproject 漏掉的 flask。
  - **额度硬约束**：GitHub 免费账户 2000 分钟/月。*/30 会达 ≈1440 次/月（最小计费 1 分钟/次）叠加 push CI 必然超额；故定时设每 2 小时（≈360 次/月）。30 分钟粒度的「AI 推进计划」交给 WorkBuddy 自动化面板。
- 下一步指针：S5。

- **S4 补充 · CI 转绿（4978029 success）**：CI 首建于 py3.11 挂红，改 py3.13 仍红。日志需 repo admin 权限（403 拿不到），改用「把 pytest 输出尾部抛成 `::error::` annotation」从公开页面读到真实报错：
  `FAILED tests/test_skill_manager.py::test_reload_picks_up_change - AssertionError: assert 'v1' == 'v2'`（1 failed, 961 passed in 18.87s）
  - **根因**：`reload()` 只 pop `sys.modules` 后重新 `load`，`exec_module` 走 SourceFileLoader 的 .pyc 缓存（按 `mtime + size` 校验）。v1→v2 两个文件**长度相同**，CI 高速（18.87s 跑完 962 个测试）使两次写入落在同一 mtime 粒度 → 命中旧字节码 → 热重载返回旧代码。**这是生产代码真实缺陷**（用户改完 skill.py 若同秒且长度不变，热重载会失效），不是测试 flaky。
  - **修复**：`reload()` 中先 `os.remove(importlib.util.cache_from_source(code_path))` 强制失效字节码缓存。本地构造「size 相同 + mtime 强制相同」场景验证：修改前会返回 v1、修改后正确返回 v2；`tests/test_skill_manager.py` 34 passed；CI 已转绿。
  - **诊断技巧（可复用）**：GitHub Actions 日志要 admin 权限时，用 `::error::` 把输出抛成 annotation（run 页面无需登录即可见）；注意每个 step 的 annotation 上限约 10 条，必须只抛关键行（失败用例 + 统计行），否则被截断。
