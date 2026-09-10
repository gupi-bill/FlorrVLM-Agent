<div align="center">

# 🎮 FlorrVLM-Agent

**一个会自己玩游戏的通用 Agent · From Florr.io → 所有游戏**

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/Model%20Context%20Protocol-%E6%A0%87%E5%87%86%20Agent-green)
![v1.0](https://img.shields.io/badge/Version-正在%20v1.0%20%E5%89%8D%E6%9C%9F-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

融合 **YOLO 视觉识别** + **MCP 标准 Agent 架构**的游戏智能体。

不只会打 Florr.io —— 它正在进化成一条通用流水线：**问游戏 → 查资料 → 确认能力 → 开玩 → 汇报**。

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
| 💾 **小硬盘适配** | 临时文件用完即删，日志按天滚动 + 压缩清理 |
| 🛡️ **安全保护** | 鼠标碰四角自动暂停，YOLO 卡顿跳帧不崩溃 |

## 🔬 稀有度体系

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

- `highest_boss`：Unique / Eternal（紧急避险）
- `boss`：Super 　· 　`elite`：Ultra / Mythic / Legendary / Epic　·　`normal`：Rare / Unusual / Common

---

## 🗺️ 路线图（Roadmap）

> **目标：稳定底座版 v1.0 = 一个真正的通用 Agent，像普通 Agent 一样工作。**

| 版本 | 主题 | 状态 |
|------|------|------|
| ✅ v0.5 | 完整 MCP 生态（参数配置化 / MCP 工具 / 面板 / 日志治理） | 已完成 |
| 🚧 **v0.6** | **Agent 形态正式化**：交互式对话 CLI、自我说明、会话持久化 | 规划中 |
| 🚧 **v0.7** | **MCP Client**：主动连接外部 MCP，外部能力为己用 | 规划中 |
| 🚧 **v0.8** | **Skill 机制**：按需加载技能包，如普通 Agent 装配能力 | 规划中 |
| 🚧 **v0.9** | **全通用化**：游戏档案化，核心解耦，切游戏零改核心 | 规划中 |
| 🚧 **v1.0** | **稳定底座版**：完整可用、对话指挥、接 MCP + Skill | 下一个 |

📚 完整开发计划见 [ROADMAP.md](ROADMAP.md) ｜ 原理与部署详解见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

---

## 🏗️ 当前架构

```
┌────────────────────────────────────────────────────────────┐
│                       对话 / 命令行指挥                      │
│   detect → research → ensure → play → report（通用骨架）      │
└──────────────┬──────────────────────────────┬─────────────┘
               ▼                              ▼
        ┌──────────────┐             ┌──────────────────┐
        │  MCP Server   │             │  MCP Client      │
        │  对外暴露工具   │             │  主动接外部服务    │
        └──────┬───────┘             └────────┬─────────┘
               │                              │
        ┌──────▼──────┐              ┌─────────▼────────┐
        │ 游戏档案(config)│◄──热加载──►│ 核心引擎(通用)      │
        │ Florr 专属    │              │ 感知/预判/评估/执行 │
        └─────────────┘              └──────────────────┘
```

## ⚙️ 一键启动

```bash
bash start_all.sh   # 感知服务 + MCP + Agent 主循环 + 面板
bash stop_all.sh    # 优雅停止并清理临时文件
```

## 🖥️ 简易面板

启动后浏览器打开 `http://127.0.0.1:5002`，实时查看：运行日志 / 知识库 / 状态。

## 🔧 快速开始

```bash
# 1. 克隆外部依赖
git clone https://github.com/PANP2010/florr_powerful_tools.git
git clone https://github.com/OpenCloserOrg/OpenClaw.git

# 2. 安装依赖
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. 配置 API
cp .env.example .env   # 填入 LLM / VLM 密钥

# 4. 启动
python perception_server.py                         # 感知服务
python video_learner.py --auto --query "florr.io教程"  # (可选) 联网学习
python agent_main.py                                # Agent 主程序
```

## 🧩 MCP 工具（13 个）

| 类别 | 工具 |
|------|------|
| 📚 知识库 | `kb_list` `kb_search` `kb_write` `kb_append` `query_boss_history` `switch_tactic` |
| 👁️ 感知 | `perceive_game` `predict_all_entities` `reset_predictor` |
| 🕹️ 动作 | `game_action` `switch_set` `handle_afk` |
| 🧹 维护 | `clean_cache` |

## 📁 文件结构

```
FlorrVLM-Agent/
├── agent_main.py        # MCP Client 主循环
├── mcp_server.py        # MCP Server + MD 知识库
├── predictor.py         # 全实体运动预判
├── combat_judge.py      # 战斗评估/套装/组队/心态
├── perception_server.py # YOLO 感知 HTTP 服务
├── video_learner.py     # 视频解析学习(--auto 联网)
├── video_sources.py     # 视频来源注册表
├── config.py / config.yaml  # 参数配置 + 热加载
├── admin_panel.py       # 简易本地面板
├── start_all.sh / stop_all.sh  # 一键启停
└── knowledge_md/        # 自动创建，MD 知识库
```

---

<div align="center">

**<ins>路线 · 从 Florr.io 专用，走向通用游戏 Agent</ins>** — 持续进化中 🚀

</div>