# Universal-Game-Framework 项目总览

> ⚠️ **声明：仅用于本地 AI 智能体技术研究。在 florr.io 官方服务器运行 bot 违反游戏服务条款，可能导致账号封禁。**

---

## 一、项目定位

**不是 Agent —— 是装到别的 Agent 上的「游戏能力包」（MCP 服务）。**

基于 MCP (Model Context Protocol) 标准，把 YOLO 视觉识别、全实体运动预判、战斗评估、拟人操作、自我进化知识库
打包成 16 个 MCP 工具，供任意支持 MCP 的客户端（WorkBuddy / OpenCode / Kilo / Codex / Claude Desktop …）调用。
已从 Florr.io 专用演化为**通用游戏能力层**：一款游戏一份档案，切换游戏零改核心。

> 装上只需一条命令：`python tools/install_mcp.py --target workbuddy`（详见 `docs/MCP_INSTALL.md`）。
> 仓库自带的对话 CLI / 主循环 / 监控大盘仅用于本地调试。

### 核心能力

1. **视频学习** — 解析教程视频，VLM 逐帧提取战术写入知识库；支持本地路径或 `--auto` 联网搜索下载
2. **全实体预判** — 同时预判 BOSS/精英/小怪未来 1.2 秒位置，带置信度
3. **战斗评估** — 自身实力 vs 敌方总威胁，输出 fight / cautious_fight / retreat
4. **动态心态** — 面对不同怪物 + 自身实力，自动切换保守/均衡/激进
5. **组队协同** — 识别队友套装，队友输出→我方辅助，队友抗伤→我方输出
6. **拟人操作** — 移动抖动 + 随机停顿 + 路径微扰，消除机器感
7. **BOSS 记忆** — 每 12 秒批量记录 BOSS 行为习惯到知识库
8. **死亡复盘** — 连续 8 帧判定死亡（`death_frame_threshold` 可配），BOSS/组队局自动生成复盘
9. **对话指挥** — `agent_cli.py` 交互式命令，像普通 Agent 一样问答编排（v0.6）
10. **Skill + 外部 MCP** — 接技能包、主动连外部 MCP（v0.7/v0.8）
11. **游戏档案化** — 每款游戏一份 YAML 档案，热加载切换（v0.9）
12. **会话记忆 / 断点续玩** — 重启自动恢复进度（v1.4）
13. **多局战绩 / 汇总统计** — 每局自动入档（v1.5/v1.6）
14. **自动汇报** — 每局结束自动出报告，可推送本地/Webhook（v1.2）
15. **自动调参** — 按命中率/死亡数自动微调战斗阈值，热加载（v1.0）
16. **知识库导入导出** — 打包备份 / 一键恢复，知识本地化可迁移（v2.0）
17. **多平台安装包** — Linux .deb / 便携版 / Windows EXE / Android APK（v1.9/v2.0）

---

## 二、稀有度与实体分类

### 完整稀有度链（Florr.io 原生）

`Common < Unusual < Rare < Epic < Legendary < Mythic < Ultra < Super < Unique = Eternal`

### 分类规则（在 game_profiles/florr.yaml 定义）

| 分类 | 稀有度 | 威胁分 | 说明 |
|------|--------|--------|------|
| `highest_boss` | Unique, Eternal | 1000 | 最高威胁，紧急避险 |
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

## 四、自有文件结构

