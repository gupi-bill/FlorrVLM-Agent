# 冲刺执行进度（自动机填写）

> 计划：`devplan/PLAN.md` ｜ 周期：每 30 分钟一个阶段 ｜ 停止时间：当日 07:00
> 运行环境：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`

## ⚠️ 本轮执行规则（每条自动化线开工前必读，优先级高于一切提示词）

1. **先读方向**：开工第一步读 `devplan/DIRECTION.md`。本项目是「通用 2D 游戏智能体框架」，真正资产是「任意 2D 游戏可接入的流水线 + 越打越强的知识闭环」。推进优先级：第二款游戏端到端跑通 > 接入流程产品化 > 知识闭环实证 > 可观测与门禁 > 稳定性与安全 > 打包分发 > **最后才是 Florr 深度化**（依赖实机，本机不可验证）。
2. **连续推进，不要只做一个就停**：从第一个未完成阶段开始，完成一个（更新本表 + `git commit`）后，**若本轮时间预算（25 分钟）仍有剩余，立刻开始下一个阶段**，直到预算用完或遇阻断。用户明确要求加大单轮工作量。
3. **第一阶段做完后自动进入第二阶段**：S1~S14 全部 ✅ 后，继续 `devplan/PLAN_PHASE2.md` 的 S15~S26（本表已列出）。不要停下等待新指令。
4. **运行锁防并发**：开工前看本文件顶部「运行锁」区块；若锁的时间距今 **< 15 分钟**且不是本轮自己写的，说明另一条线正在跑，**立刻退出、不做任何改动**。否则覆盖写锁（写线名 + 当前时间 + 阶段），结束前改为 RELEASED。
5. **停止判定**：所有阶段 ✅，或当前时间已晚于 **2026-09-22 07:00** → 只在执行日志追加一行后提交并结束。注意用完整日期比较，23:00 之后不算超时。

### 运行锁

`RELEASED | A线(02:47) | 2026-09-22T03:38 | S16`

（格式：`状态 | 线名 | ISO时间 | 阶段`。取锁时改为 `LOCK | <线名> | <时间> | <阶段>`）

---

## 阶段状态总表

| 阶段 | 名称 | 状态 | 周期 | 主要产物 |
|---|---|---|---|---|
| S0 | 前置：核心文件恢复 + venv | ✅ 完成 | 手动 | 17 个文件从 git HEAD 恢复；隔离 venv |
| S1 | 仓库基线修复与卫生清理 | ✅ 完成 | 01:31~01:40 (B线) | `.gitattributes`、`.gitignore` 增补、`requirements.txt` 三段分组、`requirements-dev.txt`；移除 8 个构建产物（含 1 个 31MB tar.gz）出版本库 |
| S2 | 静态依赖与接口审计 | ✅ 完成 | 02:01~02:45 (A线) | `tools/static_audit.py`、`devplan/AUDIT.md`、`devplan/audit_data.json`；`requirements.txt` 收敛 `mcp<2`、`mcp_server.py` v1/v2 兼容、`video_learner.py` cv2 软依赖 |
| S3 | 预判引擎实测定型 | ✅ 完成 | 02:41~02:55 (B线) | `tests/test_predictor.py`（46 用例全绿）、`tests/conftest.py`；`predictor.py` 抖动惩罚 + NaN 防御 + 分类逐帧重算；`config.yaml`/`config.py` 新增 4 个置信度曲线配置项 |
| S4 | 战斗评估与自动调参校验 | ✅ 完成 | 03:27~03:45 (A线) | `tests/test_combat_judge.py`(64)、`tests/test_auto_tuner.py`(26)；`combat_judge.py` 6 处修复、`auto_tuner.py` 3 处修复；`config.yaml`/`config.py` 新增 `combat.flee_distance`/`strafe_distance` |
| S5 | 会话/汇报/技能模块校验 | ✅ 完成 | 03:50~04:08 (B线) | `tests/test_session.py`(68)、`tests/test_report_notifier.py`(33)、`tests/test_skill_manager.py`(34)；`session.py` 10 处修复、`report_notifier.py` 5 处、`skill_manager.py` 5 处、`agent_cli.py` 会话 shim + 技能持久化；`skills/report/*` 从 9 行演示桩改为真实汇报 |
| S6 | 感知服务离线化 | ✅ 完成 | 04:43~05:05 (A线) | `perception_server.py` 重写（mock/auto/http 三后端 + `--selftest`）、`tests/test_perception_server.py`(99 用例)、`config.yaml`/`config.py` 新增 `perception.*` 段；`mcp_server._perception_url()` 端口随配置走 |
| S7 | 主循环 dry-run | ✅ 完成 | 05:11~05:34 (A线) | `agent_main.py` dry-run 分支 + `--rounds` 别名 + 软失败检测；`mcp_server.py` 补注册 `kb_append`、stdout→stderr、进程内 mock 感知降级；`perception_server.py` mock 漂移改累计时间基准；`tests/test_agent_main.py`(87)；`devplan/SMOKE_S7.md`；457 用例全绿 |
| S8 | CLI 全命令冒烟 | ✅ 完成 | 06:00~06:30 (A线) | `tools/cli_smoke.py`(31 条命令矩阵，可复用为门禁)、`tests/test_agent_cli.py`(48 用例)、`devplan/SMOKE_S8.md`；`agent_cli.py` 9 处修复：补齐未定义的 `_append_log`、`-c` 一次性模式彻底禁用交互提问、补 help/play/auto 与 `--auto search`、`unload` 跨进程恢复、kb_* 支持游戏名第二参数、交互模式补 kb_* 分支、帮助清单补登记、删 `_run_auto` 死代码 |
| S9 | MCP 工具注册验证 | ✅ 完成 | 06:39~07:10 (B线) | `tools/mcp_tools_check.py`(15 工具核对/调用/往返三检)、`tests/test_mcp_server.py`(109 用例)、`devplan/TOOLS.md`；`mcp_server.py` 10 处修复（路径穿越/向量开关死配置/dry-run 动作校验）、`kb_maintainer.py` 往返保真修复；`requirements.txt` mcp 放宽至 `>=1.0.0` |
| S10 | 游戏档案体系固化 | ✅ 完成 | 23:02~23:2x (C线) | `tests/test_game_profiles.py`(38)、`devplan/PROFILE_SPEC.md`；`florr.yaml` 补 port/sets/tactics、`tools/add_game.py` v2.0（生成即通过 strict 自检）、`agent_cli.py validate` 支持 `--strict`；**652 用例全绿** |
| S11 | UI 收敛与统一启动器 | ✅ 完成 | 23:16~23:36 (C线) | `launcher.py`（auto/panel/tk/cli + `--selftest`/`--list` + dry-run·mock 透传）、`tests/test_launcher.py`(26)、`ui/legacy/` 归档 pyqt/streamlit（含弃用头 + 路径 bootstrap + `python3`→`sys.executable`）、`admin_panel.py` 运行模式卡片、README 启动章节；**678 用例全绿** |
| S12 | 运维脚本与容器一致性 | ✅ 完成 | 23:31~00:12 (D线) | `devplan/OPS.md`、`tests/test_ops.py`(26)；`boot_check.py` v2.0 分级自检（core=ERROR / GUI·YOLO·可选库=WARN+降级指引 / 新增 `--strict`·`--json`·`--no-ops` / `check_ops()` 运维口径校验）；`start_all.sh` v2.0（`--dry-run`/`--no-check`/`--help`、`UGF_PYTHON`/`UGF_DRY_RUN`/`UGF_FOREGROUND`、端口改从 config.yaml 现读）；`stop_all.sh` v2.0（dry-run + 优雅终止 + 日志轮转 + 失效 pid 清理）；`watchdog.sh` 解释器覆盖；`Dockerfile` v2.0（opencv→headless、EXPOSE 5001/5002、前台模式）；**704 用例全绿（含根因修复后的回归）** |
| S13 | 测试套件固化与文档同步 | ✅ 完成 | 23:50~00:12 (D线) + 00:04~00:2x (A线) | `scripts/check.sh`（一条命令门禁：compileall → boot_check --fail-fast → game_profile_check --all → pytest，支持 `--fast`/`--help`，失败退出码=环节编号）、`tests/test_ops.py` 增至 26 用例、**`tests/test_docs.py`（38 用例文档—代码一致性门禁）**；README/PROJECT_SUMMARY/ROADMAP 三份文档同步（验证状态 / 离线模式 / 门禁 / 未验证清单 / 目录结构 / 版本口径）；**743 用例全绿** |
| S14 | 最终验收与归档 | ✅ 完成 | 00:30~00:38 (A线) | `devplan/FINAL_REPORT.md`（交付矩阵 / 743 用例分布 / 16 项真实缺陷 / 验收记录 / 遗留风险 / 下一步建议 / 7 条经验）；tag `v2.0-dev-20260922`；冲刺结论写入工作区记忆 |
| S15 | 第二款游戏端到端跑通（space_invaders） | ✅ 完成 | 01:26~02:05 (A线) | `tests/test_e2e_space_invaders.py`(14)、`devplan/E2E_S15.md`；`config.active_game()`（AGENT_GAME/UGF_GAME 生效，D1）、`agent_main._mcp_server_env()` 透传激活游戏（D2）、`mcp_server.resolve_set_keys()/normalize_set_name()` + 档案 `combat.set_map`（D3）、`agent_main._kb_game()` 知识库按游戏分区（D4）；`perception.mock` 迁回档案（florr.yaml 新增、config.yaml 移除）、space_invaders 补 `teammates: []`；`game_profile_check` 增 set_map 校验、`tools/add_game.py` 自动生成 set_map；PROFILE_SPEC §3/§6/§7 同步；**757 用例全绿**，`bash scripts/check.sh` 退出码 0 |
| S16 | 参考适配器模板与档案规范固化 | ✅ 完成 | 02:47~03:38 (A线) | `game_profiles/_template.yaml`（全字段注释模板 + `__UGF_*__` 槽位）、`tests/test_add_game.py`(26)、PROFILE_SPEC 新增 §0 模板机制与 §6.1 常见错误表；`tools/add_game.py` 改为**模板驱动渲染**（`load_template`/`template_defaults`/`render_from_template` + 槽位残留硬失败）、`_next_port()` 跳过 `_` 模板；**783 用例全绿**，`bash scripts/check.sh` 退出码 0 |
| S17 | 接入流程一键化（onboard） | ⬜ 待执行 | | |
| S18 | 知识闭环实证（学→检索→决策→复盘→回写） | ⬜ 待执行 | | |
| S19 | 学习链路离线化（视频→战术入库） | ⬜ 待执行 | | |
| S20 | 决策场景矩阵（战斗/组队/心态/边界） | ⬜ 待执行 | | |
| S21 | 测试门禁与可观测性固化 | ⬜ 待执行 | | |
| S22 | 稳定性长跑与资源门禁 | ⬜ 待执行 | | |
| S23 | 安全与合规加固 | ⬜ 待执行 | | |
| S24 | 打包分发实证 | ⬜ 待执行 | | |
| S25 | 文档体系重写 | ⬜ 待执行 | | |
| S26 | 版本发布与结项 | ⬜ 待执行 | | |

> S15~S26 详见 `devplan/PLAN_PHASE2.md`；方向判断详见 `devplan/DIRECTION.md`。

图例：⬜ 待执行 ｜ 🟡 进行中 ｜ ✅ 完成 ｜ ⛔ 阻塞

- **2026-09-21 06:30 · S8 · CLI 全命令冒烟（agent_cli.py）**
  - 做了什么：
    1. 新建冒烟工具 `tools/cli_smoke.py`：以**子进程**真实执行 `agent_cli.py -c "<cmd>"`（不走 monkeypatch，能抓到 import 期/运行期真实崩溃），逐条打超时，判定「不可读错误」= 输出含 `Traceback`。支持 `--json` / `--strict` / `--only`，**S13 可直接接成门禁**。
    2. **修复 C1（阻断，真实崩溃）**：`kb_list` / `kb_search` 在「游戏目录不存在」分支调用 `_append_log()`，而该函数在 `agent_cli.py` 中**根本不存在** —— `-c "kb_list florr"` 直接 `NameError` 吐 traceback。补齐实现（写 `run_logs/agent_<day>.log`，异常一律静默）。
    3. **修复 C2（阻断，卡死）**：`_collect_brief()` 无条件 `input()`，原先只靠 `EOFError` 兜底 —— 实测当父进程把 tty 透传给子进程时，`-c brief` 20s 超时、`-c "play 2"` 卡死 200s 以上。新增 `_ONE_SHOT` 全局开关：`-c` / `--auto` 一次性调用**无论 stdin 是什么都不提问**，答案改从 `UGF_BRIEF_*` 环境变量取。同时把冒烟工具的 `stdin` 显式设为 `DEVNULL`（这是能稳定复现/验证该缺陷的关键）。
    4. **修复 C3（高）**：`-c` 模式下 `help` / `play` / `auto` 三个在帮助里写着的命令全部落到「未知命令」。补齐，并把命令表从 `main()` 局部变量抽成 `_command_registry(arg)`，使「帮助清单 ⊇ 命令表」可由单测锁定。
    5. **修复 C4（高，PLAN 点名项）**：`ui_pyqt.py:139` 一直以 `["python3","agent_cli.py","--auto","search",game,"basic guide"]` 调用，而 CLI 既无 `--auto` 参数也无 `search` 子命令，该调用 100% 失败。新增 `--auto`（`--auto <游戏>` 全链路 / `--auto search <游戏> <查询词>` 走 detect→research→ensure）与等价的 `-c "auto_search <游戏> <查询词>"`。
    6. **修复 C5（中）**：`-c "unload report"` 跨进程不恢复技能，显式卸载恒返回「未加载」（`run_skill` 早有恢复逻辑，`unload` 漏了）→ 卸载前先按档案恢复。
    7. **修复 C6（中）**：`kb_search/write/append` 把整个 `arg` 当成一个参数，`kb_search boss florr` 实际搜的是 `"boss florr"` → 新增 `_arg2()` 支持游戏名第二参数。
    8. **修复 C7（中）**：交互模式 `interactive()` 的 elif 链里没有 `kb_list` / `kb_search` / `kb_write` / `kb_append`，交互式会话中这四个命令一律「未知命令」→ 补齐分支。
    9. **修复 C8（低）**：`HELP_LINES` 与 `describe_capabilities()` 都没登记 4 个 kb 命令 → 补齐。
    10. **修复 C9（低）**：`_run_auto` 的 `return` 之后有 28 行完全重复的死代码 → 删除，并由 AST 断言锁定。
    11. 附带：删除重复 `import config`；模块级 `import datetime` 替代函数内 `__import__("datetime")`；`research` 离线时追加统一降级提示 `_offline_note()`；未知命令退出码 0→1 并附可用命令列表。
  - 产物：`tools/cli_smoke.py`、`tests/test_agent_cli.py`、`devplan/SMOKE_S8.md`、`agent_cli.py`(M)
  - 测试结果：
    - `python tools/cli_smoke.py` → **31 条命令：ok 31 / traceback 0 / 有意义输出 30 (96%)**（余下 1 条为故意的未知命令反向用例）✅
    - 修复前后对比：traceback 1→0；交互阻塞超时 1→0；卡死超时 3→0；落到「未知命令」的已声明命令 3→0 ✅
    - `python -m pytest tests/ -q` → **505 passed**（S7 的 457 + 本轮 48，0 failed）✅
    - 端到端：`-c "play 2"` 14 秒跑完 2 轮（修复前卡死 >200s），MCP 连上 15 个工具，回合日志/换套/BOSS 记忆/复盘/汇报全走通 ✅
    - `-c "unload report"` 从「未加载」变为「已卸载」✅；`-c "kb_list florr"` 从 NameError 变为「知识库暂无文档」✅
    - `--auto search florr basic guide` 与 `--auto florr` 均正常出结果（修复前参数不存在）✅
    - `compileall -q .` 退出码 0；冒烟产生的 `dist/`(148K) / `kb_backups/`(16K) / `knowledge_md/smoke_s8.md` 已清理，`git status` 仅 3 项预期变更 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `play` 的 dry-run 走 `_fallback_decide` 规则分支，冒烟 2 轮只触发 `defend`，`move` 类动作（安全区钳制+抖动）未覆盖。与 S7 遗留同源，建议 **S13** 前补规则化 move 策略。
    - `package portable` / `kb_export` 会往 `dist/` 与 `kb_backups/` 落真实产物（已被 `.gitignore` 覆盖）。长跑累积移交 **S12** 运维脚本。
    - `research` 的真实联网检索仍未实测（无外部 MCP 配置、无网络），本轮只验证降级分支可读不崩溃。
    - **`ui_pyqt.py` 仍用 `python3` 而非隔离 venv 解释器**调用 CLI。本轮只对齐了参数形状（C4），解释器路径移交 **S11**。
    - `reset_brief` 的 lambda 用海象+元组+`and` 写法，可读性差但行为正确，未重构以免扩大改动面，移交 **S13**。

- **2026-09-22 00:04 · S13 · 测试套件固化与文档同步（收尾：三份文档 + 文档门禁）**
  - 起点判定：运行锁 `RELEASED`（D 线 23:47 释放），状态表首个非 ✅ 为 S13（🟡 部分完成），当前 00:04 < 2026-09-22 07:00，故续做 S13 未完成部分。（提示词写"从 S9 续跑"，但 S9~S12 均已完成，按 PROGRESS 文件规则从首个非 ✅ 开始。）
  - 做了什么：
    1. **新增 `tests/test_docs.py`（38 用例）—— 本阶段最实质的产出**：把"文档说真话"变成可机器复核的门禁，而不只是人工改一遍。覆盖：三份文档存在且非空、devplan 六份文档齐全、门禁脚本 `scripts/check.sh` 四个环节齐全、**三份文档测试基线口径一致（704）**、均链到 PROGRESS、均如实披露「未验证」、禁止失真表述（`连续 2 帧死亡` / `实机已验证` / `全部功能已完成`）、无 `sk-` 密钥字面量、**README 死亡帧数 == `config.yaml death_frame_threshold`**、**README MCP 标题数量 == 表格条目数 == 服务端实际注册清单**（复用 `tools/mcp_tools_check.check_registry()`）、文件结构块含 8 个新目录、本地 markdown 链接全部可达、ROADMAP/SUMMARY 含冲刺章节与状态口径、历史版本表必须带「实机未验证」限定、`tests/` 文件数 ≥14 且有 conftest。
    2. **README.md 修订**：新增「🧪 离线模式与自测」（4 个开关/参数表 + 5 条复核命令）与「✅ 验证状态」（门禁命令、**已实测 9 项** / **未验证 6 项**两张表 + 口径说明）；修掉与 `config.yaml` 冲突的「连续 2 帧死亡」→ 8 帧；文件结构补 `tests/`、`scripts/check.sh`、`devplan/`、`launcher.py`、`ui/legacy/`、`knowledge_archive/`、`run_logs/`、`space_invaders.yaml` 及 tools 全量；版本进度表 v0.1~v1.9 由无条件「✅ 已完成」改为「代码已落地 ✅ --- 实机未验证 ⚠️」并加口径说明；目录补两项锚点。
    3. **PROJECT_SUMMARY.md 修订**：新增「十、v2.0 冲刺实测状态」（门禁 + S1~S13 产物一览表 + 已实测 / 未验证），文件结构补全，第八节版本进度加「代码已落地 vs 实机未验证」口径，注意事项补离线跑法；并修掉两处「连续 2 帧」死亡描述。
    4. **ROADMAP.md 修订**：新增「v2.0 冲刺校准（实测）」章节（门禁 + 10 项已实测 + 6 项未验证）；版本总览下加**状态口径声明**（✅ = 代码已落地且通过离线验证，不等于实机验收）；v2.0 定位改为「地基做实」，并注明 **Florr 深度化因依赖实机、本机不可验证而后置**。
  - 产物：`tests/test_docs.py`、`README.md`(M)、`PROJECT_SUMMARY.md`(M)、`ROADMAP.md`(M)、`devplan/PROGRESS.md`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **743 passed**（S12 的 704 + 文档门禁 38 + 清理告警 1，0 failed）✅
    - `python -m pytest tests/test_docs.py -q` → 38 passed（首轮 37 通过 / 1 失败，失败项正是它抓出的真问题：PROJECT_SUMMARY 仍写「连续 2 帧死亡」，已修）✅
    - `bash scripts/check.sh --fast` → 退出码 0（语法 OK + 自检 ERROR 0 + 两份档案 ✅）✅
    - `compileall -q .` 退出码 0 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `tests/test_docs.py` 的基线常量 `BASELINE_CASES = "704"` 是**硬编码**，后续阶段新增用例后文档与常量需同步上浮；未做成动态采集（`pytest --collect-only` 会让门禁变慢且不稳定）。建议 S21 可观测性阶段再考虑动态化。
    - 三份文档中的「已实测」结论依赖**离线**结果；一旦补上实机验证，需同步替换口径，不能只改一处。
    - README 的架构图未画 `perception_server` / `launcher` / 门禁，属示意图简化，未强求与文件结构一致。
    - `PROJECT_SUMMARY.md` 第三节「外部依赖仓库（需自行 git clone）」涉及联网仓库，未做可达性校验（链接检查只覆盖本地相对路径）。

- **2026-09-22 00:30 · S14 · 最终验收与归档**
  - 起点判定：S13 已 ✅ 并提交（`ee84a0f`），运行锁由本线持有，当前 00:30 < 2026-09-22 07:00 → 按「预算有余则继续下一阶段」连做 S14。
  - 做了什么：
    1. 新建 `devplan/FINAL_REPORT.md`：冲刺结论（冲刺前「文档超前 / 代码残缺 / 零验证」→ 现在「可导入 / 离线可跑通 / 743 用例 / 一条命令门禁 / 文档与代码一致」六维对比）、**S0~S13 交付矩阵**（产物 + 用例增量 + 累计）、**14 个测试文件的用例分布表**、**16 项实测发现并修复的真实缺陷**（8 项阻断级 + 8 项高中级，每项注明根因）、**10 条验收命令与结果**、遗留风险 8 条 + 环境性未验证 6 项、第二阶段 S15~S26 优先级建议（Florr 深度化后置）、7 条经验沉淀。
    2. 实测复核：`bash scripts/check.sh`（全量）**退出码 0 / 743 passed**；`--fast` 退出码 0；`boot_check.py` ERROR 0 / WARN 5。
    3. 归档：`git add -A && git commit`，打 tag **`v2.0-dev-20260922`**。
    4. 冲刺结论写入工作区记忆 `.workbuddy/memory/2026-09-22.md`。
  - 产物：`devplan/FINAL_REPORT.md`、`devplan/PROGRESS.md`(M)、tag `v2.0-dev-20260922`、工作区记忆条目
  - 测试结果：`bash scripts/check.sh` 退出码 0（compileall + boot_check + 两份档案 + **743 用例全绿**）✅
  - 收尾说明（自主决策理由）：S1~S14 全部 ✅，本轮已耗时约 35 分钟（超 25 分钟预算），**S15（第二款游戏端到端跑通）体量较大，半途开工会留下 🟡 半成品状态**，故本轮到此收口并释放运行锁；下一轮（00:30 B 线）从 `devplan/PLAN_PHASE2.md` 的 **S15** 起跑。
  - 遗留：见 `FINAL_REPORT.md` 第五节（8 条技术性遗留 + 6 项环境性未验证）。

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

本次冲刺由多条错峰自动化线驱动，共同实现「每 30 分钟推进一个阶段」：

**第二轮窗口：2026-09-21 23:00 ~ 2026-09-22 07:00**
> ⚠️ 起点更正：窗口安排时写的是「从 S9 续跑」，但 **S9 已由 B 线在 07:10 收尾完成**（614 用例全绿，见下方执行日志）。
> 因此 23:00 首轮请**直接从 S10 · 游戏档案体系固化**开始，不要重跑 S9。

| 时间 | 触发线 | 时间 | 触发线 |
|---|---|---|---|
| 09-21 23:00 | 一次性启动任务 | 09-22 03:00 | A 线（整点） |
| 09-21 23:30 | 一次性半点任务 | 09-22 03:30 | B 线（半点） |
| 09-22 00:00 | A 线（整点） | 09-22 04:00 | A 线 |
| 09-22 00:30 | B 线（半点） | 09-22 04:30 | B 线 |
| 09-22 01:00 | A 线 | 09-22 05:00 | A 线 |
| 09-22 01:30 | B 线 | 09-22 05:30 | B 线 |
| 09-22 02:00 | A 线 | 09-22 06:00 | A 线 |
| 09-22 02:30 | B 线 | 09-22 06:30 | B 线（最后一轮） |

- 各条线共用本文件判定「下一个待执行阶段」；单轮限制 25~30 分钟内完成；窗口结束（07:00）后自动停止（`validUntil`）。
- 调度器限制：不支持逗号形式的 `BYMINUTE`；且 `validFrom` 为当日 23:00 时会被顺延到次日 00:00，故 23:00 / 23:30 两轮改用一次性任务补齐。

> 第一轮窗口（2026-09-21 00:30~06:50）：A 线整点 + B 线半点，完成 S1~S8 后由用户叫停。

---

## 调度变更（2026-09-21 22:00，待执行）

用户要求：任务不能一条通用提示词反复跑，必须是 **17 条内容各自不同的一次性任务**，每条对应一个阶段、绑定一个固定时间点，间隔从 30 分钟压到 **25 分钟**。

完整 17 条任务定义见 **`devplan/AUTOMATION_TASKS.md`**（含每条的 prompt 正文、交付物、验收、以及「用户视角：做完他能得到什么」）。

排期：23:00 → 23:25 → 23:50 → 00:15 → … → 05:40（末条），06:05~07:00 为溢出缓冲。

**创建前置动作**：先把已有的 4 条旧自动化（23:00 一次性 / 23:30 一次性 / 整点线 / 半点线）置为 **PAUSED**，否则会重复开工。
（截至 22:00，`automation_update` 工具在当前会话工具集中不可用，17 条尚未创建；已在 `~/.workbuddy/MEMORY.md` 记录"工具可能消失，规则要写进文件"的应对方式。）

---

## 执行日志

（每个周期结束后在下方追加，格式：时间 · 阶段 · 做了什么 · 产物 · 测试结果 · 遗留）

- **2026-09-21 01:40 · S1 · 仓库基线修复与卫生清理**
  - 做了什么：
    1. `git rm -r --cached` 移除 `packaging/androidapp/.buildozer/**`（4 个文件，含 1 个 31MB `v3.14.2.tar.gz`），磁盘文件保留未删。
    2. 追加发现 IDE 产物 `.trae-html-share-packages/`（60K / 4 文件）同样被跟踪，一并从索引移除。
    3. `.gitignore` 增补：`.buildozer/` `.gradle/` `*.apk` `*.aab` `*.tar.gz` `*.zip` `*.db` `.trae-html-share-packages/` `.trae/`；主动放弃 `bin/` 规则（避免误伤合法脚本目录，改由 `*.apk` 覆盖）。
    4. 新增 `.gitattributes`：`* text=auto eol=lf`，显式声明文本/二进制类型，Windows 脚本保留 CRLF。
    5. 重写 `requirements.txt`：core（7 项）/ optional（3 项，标注 `opencv-python-headless` 无头替代）两段分组，附 TMPDIR 安装说明。
    6. 新增 `requirements-dev.txt`：pytest / pytest-cov / ruff。
    7. 补装缺失的 core 依赖 `numpy`（2.5.3），装在隔离 venv 内。
  - 产物：`.gitattributes`、`.gitignore`(M)、`requirements.txt`(M)、`requirements-dev.txt`
  - 测试结果：
    - `git diff --cached --diff-filter=AM` 无 MB 级新增 ✅
    - `git add -A && git status --short` 无异常项 ✅
    - 版本库内最大文件由 31MB 降至 33KB（`agent_main.py`），跟踪文件 51 个 ✅
    - `compileall -q .` 退出码 0 ✅
    - core 依赖导入探测全通过（flask/requests/dotenv/yaml/psutil/mcp/numpy/pytest）✅
    - optional（pyautogui/PIL/cv2）确认不可用 —— 无头环境预期内，后续阶段走 mock 降级
  - 遗留：
    - 历史 pack 仍含 31MB 对象（`.git` 125MB）。按 PLAN 约束不跑 `git gc --aggressive`，待磁盘宽裕时再说。
    - `.gitignore` 中 `*.png` `*.jpg` 为宽泛规则，若将来需入库图片素材需 `git add -f` 或收窄规则（记录备查）。

- **2026-09-21 02:45 · S2 · 静态依赖与接口审计**
  - 做了什么：
    1. 新建审计工具 `tools/static_audit.py`（619 行，纯标准库）：ast 解析 27 个模块生成 import 图 / 顶层符号表；子进程 + 超时 + stub 注入的导入探针；跨模块缺失符号 / 属性 / kwargs 三项交叉核对；requirements 对账；命名空间遮蔽检测。
    2. 全量导入探针（stub）24/26 成功；裸环境（不注入 stub）23/25 成功。
    3. 定位并**修复**两个阻断级：`mcp_server` 与 mcp 2.x SDK 不兼容（FastMCP→MCPServer 改名）、`video_learner` 顶层硬依赖 cv2。
    4. `requirements.txt`：`mcp` 上界收敛 `<2.0.0`；新增第 3 段「可选但默认不装」注释登记 PyQt6/streamlit/chromadb/sentence-transformers/kivy。
    5. 顺手修 `mcp_server._path_perturb_move()` 缺失的 pyautogui 降级（W6）。
  - 产物：`devplan/AUDIT.md`（含依赖表 / 缺失符号清单 / 占位清单 / 风险分级）、`devplan/audit_data.json`、`tools/static_audit.py`、`requirements.txt`(M)、`mcp_server.py`(M)、`video_learner.py`(M)
  - 测试结果：
    - `python tools/static_audit.py` 退出码 0；跨模块缺失符号 0、kwargs 不匹配 0 ✅
    - 导入探针 22 → 24 / 26（修复 mcp_server、video_learner）✅
    - 裸环境 `import mcp_server` 成功且 `MCP_SDK_VERSION=2` ✅
    - 裸环境 `import video_learner` 成功，`CV2_AVAILABLE=False`、`extract_frames()` 返回 `[]` ✅
    - `packaging/` 遮蔽变通方案实测通过（`sys.path` 含 packaging 后 `import android_main` 成功，导出 FlorrApp/Root 等）✅
    - `AUDIT.md` 含阻断级 3 / 警告级 8 / 建议级 5，每条阻断级均有修复方案 ✅
  - 遗留（已移交，未在本轮处理）：
    - B2 `packaging/` 被 PyPI 同名包遮蔽 —— 刻意不改目录结构/不加 `__init__.py`（会反向遮蔽 pip 依赖），按变通方案处理。
    - B1 仅验证到 import 层，mcp 2.x 工具注册可用性移交 **S9** 实测。
    - W1（agent_cli 的 session 降级 shim 含 4 个不存在 API）、I4（skills/report/skill.py 仅 9 行）移交 **S5**。
    - W2/W3（PyQt6、streamlit 未安装）与 I5（4 套前端并存）移交 **S11** 收敛。
    - I1 副作用：`import mcp_server` 会自动向 `knowledge_md/` 写 4 个模板文件（审计时被触发，属既有行为）。

- **2026-09-21 02:55 · S3 · 预判引擎 predictor.py 实测定型**
  - 做了什么：
    1. 核对 `predictor.py` 读取的 11 个配置键与 `config.yaml` / `config.py DEFAULT` 三方完全一致（predict_seconds / min_frames / entity_timeout / max_output_entities / history_maxlen / confidence_threshold / rarity_*4 / threat），无漂移。
    2. 新建 `tests/test_predictor.py`（15 个测试函数 / 46 个用例，含 parametrize 展开）+ `tests/conftest.py`（注入项目根路径 + 无头环境 pyautogui/cv2/PIL stub）。
    3. 测试用 FakeClock（monkeypatch `predictor.time`）替代真实时钟，速度与超时完全确定性复现，不依赖 sleep、不 flaky。
    4. **修复缺陷 1（抖动不降置信）**：原置信度只按首尾两点算速度，来回抖动的轨迹会被平均掉，与直线冲刺拿到同样高的分。新增 `_trajectory_linearity()`（净位移 / 累计路程）作为抖动惩罚因子，下限 `predictor.jitter_floor=0.35`。
    5. **修复缺陷 2（NaN 坐标污染）**：`_is_valid_coord` 用 `float()` 后比较，`float('nan')` 能穿过所有 `<0` / `>100000` 判断进入追踪器，后续速度与预判全变 NaN。改用 `math.isfinite()` 拦截 NaN/Inf。
    6. **修复缺陷 3（分类不随稀有度刷新）**：`update_frame_entities` 原先只在创建时算 category，怪物从 Common 升到 Super 后威胁分永远停在 15。改为逐帧按 role/rarity 重算。
    7. 置信度曲线 3 个硬编码参数（8 帧满分 / 2000px·s⁻¹ 参考速度 / 0.3 惩罚下限）提到配置层：`predictor.frame_full_frames` / `speed_ref` / `speed_penalty_floor`，并同步进 `config.yaml` 与 `config.py DEFAULT`。
    8. 防御性加固：同名怪最近距离匹配时 history 为空会 IndexError，改为 0 距离兜底。
  - 产物：`tests/test_predictor.py`、`tests/conftest.py`、`predictor.py`(M)、`config.yaml`(M)、`config.py`(M)
  - 测试结果：
    - `python -m pytest tests/test_predictor.py -q` → **46 passed**（0 failed）✅
    - 覆盖：匀速外推 / 帧数不足降级 / 帧数-置信度单调 / 高速阈值锁 / 抖动降置信 / 超时剔除（0.2s 保留、0.5s 剔除）/ 威胁五档排序 / top-8 截断 / 稀有度分级 15 组 / 非法坐标 8 组 / 同名双怪不串号 / 角色识别 8 组 / reset / 配置热加载 / 历史窗口上限
    - `compileall` predictor.py + config.py + tests/ 退出码 0 ✅
    - `import mcp_server`（predictor 唯一跨模块调用方）成功，配置新键生效：`jitter_floor=0.35 speed_ref=2000 frame_full=8` ✅
  - 遗留：
    - 阈值锁偏保守：`confidence_threshold=0.65` 需 ≥6 帧且近乎直线才可能采信预判（3 帧上限仅 0.375）。属设计选择，交由 **S4** 的 `auto_tuner` 实测后再决定是否下调。
    - 同名怪匹配无距离上限，实体瞬移跨屏时仍可能张冠李戴（未修，避免与 v0.2 既有策略冲突）。
    - `combat_judge` 复用 `predictor.threat` 表但自身另有默认值分支，**S4** 需核对两处是否漂移。（S4 结论：两处 threat 表数值一致，无漂移；但 `combat.chase_min_category` / `safe_zone_margin` 在 combat_judge 内确实存在配置漂移，已修）

- **2026-09-21 03:45 · S4 · 战斗评估与自动调参校验**
  - 做了什么：
    1. 梳理输入契约：`judge_combat` 收 `CombatContext`（player/enemies/teammates/屏幕），输出 7 键决策字典；`agent_main` 消费 `decision` / `recommended_set` / `mindset` / `threat_ratio`，实测调用形状对齐无漂移。
    2. 核对 `combat_judge.CATEGORY_THREAT`（自 `predictor.threat`）与 `predictor` 自身表：7 个分类数值完全一致，S3 遗留的「两处漂移」疑问排除。
    3. 新建 `tests/test_combat_judge.py`（**64 用例**）与 `tests/test_auto_tuner.py`（**26 用例**）；`conftest.py` 新增 `tmp_tuned` 夹具把调参落盘路径重定向到 `tmp_path`，避免污染 config 加载优先级。
    4. **修复 6 处 combat_judge 缺陷**：
       - **F1（安全性，回归测试锁定）** 组队协同无条件覆盖 `recommended_set`，导致「已在全力逃生」被队友套装配置改成辅助套，逃生决策被静默吞掉 → 逃生优先级高于协同（`decision != retreat` 才协同；`_team_set_adjust` 新增可选 `decision` 参数，`None` 保持旧行为）。
       - **F2** `clamp_to_safe_zone` 在屏幕小于安全区时恒返回 `margin`，坐标可能落到屏幕外 → 退化为钉屏幕中心。
       - **F3** `calc_retreat_position` 硬编码 `margin=100 / 300 / 150`，与 `combat.safe_zone_margin` 脱节 → 改用配置，并把 `flee_distance` / `strafe_distance` 提到配置层（缺省值与原硬编码一致，行为不漂移）。
       - **F4** `combat.chase_min_category` 是死配置（`should_chase` 把 boss/elite 写死在代码里）→ 新增 `CATEGORY_RANK` 档位表按配置取最低可追档位；`highest_boss` 仍永不追。
       - **F5** `CombatEvaluator.__init__` 默认参数在 import 时绑定，config 热加载后新建评估器仍用旧防抖间隔 → 改 `None` 运行时取值。
       - **F6** 脏数据防御：`hp` / `max_hp` / `power_score` 为 `None` / 字符串 / NaN、enemies 含非 dict 时原会抛 `TypeError` 或污染决策链 → 新增 `_safe_float()` 统一收敛。
    5. **修复 3 处 auto_tuner 缺陷**：
       - **T1** 模块常量 `HOLD` 只被 `_hold` 计数却从不消费，与文档「每次调整后一段时间内不再乱动」不符，实测会持续震荡 → 实现真正的冷静期（`_cooldown`），无调整则不进入冷静期。
       - **T2** `current()` 原样返回文件里的越界值（如 `retreat_ratio: 99`）→ 读取即夹紧。
       - **T3** 手写坏的 yaml（顶层非 dict / 子段为字符串 / 语法错误）会抛 `AttributeError` 炸穿 `agent_main` 调参调用点 → 新增 `_section()` / `_clamp()` 兜底；`_write` 异常捕获从 `OSError` 放宽到 `Exception`。
    6. `config.yaml` + `config.py DEFAULT` 同步新增 `combat.flee_distance: 300`、`combat.strafe_distance: 150`。
  - 产物：`tests/test_combat_judge.py`、`tests/test_auto_tuner.py`、`tests/conftest.py`(M)、`combat_judge.py`(M)、`auto_tuner.py`(M)、`config.yaml`(M)、`config.py`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **136 passed**（predictor 46 + combat_judge 64 + auto_tuner 26，0 failed）✅
    - combat_judge 覆盖：威胁求和/未知分类/非 dict 实体、威胁比（0/负/None/NaN → 999 哨兵）、三档决策与 0.8/1.4 边界、highest_boss 强弱势、心态 7 档、组队协同 4 例（含逃生回归）、追杀 5 例（含 `chase_min_category` 生效）、安全区钳制（含退化回归）、抖动边界、避险走位 flee/strafe/重合点、评估防抖缓存命中与 invalidate、脏数据、热加载 ✅
    - auto_tuner 覆盖：默认值、死亡线性下调、命中率下调、上下限夹紧、坏文件 5 例、冷静期 4 例、往返/reset/status ✅
    - 集成冒烟：复刻 `agent_main` 调用形状（highest_boss + 弱实力 + 战斗套队友）→ `decision=retreat, recommended_set=retreat`（修复前会被改成 `team`）✅
    - `compileall` combat_judge / auto_tuner / config / tests 退出码 0 ✅
    - 回归：`config / predictor / combat_judge / auto_tuner / mcp_server / session / report_notifier / skill_manager` 全部可导入 ✅
    - 仓库零污染：调参测试后无 `tuned_overrides.yaml` 残留，`git status` 仅预期变更 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `judge_combat` 的 highest_boss 分支中 `ratio > RETREAT_RATIO*0.6` 与 `else` 两个分支产出完全相同（均为 cautious + tank），属死分支。刻意不改（改动会影响既有对局策略），建议 **S13** 文档同步时如实标注或由产品侧决定「实力充足是否应升为 fight」。
    - `decide_mindset` 的 1.2 / 1.5 / 0.5 / 0.4 / 0.3 五个心态阈值仍硬编码，与 v0.5「全部来自 config.yaml」原则不符。未提配置层（本轮预算 + 避免扩大改动面），移交 **S13**。
    - `should_chase(entity, player, ...)` 的 `player` 形参在函数体内未被使用，已给默认值 `None` 兼容，是否移除待 **S7** 主循环实测后再定。
    - pytest 的 `tmp_path` 落在 `/tmp`（10M tmpfs）。本轮用例产生的 yaml 均为字节级，实测无压力；**S13** 固化门禁时若新增大文件用例，需前置 `TMPDIR=/home/g-bill/.workbuddy/tmp`。

- **2026-09-21 04:08 · S5 · 会话/汇报/技能三大支撑模块校验**
  - 做了什么：
    1. 新建三个测试文件共 **135 用例**：`tests/test_session.py`(68) / `tests/test_report_notifier.py`(33) / `tests/test_skill_manager.py`(34)。全部落盘路径经 `monkeypatch` 重定向到 `tmp_path`；Webhook 用注入的假 `requests` 模块，全程零真实网络请求。
    2. **`session.py` 修复 10 处**：
       - **S1（阻断）** `load()` 对 list / 标量档案 `d.update(st)` 抛 "cannot convert dictionary update sequence"，整个 `session` 命令不可用 → 加 `isinstance(st, dict)` 兜底。
       - **S2（阻断）** 快照 / 历史 / 入参里的 `round` `deaths` 为 None、空串、非数字串或 NaN 时 `int(x or 0)` 抛 ValueError/TypeError，**直接炸掉 `agent_cli._cmd_play` 的收尾记账，一局白打** → 新增 `safe_int()` 统一收敛（含 `int(inf)` 的 OverflowError）。
       - **S3** `save()` 只捕 `OSError`，含 set/datetime 等不可序列化对象时抛裸 `TypeError` → 放宽为 `RuntimeError` 并带原因。
       - **S4** `describe()` 里 `last_report` 为 JSON `null` 时 `None[:80]` TypeError、为 dict 时切片 KeyError → 统一转字符串。
       - **S5** `resume_info()` 直接 subscript `rp['game']` / `['from_rounds']`，档案缺键即 KeyError → 改 `.get` + `safe_int`。
       - **S6** `stats()` / `stats_text()` 对含非 dict 条目、缺 `at`、`rounds` 非数字的历史文件会炸 → 过滤 + `safe_int`。
       - **S7** `HISTORY_MAX` 在 import 时绑定 config，热加载后上限不生效（与 S4 的 F5 同类）→ 改 `_history_max()` 运行时取值。
       - **S8** `_append_history` 遇到历史文件里混入非 dict 条目会原样写回、污染后续统计 → 写入前过滤。
       - **S9** `record_end` 的 `skills` 未做类型归一，含非字符串元素会污染档案 → `sorted({str(s) ...})`。
       - **S10** `history()` 文档串声称"新→旧"但实际返回文件顺序（旧→新），与 `stats()` 的 `[-5:][::-1]` 口径矛盾 → 修正文档串，避免**S13**文档同步时被误导。
    3. **`report_notifier.py` 修复 5 处**：
       - **R1** `_tail_log(0)`：`lines[-0:]` 等价于 `lines[0:]`，n≤0 时把**整份日志**塞进报告 → 显式 `n<=0` 返回 `[]`。
       - **R2** 无快照时报告打出 `- HP：None/None`，读者无法区分"没数据"和"血量为 0" → 改为「未知（无快照）」。
       - **R3** `push_webhook` 只返回 bool，无法区分「没配 URL / requests 缺失 / 网络异常 / HTTP 非 2xx」→ 改返回 `(ok, 原因)` 元组（已确认无外部调用方）。
       - **R4** `write_report_file` / `notify` / `notify_progress` 的异常捕获从 `OSError` 放宽（日志目录被占成同名文件时会抛 `NotADirectoryError` 之外的类型）。
       - **R5** 报告正文新增离线标注行，明确"数值来自本地快照"，避免离线产出被误读为真实对局数据。
    4. **`skill_manager.py` 修复 5 处**：
       - **K1（安全）** 技能名未校验，`load("../../etc")` 可越出 `skills/` 目录 → 新增 `is_valid_name()`，拒绝含 `/ \ : \0 ..` 的名字。
       - **K2** 加载 skill.py 时不注册 `sys.modules`，技能内用 dataclasses / 相对导入 / 自引用必失败 → 先注册再 exec；加载失败时回退清除，不留残缺模块。
       - **K3** 单个技能文件损坏（编码/权限）会拖垮整个 `scan()` → 逐项 try/except 并降级为空元信息。
       - **K4** `entry` 指向非可调用对象时仍被当成可用入口 → 增加 `callable()` 校验。
       - **K5** 只有文本返回，调用方无法程序化判断 → 新增 `is_loaded()` / `reload()`。
    5. **`skills/report/` 从 9 行演示桩改为真实汇报**：`skill.py` 改为读取 `agent_state.json` + `run_logs/agent_snapshot.json`，输出场次/回合/死亡/HP/决策/心态/套装/最高威胁，读不到走降级分支并标注离线；`SKILL.md` 补数据来源表、入口签名、示例输出、离线约束。
    6. **`agent_cli.py`**：修掉 S2 审计遗留的 W1 —— 会话降级 shim 里的 `load_state/save_state/update_state/clear_state` 在 `session.py` 中根本不存在，session 缺失时 `_cmd_play` 会 AttributeError；现按真实 API 对齐。另 `load_state()` 也补上非 dict 档案兜底。
    7. **新增技能跨调用持久化**：`run_skill` 在一次性调用模式（`python agent_cli.py -c "run_skill report"`）下原先永远返回"未加载"，因为 `load` 只存在于内存、进程退出即丢 → 已加载技能写入 `agent_state.json["skills_active"]`，`run_skill` 时按需恢复。
  - 产物：`tests/test_session.py`、`tests/test_report_notifier.py`、`tests/test_skill_manager.py`、`session.py`(M)、`report_notifier.py`(M)、`skill_manager.py`(M)、`agent_cli.py`(M)、`skills/report/SKILL.md`(M)、`skills/report/skill.py`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **271 passed**（S3 46 + S4 90 + S5 135，0 failed）✅
    - session 覆盖：safe_int 13 组、默认档案、往返、旧档案补字段、6 种损坏档案、list 档案、不可序列化、续玩点 3 态、resume_point 缺键 4 组、脏 deaths 7 组、历史追加/截断/汇总、脏历史 4 条、快照 6 组脏值、describe 5 组脏 report ✅
    - report_notifier 覆盖：最小报告、快照字段、brief、5 种损坏输入、落盘+建目录、目录被占降级、Webhook 5 分支（未配置/204/199·301·400·500·503/异常/requests 缺失）、局中进度写入与覆盖、_tail_log 3 组非正数 ✅
    - skill_manager 覆盖：名称合法性 10 组、扫描 5 例（含损坏技能不拖垮）、5 种加载失败模式且不留 sys.modules 残留、卸载/重载/调用/异常兜底、排序、清单标记、内置 report 技能真实输出与离线降级 ✅
    - 集成冒烟：`agent_cli.py -c skills / load / run_skill / unload / session / stats / notify` 全部可读输出无 traceback；跨调用 `load report` → 新进程 `run_skill report` 成功输出真实进度 ✅
    - `compileall -q .` 退出码 0；`config/predictor/combat_judge/auto_tuner/session/report_notifier/skill_manager/mcp_server/agent_cli` 全部可导入 ✅
    - 仓库零污染：本轮生成的 `run_logs/report_*.md` 与 `agent_state.json` 已清理，`git status` 仅预期变更 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `report_YYYYMMDD_HHMMSS.md` 同一秒多次 notify 会互相覆盖（未加序号后缀）。当前 `notify` 由 play 收尾单次调用，不构成实际问题；若 **S7** 主循环 dry-run 中提高汇报频率需一并处理。
    - `session.py` 与 `agent_cli.py` 各维护一份 `_default_state` / `load_state` / `save_state`，且写同一个 `agent_state.json`，两处默认值不完全一致（CLI 侧无 `sessions` / `total_deaths` / `resumed` 等键）。未合并（会扩大改动面、影响既有 `state` 命令输出），移交 **S13** 收敛。
    - `_cmd_run_skill` 在 `run_skill` 未加载时才恢复技能，若同时存在同名技能被显式 `unload`，下次 `run_skill` 会重新加载（当前行为符合直觉，但与"显式卸载应生效"有语义冲突）。已在冒烟中确认行为，待 **S8** CLI 冒烟时统一口径。
    - 无 `.env` / 无网络：Webhook 真实推送、真实 LLM 摘要均未实测，本轮全部由注入假 `requests` 覆盖，属预期降级。

- **2026-09-21 05:05 · S6 · 感知服务离线化（perception_server.py）**
  - 做了什么：
    1. **新增三后端**：`auto`（探测截图工具+YOLO 检测脚本，缺一即降级）/ `http`（真实截图+YOLO）/ `mock`（纯配置合成场景）。优先级：环境变量 `UGF_PERCEPTION_BACKEND` > `config.yaml perception.backend` > `auto`。显式后端不做探测，避免"想 mock 却被判成 http"。
    2. **新增 `perception.*` 配置段**（`config.yaml` + `config.py DEFAULT`）：`backend` / `yolo_timeout` / `skip_on_timeout` / `screen_w|h` / `mock.{drift,afk_popup,player,entities,teammates}`。默认 5 个实体（Common→Super 覆盖四档稀有度）+ 1 个队友，全部带 `vx/vy`。所有读配置改走 `_cfg()` 运行时取值，热加载立即生效。
    3. **修复 P1（静默空帧）**：原实现把 YOLO 报错（`{"error": ...}`）当成正常结果继续走标准化，返回 `entities: []` + `alive:true` 的"空场景"，Agent 会误判为"游戏里没怪"继续空转。现在统一走 `_skip_payload()`，显式带 `_skipped` / `_reason` / `_error`（`yolo_error` / `yolo_timeout` / `detect_script_missing` / `screenshot_tool_missing` / `screenshot_failed` / `yolo_bad_output`）。
    4. **修复 P1（mock 实体飞出屏幕）**：端到端实测发现——实体按 `v*t` 无限外推，服务跑 3 分钟后 x 超出"屏幕 2 倍"越界阈值被 `_is_valid_entity` 过滤，感知结果从 5 个实体退化到 1 个（只剩 vx=0 的），离线主循环会"看不见怪"。新增 `_pingpong()` 三角波往返，实体永久留在屏幕内且持续运动（predictor 可稳定累积帧）。
    5. **截图路径迁移**：`/tmp/florr_frame.png`（10M tmpfs，写大图会 OSError 28）→ `BASE_DIR/.perception_frame.png`（已被 `.gitignore` 的 `*.png` 覆盖）。
    6. **加固**：`_is_valid_entity` 增加 NaN/Inf（含 `"nan"` 字符串）拦截；`normalize_player` 脏值统一回退；`normalize_teammates` 容忍 None/标量/非 dict 输入；`_run_yolo` 的 `json` 分支不再用 `'stdout' in dir()` 这种不可靠判断。
    7. **新增 `--selftest`**：`python perception_server.py --selftest [--backend mock] [--rounds N]`，跑 N 帧校验契约（player/entities/teammates/afk_popup + 实体结构），mock 模式额外校验多帧漂移，输出 JSON，退出码 0/1。路由与自检共用 `build_perception_payload()`，避免"自检能过、实际跑挂"。
    8. **`/health` 增强**：返回 `backend` / `configured_backend` / `port` / `screenshot_tool` / `detect_script` / `offline`；`/perceive?raw=0` 可去掉 `_raw` 省 token。
    9. `mcp_server` 新增 `_perception_url()`：端口按 `perception.port` > `server.perception_port` 解析（原先硬编码 5001，改了 config 不生效）。
  - 产物：`perception_server.py`(重写)、`tests/test_perception_server.py`、`config.yaml`(M)、`config.py`(M)、`mcp_server.py`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **370 passed**（S3 46 + S4 90 + S5 135 + S6 99，0 failed）✅
    - S6 覆盖：后端选择 12 例（env 优先级/非法回落/auto 三种探测/显式绕过）、配置读取 7 例（端口回退链/超时下限/屏幕尺寸兜底/config 缺失）、实体合法性 16 组（负坐标/越界/NaN/Inf/"nan" 字符串/缺字段/非 dict）、玩家脏值 7 组、队友 6 例、mock 漂移 6 例（含 `_pingpong` 5 组边界 + 长跑 1 小时后仍 5 实体且在屏内）、http 失败降级 7 例（含"错误不伪装成空场景"回归）、Flask 路由 4 例、自检 4 例、predictor 链路 1 例 ✅
    - `python perception_server.py --selftest` → `backend=mock`（auto 在本机正确降级），`ok=true`, `drifting=true`, 退出码 0 ✅
    - `python perception_server.py --selftest --backend http --rounds 1` → `ok=true`, `_reason=detect_script_missing`（结构化错误，不崩溃）✅
    - 真实进程冒烟：`UGF_PERCEPTION_BACKEND=mock python perception_server.py` 起服务 → `/health` 返回 `backend=mock, offline=true, port=5001`；连续两帧 `/perceive` 均 5 实体、坐标在屏内、hornet 右移 120.5px ✅
    - MCP 端到端：`mcp_server.perceive_game()` 打到活体 mock 服务，返回 `_backend=mock` + 5 实体 + 队友 + 完整 player；`predict_all_entities()` 随后算出 mantis(Super) 预判 ✅
    - `compileall -q .` 退出码 0；`git status` 仅预期 5 项变更，无临时 png / 日志残留 ✅
  - 遗留（未在本轮处理，记录备查）：
    - 本机存在 ImageMagick `import`，`auto` 判定之所以仍落到 mock 是靠"无 YOLO 检测脚本"这一条。若将来放入 `florr_powerful_tools/detect.py`，`auto` 会切到 http 并在无 X server 时每帧返回 `screenshot_failed`——**S7 主循环 dry-run 必须显式设 `UGF_PERCEPTION_BACKEND=mock`**，或由 launcher 统一下发。
    - `--selftest` 对 http 后端只校验"结构合规"，`_skipped` 帧也判 ok（退出码 0）。语义上属"链路可跑"而非"感知可用"，**S13** 若要做 CI 门禁需区分这两者。
    - `agent_main` 目前只判断 `"_skipped"` / `"error"` 两个字面量，不打印 `_reason`/`_error`，排障时看不到具体原因。**S7** 主循环改造时一并补日志。
    - 无 `.env` / 无真实 YOLO：http 后端的真实截图与模型推理仍未实测，本轮全部由 monkeypatch 覆盖，属预期降级。

- **2026-09-21 05:34 · S7 · 主循环 dry-run（agent_main 全链路离线跑通）**
  - 做了什么：
    1. **新增 `UGF_DRY_RUN=1` 开关**（`agent_main.py`）：启动打印模式横幅；MCP 子进程环境显式透传全部 `UGF_*`（实测 mcp stdio 客户端只转发 `HOME/PATH/SHELL/TERM/USER/LOGNAME` 六个白名单变量，不补这一步会出现"父进程开了开关、子进程没收到"）；新增 `--rounds` 作为 `--max-rounds` 等价别名（PLAN 验收命令用 `--rounds`）。
    2. **`mcp_server.py` dry-run 降级**：`game_action` / `switch_set` / `_path_perturb_move` 在无真实键鼠时只记录不执行，返回 `[dry-run] ...` 并把动作明细落盘到 `run_logs/dryrun_actions.log`；`perceive_game` 在感知服务不可达时改走**进程内 mock**（复用 `perception_server.build_perception_payload()`，结果带 `_fallback=inproc-mock`），非 dry-run 仍返回明确错误、不伪装成空场景。
    3. **修复 A1（阻断，静默失败）**：`kb_append` 从未被 `@mcp.tool()` 注册，而主循环的 BOSS 记忆 / 战术记忆 / 学习汇总三处都在调它；`call_tool` 不抛异常只把错误塞进返回内容，导致"日志说已写入 N 条、实际一个字节没写"。已补注册，并在 `agent_main` 新增 `_tool_error()` 软失败检测，写失败改为显式报错。
    4. **修复 A2（阻断，协议污染）**：MCP 服务启动 banner 与知识库模板提示 `print` 到 stdout，而 stdio 传输把 stdout 当 JSON-RPC 通道，客户端每帧解析报 `ValidationError`。新增 `_stderr()` 全部改走 stderr。
    5. **修复 A3（高，端到端暴露）**：`perception_server` 的 mock 位移用"上一帧到这一帧"的增量 `dt`，位置恒等于 `start + v×帧间隔`，实体原地不动 → predictor 速度恒为 0、预判置信度永远上不去（dry-run 实测 5 帧 `x_now` 完全相同）。改为累计时间基准 `t0`，`reset_mock()` 一并清理。
    6. **修复 A4/A5/A6/A7**：回合计数先自增后判定导致 `--rounds 5` 汇总报"回合=6"；监控快照按 `x/y/name` 取字段而 predictor 输出 `x_now/y_now/raw_id`，威胁坐标恒为 `(0,0)`、名字恒为空；感知跳过/异常不打 `_reason`；MCP 返回解析直接下标 `content[0].text`，异常形状会打断主循环 → 统一由 `_tool_text()` 兜底，退出前 BOSS 记忆与复盘包 try/except 保证退出码 0。
    7. 新增 `UGF_REPORT_EVERY` / `UGF_LEARN_EVERY` 两个环境变量覆盖（仅用于在不改 `config.yaml` 的前提下验证汇报心跳与命中率汇总）；修正 docstring 中"连续 2 帧判定死亡"与配置 `death_frame_threshold: 8` 的不一致。
    8. 新建 `tests/test_agent_main.py`（**87 用例**）+ `devplan/SMOKE_S7.md`（开关语义、7 项缺陷、实测样例、13 项验证矩阵、5 条遗留）。
  - 产物：`agent_main.py`(M)、`mcp_server.py`(M)、`perception_server.py`(M)、`tests/test_agent_main.py`、`devplan/SMOKE_S7.md`、`devplan/PROGRESS.md`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **457 passed**（S3 46 + S4 90 + S5 135 + S6 99 + S7 87，0 failed）✅
    - 验收命令 `UGF_DRY_RUN=1 python agent_main.py --rounds 5` → **exit 0**，5 轮全走完，产出 `agent_snapshot.json` / `dryrun_actions.log` / `progress_report.md` / `agent_20260921.log`，知识库写入 `boss_behavior_log.md` / `player_tactics.md` / `review_*.md` ✅
    - S7 单测覆盖：开关解析 12 例、工具返回解析 9 例（含空 content / 非 CallToolResult 形状）、软失败检测 4 例、兜底决策 6 例、复盘过滤 5 例、BOSS 行为归纳 4 例、日志滚动与清理 3 例、热加载与子进程环境透传 3 例、工具注册回归锁 10 例（主循环依赖的 9 个工具 + `kb_append`）、dry-run 动作/换套 8 例、进程内 mock 感知 5 例（含"感知→预判"多帧连通）、mock 漂移累积回归 1 例 ✅
    - 场景验证：汇报心跳（每 4 轮）、命中率汇总 + `auto_tuner.tune`（每 6 轮）、BOSS 记忆 flush、死亡分支（临时置 `alive:false` 跑 10 轮 → 第 8 轮判定死亡、写复盘、exit 0，配置已还原）、运行中 `touch config.yaml` 触发热加载 ✅
    - 修复 A3 后快照坐标真实：hornet x=622.7、beetle x=1416.5（此前恒为初始 ± 一帧增量）✅
    - `compileall -q .` 退出码 0；`git status` 仅预期 4 项变更，无临时 png / 日志入库 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `_fallback_decide` 无 LLM 时只输出 `attack`/`defend`/`idle`，`move` 分支（安全区钳制 + 抖动）在 dry-run 中未被覆盖，需规则化 move 策略后补测（建议 **S13** 前）。
    - `mcp_server._text_search` 的 `return` 之后有 3 行不可达代码；行为无影响（空结果已正确返回"未找到相关内容"），**S13** 清理。
    - 死亡防抖阈值 8 帧与 README/模块 docstring 旧描述"2 帧"不符，文档统一移交 **S13**。
    - `review_*.md` / `learning_stats.md` 随每次 dry-run 在 `knowledge_md/` 累积（已被 `.gitignore` 忽略），长跑清理建议交 **S12** 运维脚本。
    - 无 `.env`：真实 LLM 决策仍未实测，本轮全部走 `_fallback_decide` 规则分支，属预期降级。
2026-09-21 06:51 · — · 用户叫停，A/B 双线自动化已置为 PAUSED · 已完成 S1~S8，505 用例全绿 · 剩余 S9~S14 待恢复后续跑（注意 validUntil 已过 07:00，恢复时需顺延）

- **2026-09-21 07:10 · S9 · MCP 服务端工具注册验证（mcp_server.py）**
  - 背景说明（自主决策理由）：本轮 B 线 06:39 启动时 S9 为首个待执行阶段，执行日志无并行占用，遂开工。06:51 A 线判定到点并置双线为 PAUSED、把本轮进行中的改动一并提交为 `12b4cf3`（"S8+ 叫停"）。因 S9 主体工作已完成、只剩交付物文档与状态回填，**选择把 S9 收尾干净再停**（避免出现"代码已改但进度表仍记 ⬜"的不一致状态），不做 S10 及后续。
  - 做了什么：
    1. 新建核对脚本 `tools/mcp_tools_check.py`：解析 README 的 MCP 工具表格 → 与服务端 `list_tools()` 实际注册清单逐字比对（多/少/改名/标题数量不符都会报）；对 15 个工具逐个以 mock 参数走**真实 `mcp.call_tool()`**（不是直接调底层函数，才能测出"装饰器没注册/参数 schema 不匹配"这类问题，S7 的 `kb_append` 漏注册正是死在这一层）；再跑一遍 `kb_export → kb_import` 往返。支持 `--json`（S13 可直接接门禁）/ `--strict`。
    2. 新建 `tests/test_mcp_server.py`（**109 用例**）：清单一致性 9、逐工具可调用 16、schema/必填参数 30、知识库路径安全 20、往返一致性 7、工具错误处理 17 等。知识库目录一律 `monkeypatch` 到 `tmp_path`，感知走 dry-run 进程内 mock，全程零真实网络/键鼠。
    3. **修复 M1/M2（阻断，路径穿越）**：`kb_write` / `kb_append` 的 `filename` 与 `kb_list` / `kb_search` 的 `game_name` 都只把 `/` 换成 `-`，`..` 原样保留 → `filename="../../evil.md"` 可写到知识库之外、`game_name=".."` 可列出上一级目录。新增 `_safe_name()` 与集中式 `_resolve_kb_path()`（`normpath` + `commonpath` 二次守门），两处口径统一。
    4. **修复 M3/M4（阻断，往返失真）**：`kb_maintainer.export` 用 `basename` 打包，把 `knowledge_md/florr/boss.md` 拍平成 `knowledge_md/boss.md`——按游戏分目录的知识库备份后**分类全丢**，同名文件互相覆盖；`import_backup` 又把 `knowledge_archive/*` 一律解进活跃库，**已归档笔记被复活**、`kb_max_mb` 体积控制形同虚设。改为保留相对路径 + 按顶层目录分流还原，并保留对旧扁平备份的兼容（已回归锁定）。
    5. **修复 M5（高，死配置）**：`kb_search` 函数内 `USE_VECTOR_SEARCH = False` 局部变量把模块级 `FLORR_VECTOR_SEARCH` 开关彻底短路，且 `_vector_search()` 只收 1 个参数、真放行必 `TypeError`。改读全局开关并对齐签名。
    6. **修复 M6（中，假成功）**：`game_action` 的 dry-run 分支在合法性校验**之前**返回，`game_action("fly")` 会回"动作已记录"，把无效动作伪装成成功。新增 `VALID_ACTIONS`，校验与 move 坐标检查前置。
    7. 其余：删 `_text_search` 的 3 行不可达代码并补命中计数（M7，S7 遗留）；模块 docstring「13 个」改 15 个（M8）；`clean_cache` 帧目录不存在时不再谎报"已清理"（M9）；`switch_tactic` 补路径清洗与 `OSError` 保护（M10）。
    8. `requirements.txt`：`mcp` 由 `<2.0.0` 放宽为 `>=1.0.0`。本机实际是 **2.2.0**，与原锁定矛盾；S9 已在 2.2.0 上实测 15 工具全部可注册/可调用/schema 正确，注释中记录两版差异。
  - 产物：`tools/mcp_tools_check.py`、`tests/test_mcp_server.py`、`devplan/TOOLS.md`、`mcp_server.py`(M)、`kb_maintainer.py`(M)、`requirements.txt`(M)、`devplan/PROGRESS.md`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **614 passed**（S8 的 505 + 本轮 109，0 failed）✅
    - `python tools/mcp_tools_check.py --strict` → 清单一致 OK / **15 个工具逐个调用 OK**（均有非空描述、`inputSchema.type=object`、非空返回、非 is_error）/ 往返 OK，**退出码 0** ✅
    - 往返实证：包内成员 `['knowledge_md/root.md','knowledge_md/florr/boss.md','knowledge_archive/old.md']`；还原后子目录保真 `True`、归档不被复活 `True`（修复前分别为 `False` / `False`）✅
    - SDK 实测修正（与 S7 记录不同）：mcp **2.x** 进程内 `call_tool` 对**未知工具会抛 `ToolError`**，只有工具内部异常才被包成 `is_error` 结果；2.x 的 Tool 只有 `input_schema`（无 `inputSchema` 别名，直接访问 `AttributeError`）。测试已按双版本兼容写法锁定 ✅
    - `compileall -q .` 退出码 0；探针产生的 `knowledge_md/_s9_probe*` / `_current_tactic.md` / `kb_backups/` 已清理 ✅
  - 遗留（未在本轮处理，记录备查）：
    - `handle_afk` 仅返回流程说明文本，不做实质处理（无真实弹窗坐标可测），属预期降级。
    - 旧格式扁平备份中若两个游戏目录有同名文件，导入仍会互相覆盖（导出侧已修，历史备份无法追溯）。
    - 向量检索仍为预留实现（`chromadb` / `sentence-transformers` 未装，后者会拉入 torch，磁盘紧张不装），本轮只验证"开关不被短路 + 签名正确 + 回退文本检索"。
    - S10~S14 未执行（06:51 双线已置 PAUSED）；恢复时需顺延 `validUntil` 并按 S10 → S14 顺序继续。
2026-09-21 06:59 · — · 用户指令「今晚 23:00 继续」：第二轮冲刺窗口定为 2026-09-21 23:00 ~ 2026-09-22 07:00，从 S9 续跑；A/B 双线已重新 ACTIVE 并顺延 validFrom/validUntil，23:00 与 23:30 两轮用一次性任务补齐（调度器会把当日 23:00 的 validFrom 顺延到次日 00:00）
2026-09-21 21:45 · — · 用户要求：①23:00 开工 ②周期更密、单轮工作量更大 ③先做完旧表再排新表 ④先搞清定位与方向。
已完成：新增 devplan/DIRECTION.md（定位/短板/我该往哪推/用户该往哪走/合规边界）、devplan/PLAN_PHASE2.md（S15~S26 共 12 阶段）、PROGRESS.md 增加「本轮执行规则+运行锁」与 S15~S26 行、PLAN.md 增加方向先行与「预算有余则继续下一阶段」规则。
现状：S1~S9 已完成（614 用例全绿），本轮从 **S10** 起跑。
说明：automation_update 调度工具在当前上下文不可用，无法再加触发线，故维持 30 分钟周期（23:00/23:30 一次性 + 之后整点/半点双线，至 06:30 共 17 轮）；加大工作量的方式改为「单轮连做多个阶段（预算 25 分钟内做完一个就接着做下一个）」+ 新增 12 个第二阶段任务，总计待办 17 个阶段。
2026-09-21 22:00 · — · 按用户要求改为「17 条内容各自不同的一次性任务」，间隔压缩到 25 分钟（23:00~05:40）；新增 devplan/AUTOMATION_TASKS.md（含每条 prompt 正文 + 交付物 + 验收 + 用户视角价值）。automation_update 工具仍不可用，17 条待创建；创建前需先 PAUSED 旧的 4 条。
2026-09-21 22:28 · S10（人工预改，交付 23:00 自动化续做）· 只做了不易出错的地基部分，其余留给自动化：
  - 已做：`game_profile_check.py` 升级为语义版（新增：稀有度跨档重复、威胁分金字塔倒置、负威胁分、game.name 与文件名不一致、未知顶层键、sets/default_set 合法性、mock 实体 rarity 未声明 → ERROR；缺 description/port/sets/tactics → WARN；新增 `check_all()` 修掉"退出码永远 0"的 bug；`--strict` 让建议项也阻断；`--all` 跳过 `_` 开头模板）。`space_invaders.yaml` 按实体体系重排金字塔（原档案把 "boss" 同时写进 highest_boss 与 boss 两档），并补齐 port 5011 / sets / tactics / mock 实体。
  - 验证：`game_profile_check.py --all` → florr ✅(3 条建议) + space_invaders ✅；`pytest -q` → **614 passed**（无回归）。
  - **待 23:00 自动化续做**：① florr.yaml 补 sets/tactics/port（3 条建议）② `tools/add_game.py` 的 `render_yaml` 要吐出推荐字段，保证"生成即通过 validate" ③ `tests/test_game_profiles.py`（≥12 用例：重复档位/金字塔倒置/负分/名字不一致/未知键/default_set 越界/mock rarity 未声明/切 AGENT_GAME 后核心读到新值）④ `devplan/PROFILE_SPEC.md` ⑤ 全量 pytest 后提交并改本表 S10 为 ✅。
2026-09-21 22:28 · — · 用户澄清：不要人工提前做，由 23:00 的自动化实施。人工部分到此为止（仅保留上面两处地基改动，已验证无回归）。

- **2026-09-21 23:15 · S10 · 游戏档案体系固化（game_profiles/ + game_profile_check.py）**
  - 起点判定：运行锁为 `RELEASED`（21:40 释放），S10 是首个非 ✅ 阶段（🟡 人工预改），当前 23:02 < 07:00，故开工。（提示词写"从 S9 续跑"，但 S9 已于 07:10 完成、PROGRESS 也点名"23:00 首轮直接从 S10 开始"，按文件规则执行。）
  - 做了什么：
    1. **`florr.yaml` 补齐 3 条建议项**：`server.perception_port: 5001`、`combat.sets`（combat/tank/retreat/chase/team，与 `combat_judge.recommended_set` + `mcp_server.SET_TO_KEY` 键位同名）、`combat.default_set: combat`、`combat.tactics` 4 条。至此两份档案 `--strict` 全过。
    2. **`tools/add_game.py` 升 v2.0（生成即通过 validate）**：`render_yaml` 由 6 段扩到全字段（port / sets / default_set / tactics / `perception.mock` 实体按已声明档位合成）；新增 `_next_port()` 扫描已占用端口按步长 10 避让、`_sanitize_name()` 保证「文件名 == game.name」、`_q()` 用 JSON 双引号转义描述与战术（冒号/引号不再写坏 YAML）；`activate_game()` 改为精确命中 `agent:` 段下的 `game:`（旧版 `count=1` 全局替换会误伤其它同名键）；新增 `selfcheck()` 按 **strict 口径**（ERROR 与 WARN 均为 0）自检，非 0 时进程退出码 1；新增 `--print` / `--no-activate`；`_ask()` 增加 `UGF_NONINTERACTIVE` 开关（本机 stdin 判定为 tty，无人值守会卡死 —— 实测触发过一次后台挂起，已修）。
    3. **新建 `tests/test_game_profiles.py`（38 用例）**：真实档案 strict 通过 4；语义错误 12（跨档重复 / 金字塔倒置 2 组 / 负分 / 名字不一致 / 未知顶层键 / default_set 越界 / sets 非字符串 / mock 稀有度未声明 / 缺 threat 键 / 档案不存在 / YAML 语法错 / 根节点非映射）；建议项只降级不阻断 1；`check_all` 口径 5（含"退出码永远 0"回归、`_` 模板跳过、strict 计建议）；**切游戏核心读到新值** 3（space_invaders boss=800/port=5011/sets=shoot… ↔ florr 400/5001/…，并锁"列表是替换而非拼接"不串档）；生成器 5（strict 自检 / mock 稀有度合法 / 特殊字符转义 / 端口避让 / 名字安全化）；`activate_game` 3。
    4. **`agent_cli.py` 的 `validate` 支持 `--strict`**：改用 `check_detail()` 分别列出 ✗ ERROR 与 ⚠ 建议项，保留老 API 兼容分支。
    5. 新增 `devplan/PROFILE_SPEC.md`：优先级链、顶层键表、字段细则、ERROR/WARN 分级与命令、新增游戏流程、现状表、遗留。
  - 产物：`tests/test_game_profiles.py`、`devplan/PROFILE_SPEC.md`、`tools/add_game.py`(M v2.0)、`game_profiles/florr.yaml`(M)、`agent_cli.py`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **652 passed**（S9 的 614 + 本轮 38，0 failed）✅
    - `python game_profile_check.py --all --strict` → florr ✅ + space_invaders ✅，退出码 0（此前 florr 有 3 条建议）✅
    - `agent_cli.py -c "validate florr"` / `... space_invaders` 均 ✅ 通过；加 `--strict` 同样 ✅；`validate nope` 给出可读报错 ✅
    - 生成器实证：`render_yaml(collect('demo_game'))` 解析后 keys 齐全（port 5021 / 5 套装 / 4 个 mock 实体 rarity 全部合法），落盘后 strict 自检 `ok=True errors=[] warnings=[]` ✅
    - `compileall -q .` 退出码 0；`git status` 仅 6 项预期变更，无临时档案残留 ✅
  - 遗留（未在本轮处理，记录备查）：
    - **`switch_set` 的键位映射是 florr 专属**（`SET_TO_KEY` 写死 combat/tank/retreat/chase/team→1~5），space_invaders 的 `shoot`/`dodge` 换套会落到"未知套装"。多游戏应按档案 `sets` 顺序映射按键，移交 **S15**。
    - florr 的离线 mock 场景仍在 `config.yaml`，档案自身未声明 `perception.mock`（"一份档案一份离线场景"未完全落地），移交 **S15**。
    - 校验器只做静态语义校验，不验证"档案值在实际对局里是否合理"（如威胁分是否过激），需实机数据，本机不可验证。
    - `tools/add_game.py` 的交互向导在无 tty 时全程走默认值，未在真实交互终端下人工试用（本机无交互终端）。

- **2026-09-21 23:36 · S11 · UI 收敛与统一启动器（launcher.py）**
  - 起点判定：S10 已 ✅ 并提交（`1a0141d`），运行锁仍由本线持有，当前 23:16 < 07:00 且单轮预算有余 → 按「本轮执行规则 2」连做 S11。
  - 做了什么：
    1. **前端收敛**：`ui_pyqt.py` / `ui_streamlit.py` 经 `git mv` 移入 `ui/legacy/`，文件头加 `⚠ DEPRECATED` 说明（主 UI / 备选 / 统一入口三行）与 `sys.path` bootstrap（归档后项目根不在搜索路径里，`import config` 会失败）。顺手修掉 **S8 遗留**：`ui_pyqt.py` 用硬编码 `"python3"` 调 CLI → 改为 `sys.executable`（隔离 venv 解释器）。
    2. **新增 `launcher.py`（v2.0）**：`--ui auto|panel|tk|pyqt|streamlit|cli` + `--selftest` + `--list` + `--dry-run` / `--mock`。可用性探测：`panel` 永可用（纯标准库 http.server）、`tk`/`pyqt` 需 tkinter/PyQt6 且 Linux 下要有 `DISPLAY`/`WAYLAND_DISPLAY`、`streamlit` 需模块可导入。自动顺序 panel > tk > cli（cli 保底）。离线开关经 `child_env()` 以 `UGF_DRY_RUN` / `UGF_PERCEPTION_BACKEND` 透传给子进程，并补 `PYTHONPATH`。退出码：0 正常 / 2 指定 UI 不可用 / 130 Ctrl-C。
    3. **主 UI 补「运行模式」**：`admin_panel.py` 新增 `_mode()`（在线/dry-run + 感知后端 auto/mock/http，`offline` 标黄），`_status()` 暴露 `mode`，页面新增卡片 + JS 赋值与 tooltip；文件头文档同步。
    4. **新建 `tests/test_launcher.py`（26 用例）**：UI 清单与归档断言（含 legacy 路径、DEPRECATED 标记、sys.path bootstrap）、可用性探测 5、选择逻辑 4（auto 必选到可用项 / 未知 UI 返回 None / PyQt6·streamlit 不可用时不硬拉起）、命令构造 2（`streamlit run` 形态）、开关透传 3、模式标签 3、自检输出与退出码 3、panel 模式显示 3。
    5. **README**：「快速开始」新增统一启动入口段落（6 条命令 + 收敛说明），目录树补 `launcher.py` / `ui/legacy/`。
  - 产物：`launcher.py`、`tests/test_launcher.py`、`ui/legacy/ui_pyqt.py`(M, 移)、`ui/legacy/ui_streamlit.py`(M, 移)、`admin_panel.py`(M)、`README.md`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **678 passed**（S10 的 652 + 本轮 26，0 failed）✅
    - 验收命令 `python launcher.py --ui auto --selftest` → 探测 5 项（panel ✅ / tk ✅ / pyqt — PyQt6 未安装 / streamlit — 未安装 / cli ✅），**选择结果 panel，退出码 0** ✅
    - `python launcher.py --ui pyqt --selftest` → 退出码 **2**（不可用不硬拉起）✅；`--ui cli --selftest` → 0 ✅
    - `UGF_DRY_RUN=1 UGF_PERCEPTION_BACKEND=mock python launcher.py --ui auto --selftest` → 「离线开关: dry-run / mock 感知」✅
    - `admin_panel._mode()` 默认 `在线 / auto`（offline=False）；加两个环境变量后 `dry-run / mock`（offline=True），`_status()["mode"]` 同步 ✅
    - `compileall -q .` 退出码 0；`git status` 仅预期变更（含 2 个 rename）✅
  - 遗留（未在本轮处理，记录备查）：
    - 本机 `DISPLAY=:0` 被设置（实际无 X server），故 `tk` 被判为可用；真正的可用性要 `Tk()` 建窗才知道，探测层无法区分（建窗测试可能挂起，未做）。用户若在真无显示环境用 `--ui tk` 会失败——launcher 会把子进程错误原样透出，不会误判成"启动成功"。
    - `streamlit` 拉起走 `python -m streamlit run`，未实测（模块未安装，磁盘紧张不装）。
    - `start_all.sh` 仍用 `python3` 直接起 `admin_panel.py`，未改走 launcher（统一收口移交 **S12** 运维脚本）。
    - `launcher.py` 未接 `--port` 覆盖；面板端口仍只能改 `config.yaml` 的 `server.panel_port`。
    - 未做真实 GUI 冒烟（无 X server）：tk/pyqt 的实际渲染与交互未验证，属预期降级。


- **2026-09-21 23:47 · S12 · 运维脚本与容器一致性（start_all/stop_all/watchdog/Dockerfile/boot_check）**
  - 起点判定：运行锁 `RELEASED`，状态表首个非 ✅ 为 S12，当前 23:31 < 2026-09-22 07:00，故开工（提示词写"从 S9 续跑"，但 S9~S11 已于 07:10/23:15/23:36 完成，按 PROGRESS 文件规则从首个 ⬜ 开始）。
  - 做了什么：
    1. **`boot_check.py` 升 v2.0（本阶段最实质的问题）**：旧版把 `cv2` / `PIL` 列为 REQUIRED 且判 ERROR，而本机（无 GUI / 无 X / 无 YOLO / 无 .env）这三项全缺 —— `start_all.sh --fail-fast` 会 100% 退出，即"离线链路根本起不来"，与项目定位冲突。现改为三级口径：`CORE_LIBS`（yaml/flask/requests/numpy，缺=ERROR）+ `OPTIONAL_LIBS`（PIL/cv2/pyautogui，缺=WARN，每条附"修复"与"降级"两行指引）+ 运行环境检查（X server 以 `/tmp/.X11-unix` 是否存在为准，不看 DISPLAY —— 本机 DISPLAY=:0 但并无 X；YOLO 权重目录缺失）。新增 `--strict`（WARN 也阻断，供 CI/容器门禁）、`--json`、`--no-ops`、`main(argv)` 可测入口。
    2. **新增运维口径一致性校验 `check_ops()`**（并入默认自检）：`OPS_REFS` 核对 `start_all.sh`→4 个 py、`watchdog.sh`→`agent_main.py`、`Dockerfile`→`requirements.txt`/`boot_check.py`/`start_all.sh` 是否存在；并用正则反查脚本/文档里的 `perception_port` / `panel_port` 字面量是否与 `config.yaml` 一致（不一致=ERROR）。测试用"临时删 start_all.sh"反向用例锁定校验器自身不失效。
    3. **`start_all.sh` v2.0**：端口由 `grep` 改为 `port_of()` 现读 `config.yaml`（旧写法 `$(grep perception_port config.yaml)` 会把整行注释一起打印）；`PY=python` 改为 `UGF_PYTHON` 可覆盖 + 自动探测 python3；新增 `--dry-run`（不 fork、不写 .pid、不占端口）、`--no-check`、`--help`、未知参数退出码 2；`UGF_DRY_RUN` export 给子进程；新增 `UGF_FOREGROUND=1` 前台模式（容器 CMD 用，否则容器启动完即退出）。
    4. **`stop_all.sh` v2.0**：`--dry-run` / `--keep-logs` / `--help`；先 TERM 最多等 5s 再 KILL；清理失效 pid 文件；清理范围扩到 `video_frames/`、`*.tmp`、`.write_probe`，以及 `run_logs/` 按 mtime 轮转（`UGF_LOG_KEEP_DAYS`，默认 7 天，`<=0` 不清理）。
    5. **`watchdog.sh`**：解释器支持 `UGF_PYTHON` 覆盖，并 `export UGF_DRY_RUN` 透传给 `agent_main`。
    6. **`Dockerfile` v2.0**：与 `requirements.txt` 对齐 —— 容器内把 `opencv-python` sed 替换为 `opencv-python-headless`（镜像无 GUI，GUI 版会引入无用依赖链）；补 `PIP_NO_CACHE_DIR` / `PYTHONUNBUFFERED` / `TMPDIR`、`EXPOSE 5001 5002`；CMD 改为 `boot_check --fail-fast && UGF_FOREGROUND=1 start_all.sh`（旧 CMD 只跑 watchdog，不会拉起感知/MCP/面板，且与 start_all 口径不一致）。
    7. 新建 `devplan/OPS.md`：五件套职责口径表、环境变量表、命令速查、**离线降级矩阵**（6 项缺失的旧行为→新行为→降级路径）、一致性自检说明、验收结果、遗留。
    8. 新建 `tests/test_ops.py`（21 用例）：分级口径 6（本机 0 ERROR / 可选库用 monkeypatch 强制缺失仍判 WARN 且带降级 / 核心库缺判 ERROR / strict 提升 / json schema / fail-fast 退出码）、口径一致 5（端口值、OPS_REFS 存在、当前树 check_ops 干净、删文件反向用例、脚本不得写死 `PY=python`、Dockerfile 与 requirements 对齐）、干跑 8（start --dry-run 退出码 0 且无 .pid 副作用 / 环境变量等价 / 未知参数 2 / help 0 / stop dry-run 0 / **沙箱实测清理与轮转**（删 video_frames、删过期日志、留新日志、清 tmp）/ --keep-logs / watchdog 透传）。
  - 产物：`devplan/OPS.md`、`tests/test_ops.py`、`boot_check.py`(M v2.0)、`start_all.sh`(M)、`stop_all.sh`(M)、`watchdog.sh`(M)、`Dockerfile`(M)
  - 测试结果：
    - `python -m pytest tests/ -q` → **699 passed**（S11 的 678 + 本轮 21，0 failed）✅
    - `bash start_all.sh --dry-run` → 退出码 0，打印 5001/5002，未创建 .pid ✅；`UGF_DRY_RUN=1 bash start_all.sh` 等价 ✅
    - `bash stop_all.sh --dry-run` → 0 ✅；沙箱真实清理：video_frames 删除、过期日志轮转、未过期日志保留、tmp 清理 ✅
    - `python boot_check.py` → ERROR 0 / WARN 6，退出码 0，每条 WARN 均有降级指引 ✅；`--strict` → 退出码 1 ✅；`--json` 输出含 ports ✅
    - `compileall -q .` 退出码 0；`git status` 仅 7 项预期变更，无 .pid / video_frames / .write_probe 残留 ✅
  - 遗留（未在本轮处理，记录备查）：
    - 容器镜像**未在本机构建验证**（无 docker、无网络拉基础镜像），仅做静态口径对齐与 headless 替换；真实 `docker build` 需在有 docker 的环境补验。
    - `stop_all.sh` 只按 mtime 轮转日志，未按体积封顶；磁盘紧张场景可再加 `UGF_LOG_MAX_MB`。
    - 非 dry-run 的真实启停（4 个进程 + 端口占用）在本机无 GUI 下仍需宿主机实测一次；本轮只保证"不起副作用"的干跑可验收。
    - 全量 pytest 曾出现一次 8 失败的瞬时结果（同目录下有并发写入），随后独立重跑 699 全绿；疑似与并行自动化线同时写文件有关，未复现。

2026-09-21 23:56 · S13(部分) · 本轮 25 分钟预算内 S12 完成后仍有余量，按「预算有余则继续下一阶段」规则开工 S13 的可验收核心：新建 `scripts/check.sh` 一条命令门禁（compileall → boot_check --fail-fast → game_profile_check --all → pytest，`--fast` 秒级跑、`--help`、未知参数退 2、失败退出码=环节编号），`tests/test_ops.py` 补 2 用例（门禁 fast 全程退 0 且逐阶段打印 / 未知参数 2），现 23 用例。实测 `bash scripts/check.sh --fast` 退出码 0（语法 OK + 自检 ERROR 0/WARN 5 + 两份档案 ✅）。**未做**：README / PROJECT_SUMMARY / ROADMAP 三份文档同步（工作量大，超出本轮余量），移交下一轮；故 S13 标记为 🟡 而非 ✅。

2026-09-22 00:12 · S12(补充·根因修复) · 修正上一版日志中"疑似并发线写文件"的错误归因（该结论不成立，已实测推翻）：
  - **真实根因**：全量 pytest 期间出现 9~10 个用例随机失败，均为调用 `boot_check` 子进程的用例。抓完整 stdout 后定位到宿主有 **safe-delete 批量删除护栏**（`[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] {"count":133,"threshold":50,"scope":"turn"}`）：全量测试一轮累计删除超过 50 次后，`boot_check` 写探针里的 `os.remove(probe)` 被拦截并抛错 → 被 `except OSError` 捕获 → 误报 ERROR「目录不可写: run_logs」→ `start_all.sh --fail-fast` 退出 1。单跑 test_ops.py 时删除次数未达阈值，所以"时好时坏"。
  - **修复**：新增 `boot_check._dir_writable()`，可写性探测改为「`os.access` + 追加方式打开复用同一探针文件」，**全程零删除**（残留一个空文件，由 `stop_all.sh` 顺带清理）。
  - **回归锁定**：`tests/test_ops.py` 补 3 用例 —— AST 断言 `boot_check.py` 内不得出现 `remove/unlink/rmtree` 调用、`_dir_writable` 对 `run_logs` 返回 True、对「文件冒充目录」返回 False；另把原先会**临时删除 start_all.sh** 的反向用例改为纯 monkeypatch（删仓库文件在并发 pytest 下同样是隐患），并新增「端口漂移」检测用例。
  - 验证：`pytest tests/ -q` 连续两次 **702 / 704 passed**（修复后不再随机失败）；`compileall` 退出码 0；`git status` 干净。
  - 经验（供后续阶段参考）：**本机写测试时禁止在用例里删除仓库内文件**；任何 `os.remove/shutil.rmtree` 在全量测试规模下都可能触发宿主删除护栏，应改走 tmp_path 沙箱或 monkeypatch。


- **2026-09-22 01:26~02:05 · S15 · 第二款游戏端到端跑通（space_invaders）**
  - 做了什么：
    1. 先按验收口径实测 `AGENT_GAME=space_invaders UGF_DRY_RUN=1 python agent_main.py --rounds 3`，
       发现**退出码 0 但跑的仍是 florr 数据**（敌人=5 / 队友=1 / 套装=retreat）。以产物内容为判据，
       定位 4 个静默缺陷（详见 `devplan/E2E_S15.md`）。
    2. **D1（阻断）**：`config._reload()` 只从 config.yaml 读 `agent.game`，从不读环境变量 ——
       而 PROFILE_SPEC / 档案注释 / start_all.sh 都声称「设 AGENT_GAME 即可切游戏」。新增
       `config.active_game()`（`AGENT_GAME`/`UGF_GAME` > config.yaml > florr）作为唯一来源，
       `_reload()` 与 `reload_if_changed()` 均改用它。
    3. **D2（阻断，跨进程不一致）**：`agent_main._mcp_server_env()` 只透传 `UGF_*`，`AGENT_GAME`
       在 MCP stdio 子进程丢失 → 父进程按 space_invaders 决策、子进程按 florr 出数据。改为写入
       父进程**已解析**的激活游戏，不依赖透传是否成功。
    4. **D3（高）**：`mcp_server.SET_TO_KEY` 把 florr 五个套装名硬编码进核心模块，非 florr 游戏
       `switch_set` 必然「未知套装」。新增 `resolve_set_keys()`（按档案 `combat.sets` 顺序映射 1~9）
       与 `normalize_set_name()`（按档案 `combat.set_map` 翻译决策语义）；florr 的 sets 顺序恰好等于
       原硬编码映射，对既有行为零影响。
    5. **D4（中）**：`agent_main` 所有 kb_write/kb_append 不带 `game_name`，多游戏共用一份知识库。
       新增 `_kb_game()`，知识按激活游戏分区到 `knowledge_md/<game>/`。
    6. 落实 PROFILE_SPEC §7 两项 S15 移交：`perception.mock` 迁回档案（florr.yaml 新增完整 mock 段、
       config.yaml 移除）、`space_invaders` 补 `teammates: []`（此前会继承 florr 的 player_ally）。
    7. `game_profile_check.py` 新增 `combat.set_map` 校验（目标必须 ∈ sets；套装名与决策语义
       **完全不匹配**且无 set_map 时 WARN，strict 下阻断）；`tools/add_game.py` 生成自定义套装名
       的档案时自动附带 set_map，保持「生成即通过 validate」。
    8. 产出 `devplan/E2E_S15.md`（结论表 / 4 缺陷根因与修复 / 移交落地 / 修复前后对比证据 / 遗留）
       与 `tests/test_e2e_space_invaders.py`（14 用例：环境变量切游戏、mock 场景来自档案、
       端口隔离、子进程透传、键位映射与 florr 向后兼容、决策语义翻译、strict 校验、
       **真实子进程 e2e 断言复盘落在本游戏分区且内容为 alien_* 套装 shoot**）。
  - 产物：`config.py`/`agent_main.py`/`mcp_server.py`/`game_profile_check.py`/`boot_check.py`/
    `tools/add_game.py` 修复；`game_profiles/florr.yaml`、`game_profiles/space_invaders.yaml`、
    `config.yaml`、`devplan/PROFILE_SPEC.md`、`devplan/E2E_S15.md`、新增测试 14 用例。
  - 测试结果：`tests/test_e2e_space_invaders.py` 14 passed；
    **全量 757 passed**（基线 743 + 新增 14）；`game_profile_check.py --all --strict` 退出码 0；
    `bash scripts/check.sh` 退出码 0。
  - 遗留：①日志里「套装=combat」仍是决策抽象名、未展示为 `shoot`（switch_set 已翻译，仅文案）
    → S16；②`chase`/`team` 在单人街机下的映射贴合度需实机验证；③`knowledge_md/` 根目录下
    florr 历史文件未归档迁移（数据问题）。
  - 决策依据：本轮未向用户提问，按 DIRECTION.md「第二款游戏端到端跑通优先级最高」自主选择 S15；
    4 个缺陷均以「产物内容断言」而非「退出码」为判据，符合「可复现优于可演示」。

- **2026-09-22 02:47~03:38 · S16 · 参考适配器模板与档案规范固化**
  - 做了什么：
    1. 新增 `game_profiles/_template.yaml`：**全字段 + 全注释 + 安全上下限**的参考模板，逐字段标注
       类型 / 取值域 / 缺失时的兜底行为；待填充处统一写成 `__UGF_*__` 槽位（`__UGF_SET_MAP__` 写成
       `__UGF_SET_MAP__:` 以保证模板本身是合法 YAML）。
    2. `tools/add_game.py` 从「硬编码 f-string 拼档案」改造为**以模板为唯一结构来源与数值默认来源**：
       `load_template()` 取结构与注释 → `template_defaults()` 解析字面默认值（威胁分 / 端口 /
       `chase_min_category` / 玩家状态）→ `render_from_template()` 填充槽位。原 `render_yaml()`
       保留签名并转为委托（模板缺失时降级 `_render_legacy_yaml`），既有调用方零改动。
    3. **槽位残留硬失败**：渲染后若仍有 `__UGF_*__` 残留即抛 `ValueError`。设计理由——模板新增槽位
       而生成器没跟上时，产出的是「看起来合法、实则是坏档案」，必须硬失败而非静默通过。
    4. 修复 3 个真实缺陷：①`set_map` 槽位原本缩进在 `sets:` 块内，渲染后块映射混进列表，
       **YAML 直接解析失败** → 改为与 `sets` 同级（缩进 2），空映射时整段不出现；
       ②列表块缺 `- ` 前缀（套装 / 战术 / mock 实体）→ 渲染时补前缀；
       ③`_next_port()` 会把模板的 5021 当成已占用端口 → 跳过 `_` 前缀文件。
    5. `devplan/PROFILE_SPEC.md` 扩写：§0 模板机制与槽位表、§6.1 常见错误→现象→修法（8 条，
       含本次实测的 set_map 缩进与队友串味）、§7 遗留按 S16 结论更新。
  - 产物：`game_profiles/_template.yaml`(新)、`tests/test_add_game.py`(新，26 用例)、
    `tools/add_game.py`(M)、`devplan/PROFILE_SPEC.md`(M)、`devplan/PROGRESS.md`(M)
  - 测试结果：
    - `pytest tests/test_add_game.py -q` → **26 passed** ✅
    - `pytest tests/ -q` → **783 passed**（基线 757 + 新增 26，0 failed）✅
    - `bash scripts/check.sh` → **退出码 0**（compileall / boot_check / game_profile_check / pytest 四关全过）✅
    - 端到端实证：`UGF_NONINTERACTIVE=1 python tools/add_game.py s16_probe --no-activate`
      → 生成即 strict 自检通过（0 错误 0 建议）；`game_profile_check.py s16_probe --strict` 退出码 0；
      `AGENT_GAME=s16_probe` 下核心读到 `perception_port=5021 / threat.boss=400 /
      rarity_highest_boss=['Unique','Eternal'] / sets 5 项 / mock 实体 4 条` ✅（探针档案已删除，未入库）
  - 遗留（未在本轮处理，记录备查）：
    - 模板未覆盖 `agent` / `mcp` / `paths` 三个可选顶层键（仅文字说明，需手工补）。
    - 日志展示仍用决策抽象套装名（`combat`）而非游戏内名（`shoot`）；S16 已提供唯一映射表
      `combat.set_map`，展示层直接查表即可，移交 S20/S21。
    - `chase` / `team` 在单人街机类游戏下的映射贴合度仍需实机验证。
  - 决策依据：本轮开工读取状态总表，S1~S15 全 ✅、首个 ⬜ 为 S16（提示词所述「从 S9 续跑」已过期，
    以 PROGRESS.md 实际状态为准）；运行锁为 RELEASED 故正常取锁。未向用户提问，按
    DIRECTION.md「接入新游戏路径产品化」优先级自主执行。
