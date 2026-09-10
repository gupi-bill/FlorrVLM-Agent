# FlorrVLM-Agent 项目总览

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

---

## 一、项目定位

基于 MCP (Model Context Protocol) 标准的 florr.io 游戏智能体，融合 YOLO 视觉识别、全实体运动预判、战斗评估、拟人操作、自我进化知识库。

### 核心能力

1. **视频学习** — 解析教程视频，VLM 逐帧提取战术，写入 Markdown 知识库；支持本地路径或 --auto 联网搜索下载（v0.4）
2. **全实体预判** — 同时预判 BOSS/精英/小怪未来 1.2 秒位置，带 0~1 置信度
3. **战斗评估** — 自身实力 vs 敌方总威胁，输出 fight / cautious_fight / retreat
4. **动态心态** — 面对不同怪物 + 自身实力，自动切换保守/均衡/激进
5. **组队协同** — 识别队友花瓣套装，队友输出→我方辅助，队友抗伤→我方输出
6. **拟人操作** — 移动固定小范围抖动，消除机器完美直线感
7. **BOSS 记忆** — 每 12 秒批量记录 BOSS 行为习惯到知识库
8. **死亡复盘** — 连续 2 帧死亡才判定，仅 BOSS/组队局生成复盘 md
9. **小硬盘适配** — 截图/视频帧用完立刻删，日志 500KB 滚动截断
10. **安全保护** — 鼠标碰屏幕四角自动暂停，YOLO 卡顿跳帧不崩溃

---

## 二、稀有度与实体分类

### 完整稀有度链（Florr.io 原生）

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

### 分类规则

| 分类 | 稀有度 | 威胁分 | 说明 |
|------|--------|--------|------|
| `highest_boss` | Unique, Eternal | 1000 | 最高威胁，紧急避险（实力动态调控） |
| `boss` | Super | 400 | 普通 BOSS |
| `elite` | Ultra, Mythic, Legendary, Epic | 120 | 精英怪 |
| `normal` | Rare, Unusual, Common | 15 | 普通小怪 |

> BOSS 判定依据是**稀有度**，不是名字带 "boss" 字符串。

---

## 三、外部依赖仓库（需自行 git clone）

| 项目 | 地址 | 用途 |
|------|------|------|
| florr_powerful_tools | https://github.com/PANP2010/florr_powerful_tools | YOLO 画面识别、AFK 弹窗 |
| OpenClaw | https://github.com/OpenCloserOrg/OpenClaw | Agent 底座参考、验证码模块 |

```bash
git clone https://github.com/PANP2010/florr_powerful_tools.git
git clone https://github.com/OpenCloserOrg/OpenClaw.git
```

---

## 四、自有文件清单（11 个）

```
FlorrVLM-Agent/
├── perception_server.py    # YOLO 感知 HTTP 服务 (127.0.0.1:5001)
├── mcp_server.py           # MCP 服务端，10 个工具，MD 知识库
├── video_learner.py        # 视频解析，VLM 提取战术（支持 --auto 联网）
├── video_sources.py        # v0.4 视频来源注册表（数据驱动，不写死平台）
├── agent_main.py           # MCP 客户端主循环，串联全部模块
├── predictor.py            # 全实体运动预判 + 置信度
├── combat_judge.py         # 战斗评估 + 套装 + 组队 + 动态心态
├── requirements.txt        # Python 依赖
├── .env.example            # API 密钥模板
├── .gitignore
├── README.md
├── PROJECT_SUMMARY.md      # 本文件
└── knowledge_md/           # 自动创建，MD 知识库
└── run_logs/               # 自动创建，滚动日志
```

---

## 五、核心原理

### 5.1 完整运行链路

```
每 0.5 秒循环：
  1. perception_server 截图 → /tmp/florr_frame.png
  2. YOLO 检测 → 输出 player + entities + afk_popup
  3. 立刻删除 /tmp/florr_frame.png
  4. MCP perceive_game() 拿到状态，自动喂给 predictor 更新实体历史
  5. MCP predict_all_entities() → 全部实体 1.2s 预判坐标 + 置信度（前8威胁）
  6. combat_judge 评估：自身实力 vs 敌方威胁 → 决策 + 推荐套装 + 心态
  7. MCP kb_search() 检索知识库相关战术
  8. LLM 综合：画面 + 预判 + 战斗评估 + 知识库 → 动作 JSON
  9. 移动坐标加随机抖动（模拟真人）
  10. MCP game_action() 执行键鼠
  11. 每 12 秒批量写 BOSS 行为记忆到 knowledge_md/

死亡处理：
  - 连续 2 帧 player.alive=false → 判定真实死亡
  - 仅 highest_boss/boss/组队局 → kb_write 生成复盘 md
  - 普通小怪局 → 不生成复盘，reset_predictor，节省硬盘
```

### 5.2 预判原理

- 内存 `deque(maxlen=10)` 保存每实体最近 10 帧坐标
- 取最早帧和最新帧算速度：`vx = (x_new - x_old) / delta_t`
- 预测坐标 = 当前坐标 + 速度 × 1.2 秒
- 置信度 = 帧数因子 × 速度惩罚（瞬移时置信度降低）
- 实体消失保留 0.4 秒历史，抵抗 YOLO 漏检抖动
- 非法/负数/越界坐标直接丢弃
- 输出按威胁分排序，只取前 8 个实体省 Token

