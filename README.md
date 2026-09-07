# FlorrVLM-Agent

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

融合 `florr_powerful_tools`（YOLO 视觉识别）与 MCP 标准 Agent 架构的 florr.io 游戏智能体。

## 核心能力

1. **视频学习** — 解析本地教程视频，VLM 逐帧提取战术，写入 Markdown 知识库
2. **全实体预判** — 同时预判 BOSS/精英/小怪未来 1.2 秒位置，带置信度
3. **战斗评估** — 自身实力 vs 敌方威胁，动态决定 fight / cautious / retreat
4. **动态心态** — 面对不同怪物 + 自身实力，自动切换保守/均衡/激进
5. **组队协同** — 识别队友花瓣套装，队友输出→我方辅助，队友抗伤→我方输出
6. **拟人操作** — 移动固定小范围抖动，模拟真人手操
7. **BOSS 记忆** — 每 12 秒批量记录 BOSS 行为习惯到知识库
8. **死亡复盘** — 连续 2 帧死亡才判定，仅 BOSS/组队局生成复盘 md
9. **小硬盘适配** — 截图/视频帧用完立刻删，日志 500KB 滚动截断
10. **安全保护** — 鼠标碰屏幕四角自动暂停，YOLO 卡顿跳帧不崩溃

## 稀有度体系

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

- `highest_boss`：Unique / Eternal（紧急避险，实力动态调控）
- `boss`：Super
- `elite`：Ultra / Mythic / Legendary / Epic
- `normal`：Rare / Unusual / Common

## 文件结构

```
FlorrVLM-Agent/
├── perception_server.py    # YOLO 感知 HTTP 服务
├── mcp_server.py           # MCP 服务端 + MD 知识库
├── video_learner.py        # 视频解析学习
├── agent_main.py           # MCP 客户端主循环
├── predictor.py            # 全实体运动预判
├── combat_judge.py         # 战斗评估 + 套装 + 组队 + 动态心态
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── PROJECT_SUMMARY.md      # 完整文档（全部源码 + 原理 + 部署）
└── knowledge_md/           # 自动创建，MD 知识库
```

## 快速开始

```bash
# 1. 克隆外部依赖
git clone https://github.com/PANP2010/florr_powerful_tools.git
git clone https://github.com/OpenCloserOrg/OpenClaw.git

# 2. 安装依赖
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. 配置 API
cp .env.example .env
# 编辑 .env 填入 LLM / VLM 密钥

# 4. 启动（三个终端）
python perception_server.py          # 终端1：感知服务
python video_learner.py ./tutorial.mp4  # 终端2（可选）：学视频
python agent_main.py                 # 终端3：Agent 主程序
```

## MCP 工具（9 个）

`kb_list` `kb_search` `kb_write` `kb_append` `perceive_game` `predict_all_entities` `reset_predictor` `game_action` `handle_afk`

## 注意

- 教程视频需用户自行下载到本地，程序不联网下载
- 向量检索默认关闭，设置 `FLORR_VECTOR_SEARCH=1` 可开启（需额外安装依赖）
- 成就仅内存记录，程序退出清空
- 详见 `PROJECT_SUMMARY.md`
