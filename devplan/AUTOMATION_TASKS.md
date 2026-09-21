# 今晚窗口的 17 条独立自动化任务（待创建）

> 用途：把「一条通用提示词反复跑」改成 **17 条内容各自不同的一次性任务**，每条只干一件事、时间在点上、不重复触发。
> 创建前提：**先把已有的 4 条旧自动化置为 PAUSED**（23:00 / 23:30 两条一次性 + 00:00 整点线 + 00:30 半点线），否则会与本表重复开工。
> 窗口：2026-09-21 23:00 ~ 2026-09-22 07:00。间隔 **25 分钟**（比上一轮 30 分钟更密），末条 05:40，06:05~07:00 留作溢出缓冲。
> 每条任务的 `prompt` = 「本条任务内容」+ 文末「通用约束块」。

---

## 通用约束块（每条任务的 prompt 末尾都要带上）

```
硬约束（违反会直接失败）：
- Python 一律用 /home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python；pip 为同目录 bin/pip；禁止全局 pip install。
- /tmp 是仅 10M 的 tmpfs：任何 pip / 构建命令必须前置 TMPDIR=/home/g-bill/.workbuddy/tmp，否则 OSError: [Errno 28]。
- 磁盘仅剩约 2.3G：禁止安装 opencv / torch / buildozer 等重量级包，图像处理一律用 mock 数据绕过。
- 无 .env（无 LLM/VLM 密钥）、无 X server、无 YOLO：涉及真实 API / 截图 / 键鼠的能力必须走 mock 或 dry-run 降级分支，不得假设其可用，也不得因此跳过本任务。
- 单轮时间预算 22 分钟；做不完就提交已完成部分、在 PROGRESS.md 把该阶段标 🟡 并记录断点，不要空转。
- 结束时必须：更新 devplan/PROGRESS.md（阶段状态 + 执行日志一行）并 git commit -m "S<n>: <摘要>"。
- 禁止删除用户业务文件；禁止提交密钥；未经实际验证不得宣称完成。不向用户提问，自主决策并在 PROGRESS.md 记录理由。
```

---

## 排期总表

| # | 时间 | 阶段 | 一句话任务 | 用户视角：做完他能得到什么 |
|---|---|---|---|---|
| 1 | 09-21 23:00 | S10 | 游戏档案体系固化 | 换游戏不再靠猜，`validate` 真能拦住错档案 |
| 2 | 09-21 23:25 | S11 | UI 收敛 + 统一启动器 | 不再四套前端不知道开哪个，一条命令起对界面 |
| 3 | 09-21 23:50 | S12 | 运维脚本与容器一致性 | `start_all` / `stop_all` 真能一键起停 |
| 4 | 09-22 00:15 | S13 | 测试门禁 + 文档同步 | 一条命令验证全项目，README 不再说假话 |
| 5 | 09-22 00:40 | S14 | 第一阶段验收归档 | 有结项报告，知道哪些真做完、哪些没验 |
| 6 | 09-22 01:05 | S15 | space_invaders 端到端跑通 ※ | **第一次证明「通用」不是空话** |
| 7 | 09-22 01:30 | S16 | 适配器模板 + 档案规范 | 新游戏有标准答案可抄 |
| 8 | 09-22 01:55 | S17 | 接入流程一键化 onboard | 30 分钟接入一款新游戏 |
| 9 | 09-22 02:20 | S18 | 知识闭环实证 ※ | 「越打越强」第一次有数字证明 |
| 10 | 09-22 02:45 | S19 | 学习链路离线化 | 看教程学打法不再只是文档里的功能 |
| 11 | 09-22 03:10 | S20 | 决策场景矩阵 | 以少打多/被围/残血等局面不再瞎决策 |
| 12 | 09-22 03:35 | S21 | 测试门禁 + 大盘模式显示 | 一眼看出当前是 online / dry-run / mock |
| 13 | 09-22 04:00 | S22 | 稳定性长跑与资源门禁 ※ | 7×24 挂机不断、不吃硬盘，有据可查 |
| 14 | 09-22 04:25 | S23 | 安全与合规加固 | 别人敢放心用、敢分发 |
| 15 | 09-22 04:50 | S24 | 打包分发实证 | 真的能装上、能跑起来 |
| 16 | 09-22 05:15 | S25 | 文档体系重写 | 陌生人 3 分钟看懂、30 分钟接入 |
| 17 | 09-22 05:40 | S26 | 版本发布与结项 | 有版本、有 CHANGELOG、有下一步清单 |

