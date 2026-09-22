<div align="center">

# 🎮 Universal-Game-Framework

**不是 Agent —— 是装到别的 Agent 身上的「游戏能力包」（MCP 服务）**

把它注册进任意支持 MCP 的客户端（Kilo / Codex / OpenCode / WorkBuddy / Claude Desktop），
那个 Agent 就立刻拥有 **看画面 → 预判 → 评估 → 出动作 → 查/写知识库 → 复盘** 一整套游戏能力。

融合 **YOLO 视觉识别** + **MCP 标准协议**，从 Florr.io 出发，目标是通用到所有游戏：
**detect 问游戏 → research 查资料 → ensure 确认能力 → play 开玩 → report 汇报**

> 🚀 **三分钟装上别的 Agent**：见 [docs/MCP_INSTALL.md](./docs/MCP_INSTALL.md) ｜
> 一条命令：`python tools/install_mcp.py --target workbuddy`

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org)
[![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-标准%20Agent-green)](https://modelcontextprotocol.io)
[![Version](https://img.shields.io/badge/Version-v2.0%20起步-orange)](#)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](./LICENSE)

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

</div>

---

## 目录

- [✨ 核心能力](#-核心能力)
- [🔬 稀有度体系](#-稀有度体系)
- [🏗️ 当前架构](#️-当前架构)
- [⚙️ 快速开始](#️-快速开始)
- [📦 安装包](#-安装包)
- [🧩 MCP 工具](#-mcp-工具15-个)
- [🧪 离线模式与自测](#-离线模式与自测)
- [✅ 验证状态](#-验证状态)
- [📁 文件结构](#-文件结构)
- [🗺️ 路线图](#️-路线图roadmap)

---

## ✨ 核心能力

| 能力 | 说明 |
|------|------|
| 🎬 **视频学习** | 解析教程视频，VLM 逐帧提取战术写入知识库 |
| 🔮 **全实体预判** | 同时预判 BOSS / 精英 / 小怪未来 1.2s 位置，带置信度 |
| ⚔️ **战斗评估** | 自身实力 vs 敌方威胁，动态决定 fight / cautious / retreat |
| 🧠 **动态心态** | 面对不同怪物 + 自身实力，自动切换保守 / 均衡 / 激进 |
| 👥 **组队协同** | 识别队友套装，自动分工：输出 / 辅助 / 掩护 |
| 🕹️ **拟人操作** | 移动抖动 + 随机停顿 + 路径微扰，降低脚本感 |
| 🧠 **BOSS 记忆** | 每 12s 批量记录 BOSS 行为习惯到知识库 |
| 📝 **死亡复盘** | 连续 8 帧判定死亡（`death_frame_threshold` 可配），BOSS / 组队局自动生成复盘 |
| 💬 **对话指挥** | `agent_cli.py` 交互式命令，像普通 Agent 一样问答编排 |
| 🎚️ **自动调参** | 按命中率 / 死亡数自动微调战斗阈值，热加载生效 |
| 🧩 **Skill + 外部 MCP** | 能接技能包、主动连外部 MCP，能力按需装配 |
| 🎮 **游戏档案化** | 一款游戏一份 YAML 档案，切换游戏零改核心 |
| 📊 **监控大盘** | 本地网页实时看指标卡 / BOSS 预判 / 日志 / 资源占用 |
| 🔔 **自动汇报** | 每局结束自动出报告，可推送本地 / Webhook |
| 💾 **导入导出** | 知识库打包备份 / 一键恢复，知识本地化可迁移 |
| 📦 **多平台安装包** | Linux .deb / 便携版 / Windows EXE / Android APK |

---

## 🔬 稀有度体系

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

| 实体类型 | 对应稀有度 |
|---|---|
| `highest_boss` | Unique / Eternal（紧急避险） |
| `boss` | Super |
| `elite` | Ultra / Mythic / Legendary / Epic |
| `normal` | Rare / Unusual / Common |

---

## 🏗️ 当前架构

```
┌────────────────────────────────────────────────────────────┐
│                   agent_cli.py 对话 / 命令行指挥             │
│   detect → brief → research → ensure → play → report        │
└──────────────┬──────────────────────────────┬─────────────┘
               ▼                              ▼
        ┌──────────────┐             ┌──────────────────┐
        │  MCP Server  │             │   MCP Client     │
        │  对外暴露工具  │             │  主动接外部服务    │
        └──────┬───────┘             └────────┬─────────┘
               │                              │
        ┌──────▼────────┐            ┌────────▼─────────┐
        │ game_profiles │◄──热加载──►│  核心引擎（通用）   │
        │ 游戏档案(YAML) │            │ 感知/预判/评估/执行 │
        └───────────────┘            └──────────────────┘
```

---

## 🎮 主界面：设置 → 游戏模式

浏览器打开监控大盘后，顶部有两个入口：

| 入口 | 路径 | 作用 |
|---|---|---|
| ⚙ 设置 | `/settings` | 查看运行模式、切换游戏档案、查看 MCP 注册信息 |
| 🎮 打开游戏模式 | `/game` | 一键试跑 / 停止、实时看回合、死亡、决策、威胁预判与日志 |

```bash
python admin_panel.py          # 或 python launcher.py --ui auto
# 打开 http://127.0.0.1:5002  →  ⚙ 设置  →  🎮 打开游戏模式
```

游戏模式里的「试跑 20 轮（dry-run）」**不会操作真实键鼠**，只跑完整链路，用来确认接线和配置没问题；确认无误后再关掉 dry-run 上真机。
（面板监听 `0.0.0.0`，但 `/api/game/start|stop|switch` 三个控制接口**只接受本机 127.0.0.1 访问**，局域网无法起停进程。）

## 🔌 作为 MCP 服务被其他 Agent 调用

`mcp_server.py` 以 **stdio** 形式对外暴露 15 个工具，可直接注册进任意支持 MCP 的客户端：

```json
{
  "mcpServers": {
    "ugf": {
      "command": "<你的 venv>/bin/python",
      "args": ["/绝对路径/Universal-Game-Framework/mcp_server.py"],
      "env": { "UGF_DRY_RUN": "1" }
    }
  }
}
```

本项目已写入本机 `~/.workbuddy/mcp.json`（服务名 `ugf`）；在连接器管理页把它设为信任后即可被其他 Agent 调用。

## ⚙️ 快速开始

```bash
# 1. 安装依赖
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 配置 API
cp .env.example .env   # 填入 LLM / VLM 密钥

# 3. 启动感知服务（需 florr_powerful_tools 的 YOLO）
python perception_server.py

# 4. 进入对话 CLI（另一终端）
python agent_cli.py            # 交互式；help 看全部命令
python agent_cli.py -c report  # 或跑单条命令
```

**统一启动入口（推荐，v2.0 S11）**：

```bash
python launcher.py                      # 自动挑一个能跑的 UI（大盘 > Tk > CLI）
python launcher.py --ui panel           # 强制用监控大盘（主 UI）
python launcher.py --ui tk              # 强制用 Tk 离线备选
python launcher.py --ui cli             # 直接进命令行（永可用）
python launcher.py --dry-run --mock     # 离线演示：不碰键鼠 + 合成感知
python launcher.py --ui auto --selftest # 只探测并打印选择结果（CI 用）
```

四套前端已收敛：`admin_panel.py`（纯标准库，主 UI）+ `ui_tkinter.py`（离线备选）；
`ui/legacy/ui_pyqt.py`、`ui/legacy/ui_streamlit.py` 已归档，仅在显式 `--ui pyqt|streamlit` 时拉起。

**一条命令拉起整套**：

```bash
bash start_all.sh    # 感知 + MCP + Agent 主循环 + 面板
bash stop_all.sh     # 优雅停止
```

监控面板：浏览器打开 <http://127.0.0.1:5002>（页面「运行模式」卡片显示在线/dry-run 与感知后端）

---

## 🧪 离线模式与自测

没有实机、没有 X server、没有 API 密钥，也能把整条链路跑通 —— 冲刺期间所有验证都在这种条件下完成：

| 开关 / 参数 | 作用 |
|---|---|
| `UGF_DRY_RUN=1` | 键鼠动作只记录不执行，明细落 `run_logs/dryrun_actions.log` |
| `UGF_PERCEPTION_BACKEND=mock` | 感知服务改出合成场景（5 实体 + 1 队友，坐标恒定在场内） |
| `--selftest` | 只探测不启动：`perception_server.py` / `launcher.py` 均支持 |
| `--strict` | `game_profile_check.py` / `cli_smoke.py` / `mcp_tools_check.py` 的建议项也计入失败 |

```bash
UGF_DRY_RUN=1 python agent_main.py --rounds 5   # 主循环离线跑 5 轮
python perception_server.py --selftest          # 感知自检（无 YOLO 自动降级 mock）
python launcher.py --ui auto --selftest         # UI 可用性探测 + 选择结果
python tools/cli_smoke.py --strict              # CLI 31 条命令矩阵
python tools/mcp_tools_check.py --strict        # MCP 15 工具注册 / 调用 / 知识库往返
```

---

## ✅ 验证状态

> 本节只写**真正跑过的结论**。凡标注「未验证」的，均需实机 / 联网环境才能确认 —— 不做任何推测性宣称。

### 一条命令门禁

```bash
bash scripts/check.sh          # 全量 6 环节（约 4 分钟）
bash scripts/check.sh --fast   # 秒级：语法 + 启动自检 + 档案校验
```

六个环节（S21 起 MCP 工具核对与 CLI 冒烟也纳入门禁）：
`1` 语法编译 → `2` 启动自检 → `3` 游戏档案 → `4` 单元测试 → `5` MCP 工具核对 → `6` CLI 全命令冒烟。
退出码即失败环节编号，任一环节失败即整体非零。

运行模式可观测（S21）：

```bash
python agent_cli.py -c mode     # 模式 / 感知后端 / LLM / VLM / 激活游戏
```

口径统一由 `config.runtime_mode()` 提供，大盘与 CLI 都从这里取，不存在第二套解析。

### 已实测（离线，冲刺窗口 2026-09-21 ~ 09-22）

| 项 | 结论 | 复核命令 |
|---|---|---|
| Python 语法 | 全仓库 `compileall` 通过 | `bash scripts/check.sh --fast` |
| 单元测试 | **920 用例全绿** | `python -m pytest tests/ -q` |
| 启动自检 | 本机 ERROR 0 / WARN 6，每条附「修复 + 降级」指引 | `python boot_check.py` |
| 游戏档案 | florr / space_invaders 两份 `--strict` 全过 | `python game_profile_check.py --all --strict` |
| MCP 工具 | 15 个工具可注册 / 可调用 / schema 正确 + 知识库往返保真 | `python tools/mcp_tools_check.py --strict` |
| CLI | 31 条命令矩阵，0 traceback、0 卡死 | `python tools/cli_smoke.py --strict` |
| 主循环 | 离线 5 轮跑通：感知 → 预判 → 决策 → 动作 → 记忆 → 复盘 → 汇报 | `UGF_DRY_RUN=1 python agent_main.py --rounds 5` |
| 统一启动器 | UI 探测 / 选择 / 离线开关透传全部可验 | `python launcher.py --ui auto --selftest` |
| 运维脚本 | 启停 dry-run 零副作用；日志轮转与临时清理已沙箱实测 | `bash start_all.sh --dry-run` |

### 未验证（受本机环境限制，非代码缺陷）

| 能力 | 阻塞原因 | 降级方式 |
|---|---|---|
| 真实 LLM / VLM 决策 | 无 `.env` 密钥 | 走 `_fallback_decide` 规则分支 |
| 真实截图 + YOLO 感知 | 无 X server、无模型权重 | 感知自动降级到 mock 后端 |
| 键鼠实际操作 | 无 GUI | dry-run 只记录不执行 |
| 联网教程检索 / Webhook 推送 | 无外部 MCP、无网络 | 注入假 `requests`、返回降级提示 |
| 容器镜像构建 | 本机无 docker | 仅静态口径对齐 + headless 替换 |
| GUI 真实渲染（Tk / PyQt / Streamlit） | 无 X server / 未安装 | 仅验证可用性与命令构造 |

冲刺全记录见 [devplan/PROGRESS.md](devplan/PROGRESS.md)，阶段计划见 [devplan/PLAN.md](devplan/PLAN.md)，运维口径见 [devplan/OPS.md](devplan/OPS.md)。

---

## 📦 安装包

```bash
python tools/build_dist.py all      # Linux .deb + 便携版
```

Windows EXE / Android APK 见 [packaging/README.md](packaging/README.md)。

---

## 🧩 MCP 工具（15 个）

| 类别 | 工具 |
|------|------|
| 📚 知识库 | `kb_list` `kb_search` `kb_write` `kb_append` `kb_export` `kb_import` |
| 👁️ 感知 | `perceive_game` `predict_all_entities` `reset_predictor` |
| 🕹️ 动作 | `game_action` `switch_set` `handle_afk` |
| 🧹 维护 | `clean_cache` `query_boss_history` `switch_tactic` |

---

## 📁 文件结构

```
Universal-Game-Framework/
├── agent_cli.py             # 对话指挥入口（交互 + -c 单命令）
├── agent_main.py            # MCP Client 主循环
├── mcp_server.py            # MCP 服务端
├── mcp_connector.py         # 外部 MCP 连接
├── predictor.py             # 全实体运动预判
├── combat_judge.py          # 战斗评估 / 套装 / 组队 / 心态
├── perception_server.py     # YOLO 感知 HTTP 服务
├── video_learner.py         # 视频学习
├── video_sources.py         # 视频来源
├── session.py               # 会话记忆
├── report_notifier.py       # 自动汇报
├── kb_maintainer.py         # 知识库压缩 / 归档 / 导入导出
├── auto_tuner.py            # 自动调参
├── game_profile_check.py    # 档案自检
├── boot_check.py / watchdog.sh / Dockerfile / florr-agent.service.example  # 稳定性
├── launcher.py              # 统一启动入口（v2.0：自动选 UI + 离线开关透传）
├── admin_panel.py           # 监控大盘（主 UI，纯标准库）
├── ui_tkinter.py            # 离线备选 UI
├── ui/legacy/               # 已归档：ui_pyqt.py / ui_streamlit.py（DEPRECATED）
├── cli_ui.py                # 终端界面
├── config.py / config.yaml  # 参数 + 热加载
├── ui_tkinter.py            # 离线备选 UI
├── ui/legacy/               # 已归档：ui_pyqt.py / ui_streamlit.py（DEPRECATED）
├── cli_ui.py                # 终端界面
├── game_profiles/           # 游戏档案：florr.yaml / space_invaders.yaml
├── skills/                  # 技能包
├── tools/                   # add_game.py / build_dist.py / cli_smoke.py / mcp_tools_check.py / static_audit.py
├── tests/                   # 14 个测试文件（743 用例，离线可跑）
├── scripts/check.sh         # 一条命令门禁
├── devplan/                 # PLAN / PROGRESS / AUDIT / OPS / TOOLS / PROFILE_SPEC / DIRECTION
├── packaging/               # Windows EXE / Android APK 构建
├── start_all.sh / stop_all.sh / watchdog.sh  # 一键启停 + 看门狗
├── knowledge_md/            # 自动创建，MD 知识库
├── knowledge_archive/       # 自动创建，超限归档区
└── run_logs/                # 自动创建，回合日志 / 汇报 / dry-run 动作明细
```

---

## 🗺️ 路线图（Roadmap）

| 版本 | 主题 | 状态 |
|------|------|------|
| v0.1 ~ v0.9 | 从 Florr 初版 → 完整 MCP / Skill / 游戏档案化 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v1.0 | 稳定底座版：对话指挥 + 接 MCP + Skill + 一键部署 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v1.1 ~ v1.9 | 监控大盘 / 自动汇报 / 档案登记 / 会话记忆 / 战绩 / 定时汇报 / 档案自检 / 安装包 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| 🚧 **v2.0** | **地基做实：可导入 / 可离线跑通 / 有测试 / 有门禁 / 文档与代码一致** | 进行中（S1~S13 见 PROGRESS） |

> ⚠️ **口径说明**：v0.1~v1.9 的「已完成」指**功能代码已存在且通过离线单测/冒烟**，不代表在真实 Florr.io 对局中验收过 —— 真实 LLM 决策、截图感知、键鼠操作在本机均无条件实测。判定依据见上方 [验证状态](#-验证状态)。

📚 完整开发计划见 [ROADMAP.md](ROADMAP.md) ｜ 原理与部署详解见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) ｜ 冲刺进度见 [devplan/PROGRESS.md](devplan/PROGRESS.md)

---

<div align="center">

**路线：从 Florr.io 专用，走向通用游戏 Agent** — 持续进化中 🚀

</div>
