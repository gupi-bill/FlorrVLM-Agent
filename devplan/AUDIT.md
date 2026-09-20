# S2 · 静态依赖与接口审计报告

> 生成时间：2026-09-21 02:40（自动机）
> 审计工具：`tools/static_audit.py`（纯标准库 ast 分析 + 子进程导入探针）
> 运行时：`/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python`（Python 3.13.12）
> 机器可读数据：`devplan/audit_data.json`
> 复现命令：`TMPDIR=/home/g-bill/.workbuddy/tmp <venv>/bin/python tools/static_audit.py`

---

## 一、结论速览

| 指标 | 结果 |
|---|---|
| 受审业务模块 | 26 个（含 `tools/` 2 个、`skills/report` 1 个、`packaging` 1 个） |
| 语法错误 | 0 |
| 导入探针（注入 GUI/视觉 stub） | **24 / 26 成功** |
| 裸环境导入（不注入任何 stub） | **23 / 25 成功**（`packaging.android_main` 不可作为模块导入，单列） |
| 跨模块缺失符号（`from X import Y` 而 Y 不存在） | **0** |
| 模块别名属性缺失（`X.attr` 而 attr 不存在） | 4 处（均属同一处降级 shim，见 W1） |
| 关键字参数不匹配 | 0 |
| 未声明的第三方依赖 | 5 个 |
| 声明但代码未使用 | 2 个 |
| 命名空间遮蔽 | 1 处（`packaging/`） |
| `NotImplementedError` 占位 | 0 |
| `pass` 占位 | 20 处（分布在 11 个模块） |
| TODO / FIXME（业务代码） | 0 |

**风险分级计数**：阻断级 3（本轮已修复 2、给出方案 1）· 警告级 8（已修复 1）· 建议级 5。

---

## 二、模块依赖与导入探针总表

`裸环境` = 不注入任何 stub 的实际导入结果（最能反映本机真实可导入性）。

| 模块 | LOC | 本地依赖 | 第三方依赖 | 探针(stub) | 裸环境 |
|---|---:|---|---|---|---|
| admin_panel | 245 | config, session | psutil | ✅ | ✅ |
| agent_cli | 712 | agent_main, cli_ui, config, game_profile_check, kb_maintainer, mcp_connector, report_notifier, session, skill_manager | yaml | ✅ | ✅ |
| agent_main | 742 | auto_tuner, combat_judge, config, kb_maintainer, report_notifier | dotenv, mcp, pyautogui, requests | ✅ | ✅ |
| auto_tuner | 126 | config | yaml | ✅ | ✅ |
| boot_check | 144 | config | — | ✅ | ✅ |
| cli_ui | 85 | — | — | ✅ | ✅ |
| combat_judge | 410 | config | — | ✅ | ✅ |
| config | 176 | — | yaml | ✅ | ✅ |
| game_profile_check | 124 | config | yaml | ✅ | ✅ |
| kb_maintainer | 209 | config | — | ✅ | ✅ |
| mcp_connector | 152 | config | mcp, yaml | ✅ | ✅ |
| mcp_server | 459 | config, kb_maintainer, predictor | mcp, pyautogui, requests, chromadb*, sentence_transformers* | ✅ | ✅（本轮修复，见 B1） |
| packaging.android_main | 38 | — | kivy* | ⛔ 命名空间遮蔽 | ⛔ 见 B2 |
| perception_server | 240 | — | flask | ✅ | ✅ |
| predictor | 319 | config | — | ✅ | ✅ |
| report_notifier | 187 | auto_tuner, config | requests | ✅ | ✅ |
| session | 273 | config | — | ✅ | ✅ |
| skill_manager | 131 | — | — | ✅ | ✅ |
| skills.report.skill | 9 | — | — | ✅ | ✅（内容过薄，见 I4） |
| tools.add_game | 160 | game_profile_check | — | ✅ | ✅ |
| tools.build_dist | 188 | — | — | ✅ | ✅ |
| ui_pyqt | 167 | — | PyQt6*, yaml | ⛔ 未安装 | ⛔ 未安装（W2） |
| ui_streamlit | 132 | — | streamlit*, yaml | ✅ | ⛔ 未安装（W3） |
| ui_tkinter | 398 | — | yaml | ✅ | ✅ |
| video_learner | 296 | video_sources | cv2, dotenv, requests | ✅ | ✅（本轮修复，见 B3） |
| video_sources | 65 | — | — | ✅ | ✅ |