※ = 重量级任务，22 分钟内大概率做不完，允许标 🟡 留到下个窗口。

---

## 逐条任务内容（prompt 正文）

### 任务 1 · 23:00 · S10 游戏档案体系固化
项目路径 /home/g-bill/文档/Default Project/Universal-Game-Framework。本任务只做 S10。
1. 审计 `game_profiles/florr.yaml` 与 `game_profiles/space_invaders.yaml` 的字段完整性（实体分类 / 威胁分 / 稀有度 / 套装 / 战术模板 / 感知端口），修掉 space_invaders 里稀有度与威胁分自相矛盾的取值。
2. 让 `tools/add_game.py` 生成的档案与 `game_profile_check.py` 的校验要求严格一致（生成即通过 validate）。
3. 写 `tests/test_game_profiles.py`：合法档案通过、缺字段档案报错、切换 `AGENT_GAME` 后核心读到新值。
交付物：两份补齐的档案、`tests/test_game_profiles.py`、`devplan/PROFILE_SPEC.md`。
验收：`python agent_cli.py -c validate florr` 与 `validate space_invaders` 均通过；`python -m pytest tests/test_game_profiles.py -q` 全绿。

### 任务 2 · 23:25 · S11 UI 收敛与统一启动器
只做 S11。目标：四套前端收敛成「1 主 + 1 备」，用户不再不知道开哪个。
1. 以 `admin_panel.py`（Flask，跨平台、依赖轻、已是文档中的监控大盘）为主 UI；`ui_tkinter.py`（标准库）为离线备选；`ui_streamlit.py` / `ui_pyqt.py` 移入 `ui/legacy/` 并在文件头标注 deprecated。
2. 新增 `launcher.py`：统一入口 `--ui auto|panel|tk|cli`，自动探测可用 UI，并把 dry-run / mock 开关透传下去。
3. 主 UI 增加「当前运行模式（online / dry-run / mock）」显示（S21 会深化）。
交付物：`launcher.py`、`ui/legacy/` 归档、`admin_panel.py` 增强、README 启动章节更新。
验收：`python launcher.py --ui auto --selftest` 能正确识别并打印所选 UI；`python -m pytest -q` 全绿无回归。

### 任务 3 · 23:50 · S12 运维脚本与容器一致性
只做 S12。目标：`start_all.sh` / `stop_all.sh` / `watchdog.sh` / `Dockerfile` / `boot_check.py` 五者口径一致且可干跑。
1. 核对脚本中的文件名、端口（感知 5001 / 面板 5002）、路径与代码实际一致，不一致以代码为准改脚本。
2. `start_all.sh` 支持 `UGF_DRY_RUN=1` 透传；`stop_all.sh` 清理 `video_frames/` 与过期日志。
3. `boot_check.py` 增加离线依赖检查：缺 GUI / YOLO 依赖时给降级建议，而不是直接拦死。
4. `Dockerfile` 与 `requirements.txt` 对齐（headless 包）。
交付物：三脚本 + `boot_check.py` + `Dockerfile` 修订、`devplan/OPS.md`。
验收：`bash start_all.sh --dry-run` 起停全流程退出码 0；`python boot_check.py` 在本机输出可读的降级指引。

### 任务 4 · 00:15 · S13 测试门禁 + 文档同步（第一阶段）
只做 S13。目标：一条命令验证整个项目，且文档不再与实测冲突。
1. 统一 `tests/` 结构，完善 `tests/conftest.py`（注入项目根目录、mock 掉 pyautogui 与网络）。
2. 新增 `scripts/check.sh`：`pytest` + `compileall` + `boot_check` + `tools/mcp_tools_check.py --strict` + `tools/cli_smoke.py`，任一失败即非零退出。
3. 修订 `README.md` / `PROJECT_SUMMARY.md` / `ROADMAP.md`：如实标注已验证项与未验证项，补 mock / dry-run 机制说明与测试规模。
交付物：`scripts/check.sh`、`tests/` 整理、三份文档修订。
验收：`bash scripts/check.sh` 退出码 0；文档中无与 S1~S12 实测结果冲突的陈述。

