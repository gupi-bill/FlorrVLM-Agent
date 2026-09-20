# Universal-Game-Framework 自主开发计划（v2.0 冲刺）

> 制定时间：2026-09-20 23:50
> 执行方式：定时自动化，每 30 分钟推进一个阶段，07:00 自动停止
> 项目路径：`/home/g-bill/文档/Default Project/Universal-Game-Framework`
> Python 运行环境（隔离虚拟环境）：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`
> pip：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/pip`

---

## 一、现状诊断（制定计划时的实测结论）

| 项 | 实测结果 | 结论 |
|---|---|---|
| git 索引 | `git ls-files` = 0，工作区 73 个文件被误标为删除 | 索引被清空，已用 `git reset` 重建 |
| 缺失核心文件 | `predictor.py` `session.py` `report_notifier.py` `skill_manager.py` `perception_server.py` `video_learner.py` `video_sources.py` `tools/` `skills/` `start_all.sh` `stop_all.sh` `watchdog.sh` `requirements.txt` 在磁盘上不存在 | **已从 git HEAD 无损恢复（17 个文件）** |
| 语法 | `compileall` 全部通过 | 代码本身无语法错误 |
| 运行依赖 | 系统 python3 无 `yaml` / `mcp`；无 venv、`requirements.txt` 未落地 | 已创建隔离 venv 并安装核心依赖 |
| 密钥 | 只有 `.env.example`，无 `.env` | **无法调用真实 LLM/VLM/YOLO**，必须建设离线 mock 通路 |
| 平台 | 本机 Linux 无头环境，无 X server | `pyautogui`、真实截图链路不可跑，需 headless 降级 |
| 知识库 | `knowledge_md/` 为空（仅空目录 `space_invaders/`） | 无历史知识，需造种子知识做验证 |
| 大二进制 | `packaging/androidapp/.buildozer/` 约 100MB 构建产物被 git 跟踪 | 应从版本库移除并加入 `.gitignore` |
| UI | 同时存在 `ui_tkinter.py` / `ui_streamlit.py` / `ui_pyqt.py` / `admin_panel.py` 四套前端 | 重复建设，需收敛为「1 主 + 1 备选」 |
| 测试 | 无任何测试文件 | 需建立 `tests/` 与可离线运行的冒烟脚本 |
| 未跟踪新作 | `ui_pyqt.py` `ui_streamlit.py` `ui_tkinter.py` `game_profiles/space_invaders.yaml` | 尚未入库、未校验，需纳入版本库并验证 |

**核心判断**：项目当前处于「文档超前、代码残缺、零验证」状态——README/ROADMAP 宣称 v1.0~v1.9 全部完成，但核心运行时模块一度缺失、没有任何一行代码被真正执行验证过。本次冲刺的目标不是加新功能，而是**把 v2.0 地基做实：可导入、可离线跑通、有测试、有门禁、文档与代码一致**。

---

## 二、执行原则（所有阶段通用）

1. **离线优先**：不依赖任何外部 API / 真实游戏窗口。无法联网验证的能力一律用 mock 或 stub 打通链路，并在代码里显式标注 `offline` / `dry-run` 分支。
2. **最小侵入**：优先补缺失与修 bug，不重写已能工作的模块；确需重构时保留原函数签名。
3. **每阶段可验收**：每阶段必须有可直接执行的验收命令 + 明确产物文件。
4. **每个周期只做一个阶段**：做完即更新 `devplan/PROGRESS.md` 并 `git commit`，不跨阶段铺开。
5. **禁止**：删除用户业务文件；把密钥写入版本库；在无法验证时宣称「已完成」。
6. **环境**：所有 python 命令使用 `/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`；缺依赖时用同目录 `pip` 安装，禁止全局安装。
7. **⚠️ 磁盘与临时目录**（实测踩坑，务必遵守）：
   - 根分区只剩约 2.3G（96% 占用），安装依赖避免重量级包（opencv / torch / buildozer 一律不装）。
   - **`/tmp` 是仅 10M 的 tmpfs**，pip 安装会 `OSError: [Errno 28] 设备上没有空间`。任何 pip / 构建命令必须前置 `TMPDIR=/home/g-bill/.workbuddy/tmp`。
   - 需要图像处理时用 `numpy` / `pillow` 等轻量包，或直接用 mock 数据绕过。
8. **git 仓库注意**：`.git/objects` 已有 130MB pack（历史含 Android 构建产物）。不要执行 `git gc --aggressive` 之类重操作，避免磁盘进一步吃紧。