### 5.3 战斗评估原理

- 敌方总威胁 = Σ 各实体威胁分（highest_boss=1000, boss=400, elite=120, normal=15）
- 威胁比 = 敌方总威胁 / 自身实力评分
- 威胁比 ≥1.4 → retreat（跑路）
- 0.8 ≤ 威胁比 <1.4 → cautious_fight（谨慎）
- 威胁比 <0.8 → fight（进攻）
- highest_boss 特殊处理：实力不足全力避险，实力接近谨慎周旋，实力充足可对抗
- 组队修正：队友输出多→我方辅助套，队友抗伤多→我方输出套

### 5.4 硬盘占用控制

| 数据 | 处理方式 | 保留/删除 |
|------|----------|-----------|
| 游戏截图 | YOLO 完立刻 os.remove | 删除 |
| 视频帧 | 每帧 VLM 完立刻删，结束 rmtree 目录 | 删除 |
| Ctrl+C 中断 | 信号捕获，自动清理全部临时帧 | 删除 |
| 知识库 md | 战术/复盘/BOSS记忆，永久保留 | 保留 |
| 运行日志 | run_logs/，超 500KB 截断旧内容 | 滚动 |
| 预判历史 | 内存 deque，程序退出消失 | 不写盘 |
| 成就 | 仅内存 set，程序退出清空 | 不写盘 |

---

## 六、MCP 工具列表（10 个）

| 工具 | 参数 | 说明 |
|------|------|------|
| `kb_list` | 无 | 列出知识库全部 md |
| `kb_search` | `keyword` | 关键词检索（向量检索预留开关，默认关） |
| `kb_write` | `filename`, `markdown_content` | 写入/覆盖 md |
| `kb_append` | `filename`, `markdown_content` | 追加到已有 md |
| `perceive_game` | 无 | 获取游戏状态，自动更新预判历史 |
| `predict_all_entities` | 无 | 全部实体 1.2s 预判，前8威胁 |
| `reset_predictor` | 无 | 清空预判历史 |
| `game_action` | `action_type`, `x?`, `y?` | 键鼠动作 move/attack/defend/synthesize/idle（move 带拟人路径微扰+偶发停顿） |
| `switch_set` | `set_name` | 切换花瓣套装 combat/tank/retreat/chase/team（按数字键） |
| `handle_afk` | 无 | 触发 AFK 弹窗处理 |

---

## 七、全套提示词

### 7.1 视频学习 VLM 提示词
```
你正在观看 florr.io 游戏教程视频的一帧画面。
请仔细观察：玩家使用的花瓣组合、面对的怪物/BOSS、走位方式、操作意图。
提炼一条可复用的游戏战术，用一句话输出，不要多余解释。
```

### 7.2 Agent 决策系统提示词
```
你是 FlorrVLM-Agent，一个玩 florr.io 的游戏智能体，目标是优先保命、持续作战。
可调用工具：perceive_game, kb_search, predict_all_entities, game_action, kb_write, handle_afk, reset_predictor。
决策规则：
- afk_popup=true 优先处理验证
- 遇 highest_boss(Unique/Eternal) 时，根据自身实力评估：实力不足全力避险，实力充足可谨慎周旋
- 预判置信度<0.6 时，降低对预判坐标的依赖，更多参考当前画面
- 每步只输出一个动作 JSON：{"action":"move","x":100,"y":200}
动作：move(x,y) / attack / defend / synthesize / idle。
```

---

## 八、部署步骤

```bash
# 1. 解压并进入项目
cd FlorrVLM-Agent

# 2. 克隆外部依赖
git clone https://github.com/PANP2010/florr_powerful_tools.git
git clone https://github.com/OpenCloserOrg/OpenClaw.git

# 3. 系统依赖（Debian/Ubuntu）
sudo apt update
sudo apt install -y python3-pip python3-venv scrot imagemagick xdotool

# 4. Python 环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. 配置 API 密钥
cp .env.example .env
# 编辑 .env 填入 LLM / VLM 的 API 地址和密钥

# 6. 启动（三个终端）
# 终端1：YOLO 感知服务
python perception_server.py

# 终端2（可选）：学习教程视频构建知识库
python video_learner.py ./florr_tutorial.mp4
python video_learner.py --auto --query "florr.io教程"   # v0.4 自动搜索下载再学（需 yt-dlp）

# 终端3：启动 Agent
python agent_main.py
```

---

## 九、注意事项

1. **florr_powerful_tools 入口**：检测脚本名可能不是 `detect.py`，`perception_server.py` 已自动备选探测（main.py / yolo_detect.py / infer.py / run.py）
2. **弱 CPU 机器**：不要本地跑 VLM/LLM，全部走云端 API；预判和战斗评估是纯数学运算，极轻量
3. **教程视频**：需用户自行下载到本地，程序不联网下载
4. **向量检索**：默认关闭，设置环境变量 `FLORR_VECTOR_SEARCH=1` 可开启（需安装 chromadb + sentence-transformers）
5. **成就系统**：仅内存记录，程序退出清空，不持久化
6. **复盘过滤**：只有 highest_boss/boss/组队局生成复盘 md，普通小怪局不写，保护小硬盘
7. **API 密钥安全**：`.env` 已加入 `.gitignore`，不要提交到公开仓库
8. **反作弊**：florr.io 有 AFK 检测和行为分析，长时间挂机有封号风险