### 任务 5 · 00:40 · S14 第一阶段验收归档
只做 S14。目标：给第一阶段一个可交付的结论。
1. 汇总 S1~S13 产物，生成 `devplan/FINAL_REPORT_PHASE1.md`：每阶段产物、测试规模统计（用例数 / 通过率）、遗留风险、下一步建议。
2. 全量提交，打 tag `v2.0-dev-phase1`。
3. 把结论写入工作区记忆 `.workbuddy/memory/2026-09-21.md`。
交付物：`devplan/FINAL_REPORT_PHASE1.md`、tag、记忆条目。
验收：`git log` 可见完整冲刺提交链；报告含测试总数统计与遗留风险清单。

### 任务 6 · 01:05 · S15 第二款游戏端到端跑通（※重量级）
只做 S15，这是「通用框架」的唯一证明方式。
1. 按 S10 的规范补全 space_invaders 档案，为其配置符合语义的 mock 感知（母舰 / 无人机 / 群兵 / BOSS）。
2. 以 `UGF_DRY_RUN=1` 跑完整生命周期 detect → brief → research → ensure → play → report，确认每个阶段都有真实产出而非空转。
3. 写 `tests/test_e2e_space_invaders.py`：一条命令串起全流程，断言状态文件、知识库、报告均正确写入。
交付物：补全档案、mock 配置、e2e 测试、`devplan/E2E_S15.md`。
验收：`AGENT_GAME=space_invaders` 下 dry-run 跑完退出码 0 且各阶段产物非空；e2e 测试全绿。

### 任务 7 · 01:30 · S16 适配器模板与档案规范固化
只做 S16。产出 `game_profiles/_template.yaml`（全字段带注释模板 + 默认值 + 安全上下限）；把 `PROFILE_SPEC.md` 补全为可执行规范（字段类型 / 取值域 / 缺失兜底 / 常见错误示例）；让 `add_game.py` 以模板为唯一来源生成档案。交付物含 `tests/test_add_game.py`。
验收：用模板生成一份全新档案 → `validate` 通过 → 核心读到预期值；测试全绿。

### 任务 8 · 01:55 · S17 接入流程一键化（onboard）
只做 S17。新增 `tools/onboard_game.py`，把「生成档案 → validate → mock 感知冒烟 → dry-run N 轮 → 生成接入报告」串成一条命令，报告写入 `devplan/onboard_<game>.md`；接入 CLI `agent_cli.py -c onboard <game>`。交付物含 `tests/test_onboard_game.py` 与至少两份接入报告（其中一款为全新虚构游戏）。
验收：对一款全新游戏跑通 onboard 全流程，退出码 0 且报告非空。

### 任务 9 · 02:20 · S18 知识闭环实证（※重量级）
只做 S18。造 seed 知识 → 打通「决策前检索 → 命中条目进入决策 → 结果写回」链路 → 死亡复盘触发后新笔记落库且下轮可被检索 → 输出命中率指标（检索次数 / 命中次数 / 引用次数，落 `learning_stats`）。交付物 `tests/test_knowledge_loop.py` 与 `devplan/KB_LOOP_S18.md`。
验收：闭环测试全绿；报告里有一组**真实的**命中率数字，不是占位符。

### 任务 10 · 02:45 · S19 学习链路离线化
只做 S19。`video_learner` / `video_sources` 从未跑通过：抽帧改用程序生成合成帧（不依赖下载与 cv2），VLM 环节用可注入 stub 返回结构化战术，学完写库并自动清理临时帧。交付物 `tests/test_video_learner.py`、`devplan/LEARN_S19.md`。
验收：一次完整「抽帧 → 解析 → 入库 → 清理」测试通过；断言临时目录被清空、无残留文件。

### 任务 11 · 03:10 · S20 决策场景矩阵
只做 S20。构造场景矩阵（以少打多 / 被包围 / 队友输出型 / 队友抗伤型 / 残血 / 实体突增突减 / 感知返回空 / 坐标全 NaN / 超高频抖动），对每个场景断言决策（fight / cautious_fight / retreat）、推荐套装、心态档位；发现的缺陷就地修复并补回归用例。交付物 `tests/test_decision_scenarios.py`、`devplan/SCENARIOS_S20.md`（场景 × 期望 × 实测）。
验收：矩阵全绿；场景表每一行都有实测值。

