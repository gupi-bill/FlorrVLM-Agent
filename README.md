<div align="center">

# 🎮 FlorrVLM-Agent

**一个会自己玩游戏的通用 Agent · From Florr.io → 所有游戏**

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-%E6%A0%87%E5%87%86%20Agent-green)
![v2.0](https://img.shields.io/badge/Version-v2.0%20%E8%B5%B7%E6%AD%A5-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

融合 **YOLO 视觉识别** + **MCP 标准 Agent 架构**的游戏智能体。

不只会打 Florr.io —— 它已经是一条通用流水线：**detect 问游戏 → research 查资料 → ensure 确认能力 → play 开玩 → report 汇报**。

</div>

---

## ✨ 核心能力

| 能力 | 说明 |
|------|------|
| 🎬 **视频学习** | 解析教程视频，VLM 逐帧提取战术写入知识库 |
| 🔮 **全实体预判** | 同时预判 BOSS/精英/小怪未来 1.2s 位置，带置信度 |
| ⚔️ **战斗评估** | 自身实力 vs 敌方威胁，动态决定 fight / cautious / retreat |
| 🧠 **动态心态** | 面对不同怪物 + 自身实力，自动切换保守/均衡/激进 |
| 👥 **组队协同** | 识别队友套装，自动分工：输出 / 辅助 / 掩护 |
| 🕹️ **拟人操作** | 移动抖动 + 随机停顿 + 路径微扰，降低脚本感 |
| 🧠 **BOSS 记忆** | 每 12s 批量记录 BOSS 行为习惯到知识库 |
| 📝 **死亡复盘** | 连续 2 帧死亡才判定，BOSS/组队局自动生成复盘 |
| 💬 **对话指挥** | `agent_cli.py` 交互式命令，像普通 Agent 一样问答编排 |
| 🎚️ **自动调参** | 按命中率/死亡数自动微调战斗阈值，热加载生效 |
| 🧩 **Skill + 外部 MCP** | 能接技能包、主动连外部 MCP，能力按需装配 |
| 🎮 **游戏档案化** | 一款游戏一份 YAML 档案，切换游戏零改核心 |
| 📊 **监控大盘** | 本地网页实时看指标卡 / BOSS 预判 / 日志 / 资源占用 |
| 🔔 **自动汇报** | 每局结束自动出报告，可推送本地 / Webhook |
| 💾 **导入导出** | 知识库打包备份 / 一键恢复，知识本地化可迁移 |
| 📦 **多平台安装包** | Linux .deb / 便携版 / Windows EXE / Android APK |

## 🔬 稀有度体系

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

- `highest_boss`：Unique / Eternal（紧急避险）
- `boss`：Super　·　`elite`：Ultra / Mythic / Legendary / Epic　·　`normal`：Rare / Unusual / Common

---

## 🗺️ 路线图（Roadmap）

| 版本 | 主题 | 状态 |
|------|------|------|
| ✅ v0.1~v0.9 | 从 Florr 初版 → 完整 MCP / Skill / 游戏档案化 | 已完成 |
| ✅ v1.0 | 稳定底座版：对话指挥 + 接 MCP + Skill + 一键部署 | 功能就绪(待实机验收) |
| ✅ v1.1~v1.9 | 监控大盘 / 自动汇报 / 档案登记 / 会话记忆 / 战绩 / 定时汇报 / 档案自检 / 安装包 | 已完成 |
| 🚧 **v2.0** | **Florr.io 高级拟人玩家** | 进行中 |

📚 完整开发计划见 [ROADMAP.md](ROADMAP.md) ｜ 原理与部署详解见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

---

## 🏗️ 当前架构

```
┌────────────────────────────────────────────────────────────┐
│                   agent_cli.py 对话 / 命令行指挥             │
│   detect → brief → research → ensure → play → report        │
└──────────────┬──────────────────────────────┬─────────────┘
               ▼                              ▼
        ┌──────────────┐             ┌──────────────────┐
        │  MCP Server   │             │  MCP Client      │
        │  对外暴露工具   │             │  主动接外部服务    │
        └──────┬───────┘             └────────┬─────────┘
               │                              │
        ┌──────▼──────┐              ┌─────────▼────────┐
        │ game_profiles│◄──热加载──►│ 核心引擎(通用)      │
        │ 游戏档案(YAML) │             │ 感知/预判/评估/执行 │
        └─────────────┘              └──────────────────┘
```

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

一条命令拉起整套：`bash start_all.sh`（感知 + MCP + Agent 主循环 + 面板），`bash stop_all.sh` 优雅停止。
面板：浏览器打开 `http://127.0.0.1:5002`。

## 📦 安装包

```bash
python tools/build_dist.py all      # Linux .deb + 便携版
```
Windows EXE / Android APK 见 [packaging/README.md](packaging/README.md)。

## 🧩 MCP 工具（15 个）

| 类别 | 工具 |
|------|------|
| 📚 知识库 | `kb_list` `kb_search` `kb_write` `kb_append` `kb_export` `kb_import` |
| 👁️ 感知 | `perceive_game` `predict_all_entities` `reset_predictor` |
| 🕹️ 动作 | `game_action` `switch_set` `handle_afk` |
| 🧹 维护 | `clean_cache` `query_boss_history` `switch_tactic` |

## 📁 文件结构

```
FlorrVLM-Agent/
├── agent_cli.py          # 对话指挥入口（交互 + -c 单命令）
├── agent_main.py         # MCP Client 主循环
├── mcp_server.py / mcp_connector.py  # 服务端 / 外部 MCP 连接
├── predictor.py          # 全实体运动预判
├── combat_judge.py       # 战斗评估/套装/组队/心态
├── perception_server.py  # YOLO 感知 HTTP 服务
├── video_learner.py / video_sources.py  # 视频学习 + 来源
├── session.py / report_notifier.py      # 会话记忆 / 自动汇报
├── kb_maintainer.py      # 知识库压缩/归档/导入导出
├── auto_tuner.py / game_profile_check.py  # 自动调参 / 档案自检
├── boot_check.py / watchdog.sh / Dockerfile / florr-agent.service.example  # 稳定性
├── admin_panel.py / cli_ui.py  # 面板 / 界面
├── config.py / config.yaml    # 参数 + 热加载
├── game_profiles/            # 游戏档案（florr.yaml）
├── skills/                   # 技能包
├── tools/                    # add_game.py / build_dist.py
├── packaging/                # Windows EXE / Android APK 构建
├── start_all.sh / stop_all.sh  # 一键启停
└── knowledge_md/             # 自动创建，MD 知识库
```

---

<div align="center">

**<ins>路线 · 从 Florr.io 专用，走向通用游戏 Agent</ins>** — 持续进化中 🚀

</div>