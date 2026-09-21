# UGF v2.0 冲刺 · 最终验收报告（S14）

> 冲刺窗口：2026-09-21 00:30 ~ 2026-09-22 00:35（两轮自动化窗口）
> 执行方式：A / B / C / D 四条错峰自动化线，每 25~30 分钟推进一个阶段
> 环境：本机 Linux 无头（无 X server / 无 YOLO 权重 / 无 `.env` 密钥 / 无 docker / 无网络）
> Python：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`
> 状态：**S0 ~ S13 全部完成，S14 归档中** —— 全量门禁 `bash scripts/check.sh` 退出码 0，**743 用例全绿**

---

## 一、结论

冲刺前的实测诊断是「**文档超前、代码残缺、零验证**」：核心运行时模块一度缺失、没有任何一行代码被真正执行验证过，README / ROADMAP 却宣称 v0.1~v1.9 全部完成。

因此本次冲刺把 v2.0 的目标从「加新功能」改为「**把地基做实**」——可导入、可离线跑通、有测试、有门禁、文档与代码一致。这个目标已经达成：

| 维度 | 冲刺前 | 现在 |
|---|---|---|
| 代码完整性 | 17 个核心文件从 git 恢复后才可导入 | 全部模块可导入，`compileall` 全绿 |
| 测试 | **0 用例** | **743 用例 / 14 个测试文件**，全离线可跑 |
| 门禁 | 无 | `bash scripts/check.sh`（语法 → 自检 → 档案 → 单测，退出码=失败环节编号） |
| 离线可跑 | 无密钥 / 无 GUI 即全线崩溃 | dry-run + mock 感知打通全链路，`agent_main --rounds 5` 可跑完 |
| 文档真实性 | 宣称完成但无法验证 | 三份文档加「验证状态 / 未验证」章节，并由 `tests/test_docs.py` 机器复核 |
| 版本库卫生 | 31MB Android 构建产物被跟踪 | 已移出索引；`.gitattributes` / `.gitignore` 三段分组依赖 |

---

## 二、阶段交付矩阵

| 阶段 | 名称 | 主要产物 | 用例增量 | 累计 |
|---|---|---|---|---|
| S0 | 前置恢复 + venv | 17 个文件恢复、隔离 venv | — | 0 |
| S1 | 仓库基线修复与卫生清理 | `.gitattributes`、`.gitignore`、requirements 三段分组 | — | 0 |
| S2 | 静态依赖与接口审计 | `tools/static_audit.py`、`devplan/AUDIT.md` | — | 0 |
| S3 | 预判引擎实测定型 | `tests/test_predictor.py` | 46 | 46 |
| S4 | 战斗评估与自动调参校验 | `test_combat_judge.py`、`test_auto_tuner.py` | 90 | 136 |
| S5 | 会话/汇报/技能模块校验 | `test_session.py`、`test_report_notifier.py`、`test_skill_manager.py` | 135 | 271 |
| S6 | 感知服务离线化 | `perception_server.py` 重写、`test_perception_server.py` | 99 | 370 |
| S7 | 主循环 dry-run | `agent_main.py` dry-run、`test_agent_main.py` | 87 | 457 |
| S8 | CLI 全命令冒烟 | `tools/cli_smoke.py`、`test_agent_cli.py` | 48 | 505 |
| S9 | MCP 工具注册验证 | `tools/mcp_tools_check.py`、`test_mcp_server.py`、`devplan/TOOLS.md` | 109 | 614 |
| S10 | 游戏档案体系固化 | `tools/add_game.py` v2.0、`test_game_profiles.py`、`devplan/PROFILE_SPEC.md` | 38 | 652 |
| S11 | UI 收敛与统一启动器 | `launcher.py`、`test_launcher.py`、`ui/legacy/` 归档 | 26 | 678 |
| S12 | 运维脚本与容器一致性 | `boot_check.py` v2.0、三脚本 v2.0、`Dockerfile` v2.0、`devplan/OPS.md`、`test_ops.py` | 26 | 704 |
| S13 | 测试套件固化与文档同步 | `scripts/check.sh`、`tests/test_docs.py`、三份文档同步 | 39 | **743** |

### 用例分布（14 个测试文件）

| 文件 | 用例 | 文件 | 用例 |
|---|---|---|---|
| `test_mcp_server.py` | 109 | `test_launcher.py` | 26 |
| `test_perception_server.py` | 99 | `test_auto_tuner.py` | 26 |
| `test_agent_main.py` | 87 | `test_ops.py` | 27 |
| `test_session.py` | 68 | `test_report_notifier.py` | 33 |
| `test_combat_judge.py` | 64 | `test_skill_manager.py` | 34 |
| `test_predictor.py` | 46 | `test_docs.py` | 38 |
| `test_agent_cli.py` | 48 | `test_game_profiles.py` | 38 |

---

## 三、发现并修复的真实缺陷（按严重度）

冲刺过程中**实测**发现的缺陷，全部有回归测试锁定：

### 阻断级（功能完全不可用）
1. **S7-A1 `kb_append` 从未注册**：主循环三处调用它，`call_tool` 不抛异常只把错误塞进返回内容 —— 「日志说已写入 N 条、实际一个字节没写」。
2. **S7-A2 MCP 协议污染**：启动 banner 与知识库提示打到 stdout，而 stdio 传输把 stdout 当 JSON-RPC 通道，客户端每帧 `ValidationError`。
3. **S9-M1/M2 知识库路径穿越**：`filename="../../evil.md"` 可写到库外、`game_name=".."` 可列出上级目录。
4. **S9-M3/M4 备份往返失真**：`kb_export` 用 `basename` 把按游戏分目录的知识库拍平，备份后分类全丢；`kb_import` 又把归档笔记复活。
5. **S8-C2 CLI 卡死**：`-c` 一次性模式仍走 `input()`，父进程透传 tty 时 `play 2` 卡死 200s+。
6. **S6-P1 感知错误伪装成空场景**：YOLO 报错被当成正常结果，Agent 误判「游戏里没怪」继续空转。
7. **S5-S1/S2 会话崩溃**：`load()` 对 list 档案抛异常；`round`/`deaths` 脏值炸掉 `play` 收尾记账（一局白打）。
8. **S12 boot_check 把可选依赖当必需**：本机 3 项全缺 → `start_all.sh --fail-fast` 100% 退出，即「离线链路根本起不来」。

### 高 / 中（行为错误或安全策略被绕过）
9. **S4-F1 逃生决策被静默吞掉**：组队协同无条件覆盖 `recommended_set`，「已在全力逃生」被队友配置改成辅助套。
10. **S4-F4 死配置**：`combat.chase_min_category` 定义了却没人消费，追杀档位写死在代码里。
11. **S9-M5 向量开关被局部变量短路**：`USE_VECTOR_SEARCH = False` 写在函数内，配置永远无效。
12. **S9-M6 dry-run 假成功**：`game_action("fly")` 校验前就返回「动作已记录」，无效动作被伪装成成功。
13. **S6-P1 mock 实体无限外推**：跑 3 分钟后飞出屏幕被过滤，感知从 5 个实体退化到 1 个。
14. **S8-C4 UI→CLI 调用形状对不上**：`ui_pyqt.py` 一直以不存在的参数调 CLI，100% 失败且无人发现。
15. **S3 抖动不降置信 / NaN 污染 / 分类不刷新**：三处数值缺陷，均由单测锁定。
16. **S13 stop_all 清理静默失败**：`rmtree(ignore_errors=True)` 吞掉失败，「磁盘没清干净」变隐形故障 —— 已改为显式 `[warn]` 告警。

---

## 四、验收记录（本轮实测）

| 验收项 | 命令 | 结果 |
|---|---|---|
| 一条命令门禁（全量） | `bash scripts/check.sh` | **退出码 0**，743 passed |
| 门禁（秒级） | `bash scripts/check.sh --fast` | 退出码 0；自检 ERROR 0 / WARN 5 |
| 单元测试 | `python -m pytest tests/ -q` | **743 passed / 0 failed** |
| 启动自检 | `python boot_check.py` | ERROR 0 / WARN 6，每条带降级指引 |
| 游戏档案 | `python game_profile_check.py --all --strict` | florr ✅ + space_invaders ✅ |
| MCP 工具 | `python tools/mcp_tools_check.py --strict` | 15 工具注册/调用/往返全过 |
| CLI 冒烟 | `python tools/cli_smoke.py --strict` | 31 条命令，0 traceback / 0 卡死 |
| 主循环离线 | `UGF_DRY_RUN=1 python agent_main.py --rounds 5` | 退出码 0，5 轮全链路跑通 |
| 统一启动器 | `python launcher.py --ui auto --selftest` | 选择 panel，退出码 0 |
| 运维干跑 | `bash start_all.sh --dry-run` | 退出码 0，无 .pid / 无端口占用 |

---

## 五、遗留风险与未验证项

### 5.1 环境性未验证（非代码缺陷，需换环境补验）

| 能力 | 阻塞原因 | 当前降级 |
|---|---|---|
| 真实 LLM / VLM 决策 | 无 `.env` 密钥 | `_fallback_decide` 规则分支 |
| 真实截图 + YOLO 感知 | 无 X server、无权重 | mock 后端 |
| 键鼠实际操作 | 无 GUI | dry-run 只记录不执行 |
| 联网检索 / Webhook 推送 | 无网络、无外部 MCP | 注入假 `requests` |
| 容器构建 | 无 docker | 静态口径对齐 + headless 替换 |
| GUI 真实渲染 | 无 X server / 未安装 | 仅验证可用性与命令构造 |

### 5.2 技术性遗留（按建议处理顺序）

1. **`switch_set` 键位映射是 florr 专属**（`SET_TO_KEY` 写死 1~5）；多游戏应按档案 `sets` 顺序映射 → **S15**。
2. **`_fallback_decide` 无 move 策略**：无 LLM 时只出 attack/defend/idle，安全区钳制与抖动未覆盖 → **S13 后尽快**。
3. **`mindset` 五个阈值仍硬编码**（1.2/1.5/0.5/0.4/0.3），与「全部来自 config.yaml」原则不符 → **S21**。
4. **`session.py` 与 `agent_cli.py` 各维护一份 state**，默认值不一致 → 收敛。
5. **`tests/test_docs.py` 基线常量 `743` 硬编码**，后续新增用例需同步上浮 → 可考虑动态化。
6. **`judge_combat` 的 highest_boss 分支存在死分支**（两分支产出相同），属产品决策，未擅自改动。
7. **`stop_all.sh` 只按 mtime 轮转日志**，未按体积封顶；磁盘紧张场景可加 `UGF_LOG_MAX_MB`。
8. **历史 pack 仍含 31MB 对象**（`.git` 约 130MB），磁盘宽裕时再处理，勿跑 `git gc --aggressive`。

---

## 六、下一步建议（第二阶段 S15~S26）

方向判断见 `devplan/DIRECTION.md`：项目真正资产是「**任意 2D 游戏可接入的流水线 + 越打越强的知识闭环**」，而不是某一个游戏的深度。建议优先级：

1. **S15 第二款游戏端到端跑通（space_invaders）** —— 证明「通用」二字，当前最硬的缺口。
2. **S17 接入流程一键化（onboard）** —— 让「换游戏」变成一条命令。
3. **S18 知识闭环实证** —— 学 → 检索 → 决策 → 复盘 → 回写，证明「越打越强」。
4. **S21~S23 门禁 / 长跑 / 安全** —— 把离线验证过的东西做成可持续。
5. **S24~S26 打包与发布** —— 最后才是分发。
6. **Florr 深度化后置**：依赖实机，本机不可验证，不应继续占用冲刺预算。

---

## 七、经验沉淀（给后续自动化线）

1. **先写工具再写报告**：`static_audit` / `cli_smoke` / `mcp_tools_check` / `game_profile_check` 一次写好，后续阶段直接复用为门禁。
2. **冒烟必须走子进程 + `stdin=DEVNULL`**：进程内 monkeypatch 抓不到 tty 透传导致的 `input()` 卡死。
3. **「函数被调用但从未定义」「常量定义了却没人消费」是高频真 bug**，静态审计抓不到，只有真实跑到那个分支才暴露。
4. **落盘型模块必须重定向路径**：`auto_tuner` / `session` / `kb_*` 不隔离会污染配置优先级与仓库。
5. **带时间的 mock 必须自约束**：随真实时间无限外推的假数据长跑后会退化成「空输入」，反而制造假故障。
6. **禁止在测试用例里删除仓库内文件**；也不要依赖清理类子进程继承当前环境——本轮两次「疑似宿主删除护栏」的归因都被推翻，真实根因是**子进程继承了 `UGF_DRY_RUN` 等环境变量**，显式清空后才稳定。
7. **门禁脚本不能默认系统解释器**：`python3` 无核心依赖会让自检误报 4 个 ERROR，必须做「能 import yaml」的能力探测。