`*` = 代码 import 了但 `requirements.txt` 未声明（详见第三节）。

---

## 三、第三方依赖对账

### 3.1 代码 import 但未声明（5 个）

| 包 | 使用模块 | 性质 | 处置 |
|---|---|---|---|
| `PyQt6` | ui_pyqt | GUI 前端 | 已注释形式写入 `requirements.txt` 第 3 段（默认不装，S11 UI 收敛后再定） |
| `streamlit` | ui_streamlit | GUI 前端 | 同上 |
| `chromadb` | mcp_server（仅 `FLORR_VECTOR_SEARCH=1`） | 可选增强 | 同上 |
| `sentence-transformers` | mcp_server（同上） | 可选增强，会拉入 torch（GB 级） | 同上，明确标注磁盘风险 |
| `kivy` | packaging/android_main | 仅 Android 打包 | 同上 |

### 3.2 声明但代码未 import（2 个）

| 包 | 判断 |
|---|---|
| `numpy>=1.24.0` | 当前无任何模块 import。预判引擎/威胁评分目前用纯 Python 实现。保留（后续数值化会用到），不做删除 |
| `pillow>=10.0.0` | 当前无模块 import（`video_learner` 走 cv2 路径）。作为截图编码的替补路径保留 |

### 3.3 版本约束冲突（本轮已修）

`mcp>=1.0.0` 上不封顶，全新安装会拿到 **mcp 2.2.0**，而 2.x 已删除 `mcp.server.fastmcp.FastMCP`（改名为 `mcp.server.mcpserver.MCPServer`）→ `mcp_server.py` 必然 `ImportError`。已收紧为 `mcp>=1.0.0,<2.0.0`。

**已安装版本快照**：flask 3.1.3 · requests 2.34.2 · python-dotenv 1.2.3 · pyyaml 6.0.3 · psutil 7.2.2 · **mcp 2.2.0（与约束不符，本机残留）** · numpy 2.5.3 · pytest 9.1.1。

---

## 四、跨模块接口核对

| 检查项 | 结果 |
|---|---|
| `from <本地模块> import <符号>` 且符号不存在 | **0 处** ✅ |
| 调用点关键字参数与形参不匹配 | **0 处** ✅ |
| `模块别名.属性` 且属性不存在 | **4 处**（见下） |

4 处缺失属性全部指向同一位置 —— `agent_cli.py:29-32` 的 `session` 降级 shim：

```python
# agent_cli.py 22-35（try: import session / except ImportError: 兜底）
session.load_state  = lambda: {}        # ❌ session.py 无此函数（真实 API 为 load()）
session.save_state  = lambda s: None    # ❌ 真实 API 为 save()
session.update_state= lambda k, v: None # ❌ 不存在
session.clear_state = lambda: None      # ❌ 不存在
```

**关键判定**：`session.py` 实际导出 `load / save / record_start / record_end / mark_resumed / snapshot_rounds_deaths / resume_info / describe / stats_text / history / stats`。
`agent_cli.py` 的真实调用点（259/260/263/269/276/279/628/630/633/685-687 行）全部使用正确的 `record_*` / `describe` / `resume_info` / `stats_text`，**因此线上不报错**。该 shim 只在 `import session` 失败时才生效，而 `session.py` 始终存在 → shim 实际不可达。
定级 **警告级（W1）**：属"过期兜底代码"，误导维护者，且 shim 一旦真的触发会立刻 `AttributeError`（缺 `record_start`）。

