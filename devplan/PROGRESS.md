# 冲刺执行进度（自动机填写）

> 计划：`devplan/PLAN.md` ｜ 周期：每 30 分钟一个阶段 ｜ 停止时间：当日 07:00
> 运行环境：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`

## 阶段状态总表

| 阶段 | 名称 | 状态 | 周期 | 主要产物 |
|---|---|---|---|---|
| S0 | 前置：核心文件恢复 + venv | ✅ 完成 | 手动 | 17 个文件从 git HEAD 恢复；隔离 venv |
| S1 | 仓库基线修复与卫生清理 | ⬜ 待执行 | | |
| S2 | 静态依赖与接口审计 | ⬜ 待执行 | | |
| S3 | 预判引擎实测定型 | ⬜ 待执行 | | |
| S4 | 战斗评估与自动调参校验 | ⬜ 待执行 | | |
| S5 | 会话/汇报/技能模块校验 | ⬜ 待执行 | | |
| S6 | 感知服务离线化 | ⬜ 待执行 | | |
| S7 | 主循环 dry-run | ⬜ 待执行 | | |
| S8 | CLI 全命令冒烟 | ⬜ 待执行 | | |
| S9 | MCP 工具注册验证 | ⬜ 待执行 | | |
| S10 | 游戏档案体系固化 | ⬜ 待执行 | | |
| S11 | UI 收敛与统一启动器 | ⬜ 待执行 | | |
| S12 | 运维脚本与容器一致性 | ⬜ 待执行 | | |
| S13 | 测试套件固化与文档同步 | ⬜ 待执行 | | |
| S14 | 最终验收与归档 | ⬜ 待执行 | | |

图例：⬜ 待执行 ｜ 🟡 进行中 ｜ ✅ 完成 ｜ ⛔ 阻塞

---

## S0 · 前置恢复（已由人工启动完成）

- 从 git HEAD 恢复缺失文件 17 个：`perception_server.py` `predictor.py` `report_notifier.py` `session.py` `skill_manager.py` `video_learner.py` `video_sources.py` `requirements.txt` `start_all.sh` `stop_all.sh` `watchdog.sh` `tools/add_game.py` `tools/build_dist.py` `skills/report/SKILL.md` `skills/report/skill.py` `packaging/build_windows.bat` `packaging/buildozer.spec`
- `git reset` 重建被清空的索引，`git status` 语义恢复正常
- `compileall` 全量语法检查通过
- 创建隔离虚拟环境 `/home/g-bill/.workbuddy/binaries/python/envs/ugf`，安装 pyyaml/requests/psutil/mcp/flask/python-dotenv/pytest

### ⚠️ 环境硬约束（后续所有周期必读）
- 根分区仅剩约 2.3G（96%）→ **禁止安装 opencv/torch/buildozer 等重量级包**；图像处理一律用 mock 数据绕过。
- **`/tmp` 是 10M tmpfs** → pip / 构建命令必须前置 `TMPDIR=/home/g-bill/.workbuddy/tmp`，否则 `OSError: [Errno 28]`。
- `.git/objects` pack 已 130MB，勿跑 `git gc --aggressive`。

### 遗留
- `.env` 不存在（无 LLM/VLM 密钥），所有链路走离线/mock。
- `packaging/androidapp/.buildozer` 大二进制待 S1 清理。

---

## 调度说明

本次冲刺由两条错峰自动化线驱动，共同实现「每 30 分钟推进一个阶段」：

- **A 线（整点）**：01:00 / 02:00 / 03:00 / 04:00 / 05:00 / 06:00
- **B 线（半点）**：00:30 / 01:30 / 02:30 / 03:30 / 04:30 / 05:30 / 06:30

两条线共用本文件判定「下一个待执行阶段」；各自限制单轮 25~30 分钟内完成，07:00 后自动停止（`validUntil`）。
调度器不支持逗号形式的 `BYMINUTE`，故采用双线错峰实现 30 分钟周期。

---

## 执行日志

（每个周期结束后在下方追加，格式：时间 · 阶段 · 做了什么 · 产物 · 测试结果 · 遗留）