```
Universal-Game-Framework/
├── agent_cli.py            # 对话指挥入口（交互 + -c 单命令）——主入口
├── agent_main.py           # MCP Client 主循环
├── mcp_server.py           # MCP 服务端（16 个工具，MD 知识库）
├── mcp_connector.py        # 外部 MCP 主动连接（v0.7）
├── skill_manager.py / skills/  # 技能包机制（v0.8）
├── predictor.py            # 全实体运动预判 + 置信度
├── combat_judge.py         # 战斗评估 + 套装 + 组队 + 动态心态
├── game_profile_check.py   # 游戏档案自检器（v1.8）
├── perception_server.py    # YOLO 感知 HTTP 服务
├── video_learner.py / video_sources.py  # 视频学习 + 来源注册表
├── session.py              # 会话记忆 & 断点续玩（v1.4）
├── report_notifier.py      # 自动汇报 & 多渠道通知（v1.2）
├── kb_maintainer.py        # 知识库压缩/归档/导入导出（v1.0/v2.0）
├── auto_tuner.py           # 自动调参（v1.0）
├── boot_check.py           # 启动自检（v1.0）
├── watchdog.sh / florr-agent.service.example / Dockerfile  # 稳定性
├── admin_panel.py          # 可视化监控大盘（v1.1/v1.6）
├── launcher.py             # 统一启动入口（自动选 UI + 离线开关透传，v2.0）
├── ui/legacy/              # 已归档前端：ui_pyqt.py / ui_streamlit.py（DEPRECATED）
├── cli_ui.py               # CLI 界面（彩色面板）
├── config.py / config.yaml # 参数配置 + 热加载
├── game_profiles/          # 游戏档案：florr.yaml / space_invaders.yaml
├── tools/                  # add_game.py / build_dist.py / cli_smoke.py / mcp_tools_check.py / static_audit.py
├── tests/                  # 14 个测试文件（743 用例，全离线可跑）
├── scripts/check.sh        # 一条命令门禁（语法 + 自检 + 档案 + 测试）
├── devplan/                # PLAN / PROGRESS / AUDIT / OPS / TOOLS / PROFILE_SPEC / DIRECTION
├── packaging/              # Windows EXE / Android APK 构建
├── start_all.sh / stop_all.sh / watchdog.sh
├── requirements.txt / requirements-dev.txt / .env.example / .gitignore
├── knowledge_md/           # 自动创建，MD 知识库
├── knowledge_archive/      # 自动创建，超限归档区
└── run_logs/               # 自动创建，回合日志 / 汇报 / dry-run 动作明细
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
  - 连续 8 帧 player.alive=false（`death_frame_threshold`）→ 判定真实死亡
  - 仅 highest_boss/boss/组队局 → kb_write 生成复盘 md
  - 普通小怪局 → 不生成复盘，reset_predictor，节省硬盘
```

### 5.2 Agent 通用骨架（v1.0+）

任何一款游戏都走同一套生命周期，由对话（agent_cli.py）编排：

```
detect(这是什么游戏) → brief(开玩前了解) → research(去查资料)
→ ensure(确认能玩) → play(游戏主循环) → report(汇报) → notify(推送)
```

- 每款游戏一份 `game_profiles/<name>.yaml`，切换游戏零改核心
- `session.py` 跨启动记忆进度 / 战况 / brief（断点续玩）
- 打完一局自动 `report_notifier.py` 生成报告并可推送

### 5.3 预判原理

- 内存 `deque(maxlen=10)` 保存每实体最近 10 帧坐标
- 取最早帧和最新帧算速度：`vx = (x_new - x_old) / delta_t`
- 预测坐标 = 当前坐标 + 速度 × 1.2 秒
- 置信度 = 帧数因子 × 速度惩罚（瞬移时置信度降低）
- 实体消失保留 0.4 秒历史，抵抗 YOLO 漏检抖动
- 非法/负数/越界坐标直接丢弃
- 输出按威胁分排序，只取前 8 个实体省 Token

### 5.4 战斗评估原理

- 敌方总威胁 = Σ 各实体威胁分（highest_boss=1000, boss=400, elite=120, normal=15）
- 威胁比 = 敌方总威胁 / 自身实力评分
- 威胁比 ≥1.4 → retreat（跑路）
- 0.8 ≤ 威胁比 <1.4 → cautious_fight（谨慎）
- 威胁比 <0.8 → fight（进攻）
- highest_boss 特殊处理：实力不足全力避险，实力接近谨慎周旋，实力充足可对抗
- 组队修正：队友输出多→我方辅助套，队友抗伤多→我方输出套

### 5.5 硬盘占用控制

| 数据 | 处理方式 | 保留/删除 |
|------|----------|-----------|
| 游戏截图 | YOLO 完立刻 os.remove | 删除 |
| 视频帧 | 每帧 VLM 完立刻删，结束 rmtree 目录 | 删除 |
| Ctrl+C 中断 | 信号捕获，自动清理全部临时帧 | 删除 |
| 知识库 md | 战术/复盘/BOSS记忆，体积上限超限自动归档 | 保留(受控) |
| 运行日志 | run_logs/，按天滚动 + 保留期压缩清理 | 滚动 |
| 预判历史 | 内存 deque，程序退出消失 | 不写盘 |