---

## 三、阶段清单（S1 ~ S14）

### S1 · 仓库基线修复与卫生清理
- **目标**：让仓库处于可提交、可 diff、无垃圾的干净状态。
- **任务**
  1. 确认 git 索引恢复正确（`git status` 语义正常）。
  2. 从版本库移除 `packaging/androidapp/.buildozer/**` 全部构建产物（`git rm -r --cached`），并在 `.gitignore` 增补 `.buildozer/`、`*.tar.gz`、`*.zip`、`*.db`、`.gradle/`。
  3. 新增 `.gitattributes`（`* text=auto eol=lf`），消除跨 Windows/Linux 的换行噪音。
  4. 补齐 `requirements.txt`：按「核心 / 可选 / 开发」三段分组，标注 headless 替代包（`opencv-python-headless`）。
  5. 新增 `requirements-dev.txt`（pytest / pytest-cov / ruff）。
- **交付物**：`.gitattributes`、更新后的 `.gitignore`、`requirements.txt`、`requirements-dev.txt`、一次 `git commit`。
- **验收**：`git status --short` 无大二进制变更；`git add -A && git status` 待提交项不含 MB 级二进制。

### S2 · 静态依赖与接口审计
- **目标**：把「看起来能跑」变成「确认能导入」。
- **任务**
  1. 生成全量 import 图，列出第三方依赖与本地模块依赖。
  2. 对每个模块做 `importlib` 导入测试（用 venv 解释器，允许 mock 缺失的 GUI/硬件依赖）。
  3. 交叉核对跨模块调用签名：找出调用方引用了但被调方不存在/改名/参数不符的函数（重点 `predictor` / `session` / `report_notifier` / `skill_manager` / `combat_judge` / `agent_main`）。
  4. 汇总 `TODO` / `FIXME` / `NotImplementedError` / `pass  #` 占位。
- **交付物**：`devplan/AUDIT.md`（依赖表 + 缺失符号清单 + 占位清单 + 风险分级）。
- **验收**：`devplan/AUDIT.md` 存在且含「阻断级 / 警告级 / 建议级」三类条目；所有阻断级已给出修复方案。

### S3 · 预判引擎 `predictor.py` 实测定型
- **目标**：全实体运动预判是核心卖点，必须数学正确、可单测。
- **任务**
  1. 通读 `predictor.py`，核对配置键（`predict_seconds` / `min_frames` / `entity_timeout` / `confidence_threshold` / 稀有度分级 / 威胁分）与实际读取是否一致。
  2. 编写 `tests/test_predictor.py`：匀速外推、抖动降置信、实体超时剔除、威胁排序、top-N 截断、置信度阈值锁。
  3. 修复测试暴露的缺陷。
- **交付物**：`tests/test_predictor.py`（≥8 个用例），可能的 `predictor.py` 修复。
- **验收**：`python -m pytest tests/test_predictor.py -q` 全绿。

### S4 · 战斗评估与自动调参校验
- **目标**：`combat_judge.py` 的决策（fight/cautious/retreat、套装推荐、心态切换）与 `auto_tuner.py` 的阈值微调必须可离线复现。
- **任务**
  1. 梳理 `combat_judge` 的输入契约（自身实力 / 敌方威胁 / 稀有度 / 组队信息），补齐缺失分支。
  2. 编写 `tests/test_combat_judge.py`：威胁分级、逃跑判定、套装推荐、心态切换、边界（零实体 / 超高威胁）。
  3. 编写 `tests/test_auto_tuner.py`：命中率统计、阈值上下限夹紧、热加载写出。
- **交付物**：两个测试文件 + 修复。
- **验收**：两个测试文件全绿。

### S5 · 会话 / 汇报 / 技能三大支撑模块校验
- **目标**：`session.py`（断点续玩）、`report_notifier.py`（自动汇报）、`skill_manager.py`（技能包）是 v1.2/v1.4/v0.8 的交付物，需实证可用。
- **任务**
  1. `session.py`：状态持久化 / 恢复 / 旧版本无字段兼容（写入读取往返测试）。
  2. `report_notifier.py`：无 webhook 时只落本地文件；有 webhook 时用 mock HTTP 验证；报告字段与 `agent_state.json` 对齐。
  3. `skill_manager.py`：`skills/` 扫描、`load/unload`、清单输出；修复 `skills/report` 内容过薄问题（补全 `SKILL.md` 与 `skill.py` 的真实可执行逻辑）。