---

## 五、占位与标记清单

- `NotImplementedError`：**0 处**。
- `pass` 占位：20 处，分布在 admin_panel(3) / agent_cli(1) / agent_main(5) / auto_tuner(3) / kb_maintainer(2) / mcp_connector(1) / perception_server(1) / session(1) / ui_streamlit(1) / ui_tkinter(1) / video_learner(1)。抽查 `agent_main.py` 的 5 处（125/149/176/297/443 行）均为 `except ...: pass` 的异常吞除，**非未实现函数**。
- TODO / FIXME / XXX / HACK：业务代码 **0 处**（仅审计工具自身的注释命中）。

---

## 六、风险分级与修复方案

### 6.1 阻断级（Blocker）

#### B1 · `mcp_server.py` 与 mcp 2.x SDK 不兼容 —— ✅ 本轮已修复并验证
- **证据**：`from mcp.server.fastmcp import FastMCP` → mcp 2.2.0 抛 `ModuleNotFoundError: ... This is mcp 2.x, where FastMCP was renamed to MCPServer`；原代码 `except ImportError: raise ImportError("请先安装 mcp")`，即已装 mcp 也必然失败。
- **影响**：MCP 服务端（S9 依赖）在无 `<2` 约束的机器上 100% 不可导入。
- **修复**：① `requirements.txt` 收紧为 `mcp>=1.0.0,<2.0.0`；② `mcp_server.py` 加 v1/v2 双路径兼容层（`MCP_SDK_VERSION` 标记 1/2）。
- **验证**：裸环境 `import mcp_server` 成功，`MCP_SDK_VERSION=2`。
- **遗留**：mcp 2.x 还有其它 API 变更，**工具注册能否真正工作由 S9 实测确认**；推荐生产环境仍按 `<2.0.0` 安装。

#### B2 · `packaging/` 目录被 PyPI 同名包遮蔽 —— ⚠️ 给出方案，未改结构
- **证据**：`packaging/` 无 `__init__.py` → 属**命名空间包**，优先级低于 site-packages 中的常规包 `packaging`（`/…/site-packages/packaging/__init__.py`），故 `import packaging.android_main` 恒为 `ModuleNotFoundError`。
- **影响**：`packaging/android_main.py`（Android 入口）无法通过包名导入，只能在打包时被拷贝使用。
- **方案（推荐）**：不新增 `packaging/__init__.py`——那样会**反向遮蔽** PyPI 的 `packaging`，破坏 pip/setuptools。改为在需要使用时把目录本身加入 `sys.path`：
  ```python
  sys.path.insert(0, str(ROOT / "packaging")); import android_main
  ```
- **验证**：该变通已实测通过（kivy 以 stub 注入），`android_main` 顶层符号 `FlorrApp / Root / App / BoxLayout / Label / Clock` 正常导出。
- **判定**：不阻塞主链路（桌面端不涉及），维持目录结构不动以免触碰业务文件。

#### B3 · `video_learner.py` 顶层硬依赖 cv2 —— ✅ 本轮已修复并验证
- **证据**：第 28 行顶层 `import cv2` 无任何降级，本机未装 opencv → `ModuleNotFoundError: No module named 'cv2'`，整个模块不可导入，违反项目"离线优先 / headless 可跑"原则。
- **修复**：改为软依赖（`try: import cv2 / except ImportError: CV2_AVAILABLE=False`），`extract_frames()` 在无 cv2 时打印 `[offline]` 提示并返回空列表，保证上层 dry-run 链路不断。
- **验证**：裸环境 `import video_learner` 成功；`CV2_AVAILABLE=False`；`extract_frames("nope.mp4") == []`。

### 6.2 警告级（Warning）