---

## 六、MCP 工具列表（16 个）

| 工具 | 参数 | 说明 |
|------|------|------|
| `kb_list` | 无 | 列出知识库全部 md |
| `kb_search` | `keyword` | 关键词检索（向量检索预留开关，默认关） |
| `kb_write` | `filename`, `markdown_content` | 写入/覆盖 md |
| `kb_append` | `filename`, `markdown_content` | 追加到已有 md |
| `kb_export` | 无 | 导出整个知识库为 tar.gz 备份（v2.0） |
| `kb_import` | `backup_path` | 从备份恢复知识库（v2.0） |
| `perceive_game` | 无 | 获取游戏状态，自动更新预判历史 |
| `predict_all_entities` | 无 | 全部实体 1.2s 预判，前8威胁 |
| `reset_predictor` | 无 | 清空预判历史 |
| `game_action` | `action_type`, `x?`, `y?` | 键鼠动作 move/attack/defend/synthesize/idle |
| `switch_set` | `set_name` | 切换花瓣套装 combat/tank/retreat/chase/team |
| `handle_afk` | 无 | 触发 AFK 弹窗处理 |
| `query_boss_history` | `boss_name` | 查询 BOSS 历史习性 |
| `clean_cache` | 无 | 清理临时文件 |
| `switch_tactic` | `tactic` | 切换战术套装 |

---

## 七、部署步骤

```bash
# 1. 进入项目
cd Universal-Game-Framework

# 2. 克隆外部依赖（Florr 实机才需要）
git clone https://github.com/PANP2010/florr_powerful_tools.git

# 3. 系统依赖（Debian/Ubuntu）
sudo apt update
sudo apt install -y python3-pip python3-venv scrot imagemagick xdotool

# 4. Python 环境
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 5. 配置 API 密钥
cp .env.example .env    # 编辑填入 LLM / VLM 的 API 地址和密钥

# 6. 一键启动（或分步启动）
bash start_all.sh       # 感知 + MCP + Agent 主循环 + 面板

# 7. 对话指挥（另一终端）
python agent_cli.py            # 交互式
python agent_cli.py -c play 0  # 单命令跑主循环
```

### 打安装包

```bash
python tools/build_dist.py all        # Linux .deb + 便携版
```
Windows EXE / Android APK 构建详见 [packaging/README.md](packaging/README.md)。

---

## 八、版本进度

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.1~v0.3 | Florr 初版 + 稳定性 + 基础战术扩充 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v0.4~v0.5 | 学习闭环 + 完整 MCP 生态 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v0.6~v0.9 | Agent 形态 + 外部 MCP + Skill + 通用化 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v1.0~v1.9 | 稳定底座 + 大盘/汇报/会话/战绩/自检/安装包 | 代码已落地 ✅ --- 实机未验证 ⚠️ |
| v2.0 | 地基做实：离线可跑通 + 743 用例 + 一条命令门禁 + 文档与代码一致 | 🚧 进行中（S1~S14，见 devplan/PROGRESS.md） |

> ⚠️ **口径**：「✅ 完成」= 功能代码存在且通过**离线**单测/冒烟；真实 LLM 决策、截图感知、键鼠操作在本机无条件实测，故不构成实机验收。
> 冲刺期实测校准详见第十节。

---

## 九、注意事项

1. **florr_powerful_tools 入口**：`perception_server.py` 已自动备选探测检测脚本（main.py / yolo_detect.py / infer.py / run.py）
2. **弱 CPU 机器**：不要本地跑 VLM/LLM，全部走云端 API；预判和战斗评估是纯数学运算，极轻量
3. **向量检索**：默认关闭，设置环境变量 `FLORR_VECTOR_SEARCH=1` 可开启（需安装 chromadb + sentence-transformers）
4. **知识库导入导出**：`kb_export` / `kb_import`（或 kb_maintainer.py --export / --import-from），备份文件在 kb_backups/
5. **API 密钥安全**：`.env` 已加入 `.gitignore`，不要提交到公开仓库
6. **离线可跑（v2.0）**：无密钥 / 无 X server / 无 YOLO 时用 `UGF_DRY_RUN=1` + `UGF_PERCEPTION_BACKEND=mock` 即可跑通全链路；`bash scripts/check.sh --fast` 一条命令复核地基