- **交付物**：`tests/test_session.py`、`tests/test_report_notifier.py`、`tests/test_skill_manager.py`、补全后的 `skills/report/*`。
- **验收**：三个测试文件全绿。

### S6 · 感知服务离线化（`perception_server.py`）
- **目标**：在无 YOLO、无显卡、无游戏窗口的机器上，感知服务仍能被拉起并返回结构化结果，整条链路可跑。
- **任务**
  1. 为 `perception_server.py` 增加 `mock` 后端：环境变量 `UGF_PERCEPTION_BACKEND=mock|http` 切换；mock 返回符合契约的实体列表。
  2. 保证 HTTP 后端在目标端口不可用时返回明确错误（而非崩溃）。
  3. `config.yaml` 增加 `perception.backend` / `perception.mock_entities` 配置项，并确认 `config.py` 热加载能读到。
- **交付物**：改造后的 `perception_server.py`、`config.yaml` 新配置、`tests/test_perception_server.py`。
- **验收**：mock 模式下 `python perception_server.py --selftest` 或等价自检命令返回结构化实体；测试全绿。

### S7 · 主循环 dry-run（`agent_main.py`）
- **目标**：让 `detect → brief → research → ensure → play → report` 全链路在离线模式下跑 N 轮而不崩。
- **任务**
  1. 增加 `UGF_DRY_RUN=1` 开关：不做真实键鼠动作、不调外部 LLM（用规则化决策 stub），只走流程与写状态。
  2. 修复主循环中因缺失模块/签名不符导致的运行时错误。
  3. 验证热加载、`report_every` 心跳、BOSS 记忆写入、日志滚动在 dry-run 下正常。
- **交付物**：`agent_main.py` 的 dry-run 分支、`run_logs/` 样例输出、`devplan/SMOKE_S7.md` 记录。
- **验收**：`UGF_DRY_RUN=1 python agent_main.py --rounds 5` 正常退出（exit 0），产出状态文件与日志。

### S8 · CLI 全命令冒烟（`agent_cli.py`）
- **目标**：25+ 个子命令逐个可执行，报错也必须是可读的错误而非 traceback。
- **任务**
  1. 批量执行 `detect / brief / capabilities / state / validate / kb_list / kb_write / kb_search / kb_append / kb_export / kb_import / stats / report / notify / session / resume / skills / package` 的离线路径。
  2. 修掉 `ui_pyqt.py` 调用的 `--auto search <game> <query>` 与 CLI 实际 `auto` 参数解析不匹配的问题。
  3. 为所有需要网络/真机的命令加统一降级提示（"当前离线/dry-run 模式，该能力不可用"）。
- **交付物**：`devplan/SMOKE_S8.md`（命令 × 结果矩阵）、`agent_cli.py` 修复。
- **验收**：命令矩阵中无 traceback；至少 80% 命令在离线模式下给出有意义的输出。

### S9 · MCP 服务端工具注册验证（`mcp_server.py`）
- **目标**：README 宣称 15 个 MCP 工具，必须逐个能被列举与调用。
- **任务**
  1. 编写离线调用脚本，直接 import `mcp_server` 并对每个工具函数以 mock 参数调用。
  2. 核对工具清单与 README 表格一致（不一致则改代码或改文档）。
  3. 验证 `kb_export` / `kb_import` 往返一致性。
- **交付物**：`tests/test_mcp_server.py`、`devplan/TOOLS.md`（工具清单核对表）。
- **验收**：测试全绿；工具清单与 README 一致。

### S10 · 游戏档案体系固化（`game_profiles/` + `game_profile_check.py`）
- **目标**：「一款游戏一份 YAML，切游戏零改核心」是项目核心卖点，必须真能切。
- **任务**
  1. 审计 `florr.yaml`（HEAD 版）与新增的 `space_invaders.yaml` 字段完整性，补齐缺失键（实体分类 / 威胁分 / 稀有度 / 套装 / 战术 / 端口）。
  2. 让 `tools/add_game.py` 生成的档案与校验器要求严格一致（生成即通过 validate）。
  3. 编写 `tests/test_game_profiles.py`：校验器对合法档案通过、对缺字段档案报错、切换档案后核心读取到新值。
- **交付物**：补齐后的两份档案、测试文件、`devplan/PROFILE_SPEC.md`（档案字段规范）。
- **验收**：`python agent_cli.py -c validate florr` 与 `... space_invaders` 均通过；测试全绿。