| # | 问题 | 影响 | 修复方案 | 归属 |
|---|---|---|---|---|
| W1 | `agent_cli.py:29-32` session 降级 shim 定义了 4 个不存在的 API，且缺 `record_start` 等真实 API | 误导维护者；shim 一旦触发立即崩溃 | 删除 4 个幽灵 lambda，按 `session.py` 真实导出补齐 shim，或直接改为 `from session import ...` 显式导入 | S5 |
| W2 | `ui_pyqt.py` 依赖 PyQt6，本机未装且 requirements 未声明 | 模块不可导入 | 已在 requirements 第 3 段以注释形式登记；保留/删除由 S11 UI 收敛决定 | S11 |
| W3 | `ui_streamlit.py` 依赖 streamlit，同上 | 裸环境不可导入 | 同上 | S11 |
| W4 | `mcp_server.py` 可选依赖 chromadb / sentence-transformers 未声明 | 开启 `FLORR_VECTOR_SEARCH=1` 时才暴露 | 已注释登记；sentence-transformers 会拉入 torch，磁盘紧张时禁止安装 | 已缓解 |
| W5 | `packaging/android_main.py` 依赖 kivy 未声明 | 仅 Android 打包暴露 | 已注释登记 | 已缓解 |
| W6 | `mcp_server._path_perturb_move()` 内 `import pyautogui` 缺少降级（同文件其它键鼠入口都有 try/except） | 无 pyautogui 机器调用该函数即 ImportError | ✅ 本轮已加 `try/except ImportError: return`，与同文件其它入口一致 | 已修复 |
| W7 | `numpy` / `pillow` 声明但代码未 import | 依赖表与代码不完全一致 | 保留（后续数值化/截图编码会用到），不做删除 | 可接受 |
| W8 | `agent_cli.py` 第 21-22 行 `import config` 重复两次 | 无害但属代码噪音 | 删除重复行 | S11/清理 |

### 6.3 建议级（Info）

| # | 建议 | 说明 |
|---|---|---|
| I1 | `mcp_server` 导入即有副作用 | 实测 `import mcp_server` 会自动向 `knowledge_md/` 写入 4 个模板文件，审计/测试会污染工作区。建议把"空知识库初始化"挪到显式初始化函数 |
| I2 | `video_learner` 顶层 `signal.signal()` 限制导入线程 | 非主线程导入会抛 `ValueError: signal only works in main thread`。建议移入 `main()`，便于测试框架并发导入 |
| I3 | 20 处 `pass` 占位需逐个确认 | 抽查均为异常吞除；建议 S13 前逐处确认是否应记日志而非静默 |
| I4 | `skills/report/skill.py` 仅 9 行 | 技能包内容过薄，与 v0.8 技能系统定位不符 |
| I5 | 4 套前端并存（tkinter / PyQt / streamlit / admin_panel） | 重复建设，S11 收敛为「1 主 + 1 备选」 |

---

## 七、本轮改动清单

| 文件 | 改动 |
|---|---|
| `tools/static_audit.py` | 新增（619 行）：静态依赖与接口审计工具 |
| `devplan/audit_data.json` | 新增：机器可读审计数据 |
| `devplan/AUDIT.md` | 新增：本报告 |
| `requirements.txt` | `mcp` 上界收敛至 `<2.0.0`；新增第 3 段「可选但默认不装」登记 5 个未声明依赖 |
| `mcp_server.py` | mcp v1/v2 双路径兼容层；`_path_perturb_move` 补 pyautogui 降级 |
| `video_learner.py` | cv2 改软依赖 + `extract_frames()` offline 分支 |

---

## 八、遗留与移交

1. **mcp 2.x 兼容性仅验证到 import 层**，工具注册/调用由 **S9** 实测。
2. `packaging/` 遮蔽未做结构改动，按 B2 变通方案处理；若 S12（运维脚本）需要脚本化调用 Android 入口，直接套用该变通。
3. W1（session shim）与 I4（skill.py 过薄）明确移交 **S5**。
4. `requirements.txt` 第 3 段为注释态，**不参与 `pip install -r`**，避免磁盘被 torch/Qt 撑爆。