---

## 十、v2.0 冲刺实测状态（2026-09-21 ~ 09-22）

> 冲刺目标不是加新功能，而是**把地基做实**：可导入、可离线跑通、有测试、有门禁、文档与代码一致。
> 计划 [devplan/PLAN.md](devplan/PLAN.md) ｜ 进度 [devplan/PROGRESS.md](devplan/PROGRESS.md) ｜ 运维口径 [devplan/OPS.md](devplan/OPS.md) ｜ 工具清单 [devplan/TOOLS.md](devplan/TOOLS.md) ｜ 档案规范 [devplan/PROFILE_SPEC.md](devplan/PROFILE_SPEC.md)

### 一条命令门禁

```bash
bash scripts/check.sh          # compileall → boot_check → game_profile_check → pytest
bash scripts/check.sh --fast   # 秒级：语法 + 启动自检 + 档案校验
```
退出码 = 失败环节编号：`1` 语法 / `2` 启动自检 / `3` 游戏档案 / `4` 单元测试。

### 阶段产物一览

| 阶段 | 产物 |
|---|---|
| S1 | `.gitattributes`、`.gitignore` 增补、requirements 三段分组（移除 31MB 构建产物出版本库） |
| S2 | `tools/static_audit.py`、`devplan/AUDIT.md`（mcp<2 兼容、cv2 软依赖） |
| S3 | `tests/test_predictor.py`（46）—— 抖动惩罚、NaN 防御、分类逐帧重算 |
| S4 | `tests/test_combat_judge.py`(64)、`test_auto_tuner.py`(26) —— 逃生优先于协同、冷静期、脏数据兜底 |
| S5 | `tests/test_session.py`(68)、`test_report_notifier.py`(33)、`test_skill_manager.py`(34) |
| S6 | `perception_server.py` 重写（mock / auto / http + `--selftest`）、`test_perception_server.py`(99) |
| S7 | `agent_main.py` dry-run 分支、`test_agent_main.py`(87)、`devplan/SMOKE_S7.md` |
| S8 | `tools/cli_smoke.py`（31 命令矩阵）、`test_agent_cli.py`(48)、`devplan/SMOKE_S8.md` |
| S9 | `tools/mcp_tools_check.py`、`test_mcp_server.py`(109)、`devplan/TOOLS.md` |
| S10 | `tools/add_game.py` v2.0、`test_game_profiles.py`(38)、`devplan/PROFILE_SPEC.md` |
| S11 | `launcher.py`、`test_launcher.py`(26)、`ui/legacy/` 归档 |
| S12 | `boot_check.py` v2.0、三脚本 v2.0、`Dockerfile` v2.0、`test_ops.py`(26)、`devplan/OPS.md` |
| S13 | `scripts/check.sh`、`tests/test_docs.py`（文档与代码一致性）、三份文档同步 |

### 已实测（离线）

| 项 | 结论 |
|---|---|
| 单元测试 | **743 用例全绿** |
| 启动自检 | ERROR 0 / WARN 6，每条附降级指引 |
| MCP 工具 | 16 个全部可注册 / 可调用 / schema 正确 |
| CLI | 31 条命令矩阵，0 traceback、0 卡死 |
| 主循环 | 离线 5 轮全链路跑通（感知 → 预判 → 决策 → 动作 → 记忆 → 复盘 → 汇报） |
| 游戏档案 | florr / space_invaders 两份 `--strict` 全过 |

### 未验证（受本机环境限制）

真实 LLM/VLM 决策（无密钥）· 真实截图 + YOLO（无 X server / 无权重）· 键鼠实操（无 GUI）· 联网检索与 Webhook（无网络）· 容器构建（无 docker）· GUI 真实渲染。
以上均已内置 mock / dry-run / 降级分支，链路可跑但结论待实机确认。
6. **反作弊**：florr.io 有 AFK 检测和行为分析，长时间挂机有封号风险