### 任务 12 · 03:35 · S21 测试门禁与可观测性固化
只做 S21。`scripts/check.sh` 定稿（S13 已搭骨架，此处补全并与后续工具对齐）；监控大盘与 CLI 状态输出增加「运行模式（online / dry-run / mock）」与「感知后端」标识；README 增加门禁章节。交付物含 `tests/test_check_script.py`。
验收：`bash scripts/check.sh` 退出码 0；大盘能正确显示 mock / dry-run 模式。

### 任务 13 · 04:00 · S22 稳定性长跑与资源门禁（※重量级）
只做 S22。dry-run 长循环（≥500 轮或固定时长）验证：无异常退出、RSS 无单调增长、无句柄泄漏；跑完断言 `video_frames/` / 截图路径 / 过期日志**零残留**；离线验证 `watchdog.sh` 自恢复（杀进程 → 自动拉起 → 状态恢复）。交付物 `tools/longrun_check.py` 或 `tests/test_longrun.py`、`devplan/STABILITY_S22.md`。
验收：长跑测试通过；残留文件断言为 0；报告含实测内存与单轮耗时数字。

### 任务 14 · 04:25 · S23 安全与合规加固
只做 S23。全量复查路径穿越（知识库读写 / 备份导入 / 档案加载全部限制在项目目录内）；密钥扫描测试（`.env` / 备份包 / 日志不得泄漏）；档案沙箱（超大数值、恶意键、异常结构不得崩溃，须给出可读错误）；README 与 PROJECT_SUMMARY 增补合规声明（面向本地 / 授权环境，不鼓励在他人服务器运行）。
交付物 `tests/test_security.py`、文档合规章节、必要代码加固。
验收：安全测试全绿；恶意档案用例返回可读错误而非 traceback。

### 任务 15 · 04:50 · S24 打包分发实证
只做 S24。Linux 侧跑通 `.deb` / 便携版构建，检查产物结构与体积，便携版解包后能执行 `--help`；Windows EXE / Android APK 本机无法交叉构建，须在 `packaging/README.md` 中**如实标注「脚手架就绪、未实证」**并写清所需环境；复查 `.gitignore` 确保构建产物不入库。交付物 `devplan/PACKAGING_S24.md`。
验收：Linux 产物构建成功且便携版可执行；报告对 Windows / Android 如实标注未实证。

### 任务 16 · 05:15 · S25 文档体系重写
只做 S25。`README.md` 重写为「一句话定位 → 三分钟上手（含 mock 模式）→ 架构 / 生命周期 / 目录三张图 → 接入新游戏 → 二次开发 → 合规声明 → 已知限制（如实列出未实证项）」；`PROJECT_SUMMARY.md` 与代码实际对齐；`ROADMAP.md` 按本工作表重排（Florr 深度化后置并标注前置条件）；新增 `FAQ.md` 收录本机踩坑（TMPDIR / 磁盘 / 无 X server / 无密钥）与解法。
验收：文档中每条命令均可复制执行；无与 S1~S24 实测冲突的陈述。

### 任务 17 · 05:40 · S26 版本发布与结项
只做 S26。新增 `CHANGELOG.md`（按阶段汇总两阶段全部变更）；统一版本号到 `v2.1.0-dev`（README / config / 打包脚本 / 面板页脚）并打 tag；写 `devplan/FINAL_REPORT.md`（完成度、测试规模统计、遗留风险、下一步建议，含 Florr 实机阶段的立项条件）；把结论写入工作区记忆。
交付物：`CHANGELOG.md`、tag、`devplan/FINAL_REPORT.md`、一次完整提交。
验收：`git log` 可见完整冲刺提交链；报告含测试总数与遗留风险清单。

---

## 用户视角的设计原则（写这些任务时的准绳）

1. **每条任务都要落到「用户能感知到的变化」**：不是"重构了 XX 模块"，而是"换游戏不再靠猜""一条命令起对界面""第一次证明通用不是空话"。
2. **顺序按用户上手路径排**：先让他跑得起来（S10~S14 地基）→ 再让他换得了游戏（S15~S17）→ 再让他看到 Agent 真的在进步（S18~S20）→ 最后让他放心长期用与分发（S21~S26）。
3. **凡是本机验不了的（真机 / 真 VLM / 交叉编译），一律如实标注未实证**，不许在文档和报告里含糊过去——用户最怕的是照着文档做了半天发现根本跑不通。
4. **不留垃圾**：临时文件零残留、构建产物不入库、失效任务不堆积。