### S11 · UI 收敛与统一启动器
- **目标**：四套前端砍到「1 主 + 1 备选」，且都能被一键拉起。
- **任务**
  1. 选型：`admin_panel.py`（Flask，无重依赖、跨平台、已是文档中的监控大盘）为主 UI；`ui_tkinter.py`（标准库）为离线备选；`ui_streamlit.py` / `ui_pyqt.py` 移入 `ui/legacy/` 并在文件头标注 deprecated。
  2. 新增 `launcher.py`：统一入口，按可用性自动选择 UI（`--ui auto|panel|tk|cli`），并把 dry-run / mock 开关透传。
  3. 主 UI 补齐「当前模式（在线/dry-run/mock）」状态显示。
- **交付物**：`launcher.py`、`ui/legacy/` 归档、`admin_panel.py` 增强、README 启动章节更新。
- **验收**：`python launcher.py --ui auto --selftest` 能正确识别可用 UI 并打印选择结果。

### S12 · 运维脚本与容器一致性
- **目标**：`start_all.sh` / `stop_all.sh` / `watchdog.sh` / `Dockerfile` / `boot_check.py` 五者口径一致，且在本机可干跑。
- **任务**
  1. 核对脚本中的文件名、端口、路径与代码实际一致（端口 5001 感知 / 5002 面板）。
  2. `start_all.sh` 支持 `UGF_DRY_RUN=1` 透传；`stop_all.sh` 清理临时目录（`video_frames/`、过期日志）。
  3. `boot_check.py` 增加「离线依赖检查」：缺失 GUI/YOLO 依赖时给出降级建议而非直接拦截。
  4. `Dockerfile` 与 `requirements.txt` 对齐（headless 包）。
- **交付物**：三个脚本 + `boot_check.py` + `Dockerfile` 修订，`devplan/OPS.md`。
- **验收**：`bash start_all.sh --dry-run` 起停全流程退出码 0；`python boot_check.py` 在本机输出可读的降级指引。

### S13 · 测试套件固化与文档同步
- **目标**：把前 12 阶段的验证固化成一条命令可跑的门禁，并让文档说真话。
- **任务**
  1. 统一 `tests/` 结构，新增 `conftest.py`（统一注入项目根目录、mock 掉 `pyautogui` / 网络）。
  2. 新增 `Makefile` 或 `scripts/check.sh`：`pytest` + `compileall` + `boot_check` 一条命令跑完。
  3. 修订 `README.md` / `PROJECT_SUMMARY.md` / `ROADMAP.md`：如实标注已验证项与未验证项，补 v2.0 实际进度、离线模式说明、测试与门禁说明。
- **交付物**：`tests/conftest.py`、`scripts/check.sh`、三份文档修订。
- **验收**：`bash scripts/check.sh` 全程退出码 0；文档与实测结果无冲突陈述。

### S14 · 最终验收与归档
- **目标**：输出一份可交付的冲刺报告，并把状态固化进版本库与记忆。
- **任务**
  1. 汇总 S1~S13 的所有产物，生成 `devplan/FINAL_REPORT.md`：每个阶段的产物、测试结果统计（用例数 / 通过率）、遗留风险与下一步建议。
  2. 全量 `git add -A && git commit`，必要时打 tag `v2.0-dev-<date>`。
  3. 把冲刺结论写入工作区记忆 `.workbuddy/memory/2026-09-21.md`。
- **交付物**：`devplan/FINAL_REPORT.md`、一次完整提交、记忆条目。
- **验收**：`git log` 可见本次冲刺提交链；报告含测试统计与遗留风险清单。

---

## 四、阶段推进规则（自动化周期执行约定）

1. 每周期（30 分钟）**只执行一个阶段**，顺序 S1 → S14。
2. 开始先读 `devplan/PROGRESS.md` 定位当前阶段；结束必须更新该文件（阶段状态、产物清单、测试结果、遗留问题、下一步）。
3. 阶段内如发现阻断级问题无法在本周期解决，记录到 PROGRESS 的「阻塞项」并继续下一阶段，不空转。
4. 每阶段结束执行一次 `git add -A && git commit -m "<stage>: <摘要>"`（无改动则跳过）。
5. 到达 07:00 或全部阶段完成，停止推进，不再安排新任务。
6. 全过程不向用户提问；遇不确定项按本计划的原则自主决策并在 PROGRESS 中记录理由。
