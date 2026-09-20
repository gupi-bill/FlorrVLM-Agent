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
    - `combat_judge` 复用 `predictor.threat` 表但自身另有默认值分支，**S4** 需核对两处是否漂移。
