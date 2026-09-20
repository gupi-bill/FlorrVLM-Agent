# 冲刺执行进度（自动机填写）

> 计划：`devplan/PLAN.md` ｜ 周期：每 30 分钟一个阶段 ｜ 停止时间：当日 07:00
> 运行环境：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`

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
