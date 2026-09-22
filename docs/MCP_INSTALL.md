# 把 UGF 装到别的 Agent 上（MCP 接入指南）

> Universal-Game-Framework **不是一个 Agent**，而是一个**给别的 Agent 用的 MCP 能力包**：
> 装上之后，任何支持 MCP 的客户端（Kilo / Codex / OpenCode / WorkBuddy / Claude Desktop …）
> 就拥有了「看游戏画面 → 预判实体 → 评估战力 → 出动作 → 查/写知识库 → 复盘」这套能力。

---

## 一、三分钟装上

```bash
cd Universal-Game-Framework
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python tools/install_mcp.py --list                 # 看看能装到哪些客户端
python tools/install_mcp.py --target workbuddy     # 装到 WorkBuddy
python tools/install_mcp.py --target opencode      # 或装到 OpenCode
python tools/install_mcp.py --target custom --path /绝对路径/mcp.json   # 或任意客户端
```

装完在客户端的「连接器 / MCP 设置」里把 `ugf` 设为**信任**，重启客户端即可调用。

参数：`--dry-run` 只看不写 ｜ `--remove` 卸载 ｜ `--online` 关闭 dry-run（允许真实键鼠，**仅在授权环境**）。

---

## 二、它给你什么能力（16 个 MCP 工具）

| 类别 | 工具 | 说明 |
|---|---|---|
| 感知 | `perceive_game` | 取当前画面状态（含自身 HP / 实体列表），并自动喂给预判器 |
| 感知 | `predict_all_entities` | 全实体未来 1.2s 位置预判，带置信度，按威胁排序取前 8 |
| 感知 | `reset_predictor` | 清空预判历史（切局/重生后调用） |
| 动作 | `game_action` | 执行动作：move / attack / defend / synthesize / idle |
| 动作 | `switch_set` | 切换套装 |
| 动作 | `handle_afk` | 处理 AFK 人机验证弹窗 |
| 知识 | `kb_list` `kb_search` `kb_write` `kb_append` | 本地 MD 知识库读写检索 |
| 知识 | `kb_export` `kb_import` | 知识库打包备份 / 恢复 |
| 决策 | `switch_tactic` | 切换当前战术 |
| 维护 | `query_boss_history` | 查某个 BOSS 的历史习性 |
| 维护 | `clean_cache` | 清理临时文件 |
| 手册 | `ugf_guide` | 返回本服务使用手册（能力/工具清单/调用链/注意事项），第一次接入先调它 |

---

## 三、标准调用链（可直接抄）

**1) 摸清局面**
```
perceive_game() → predict_all_entities() → kb_search(keyword=当前最强敌人)
```

**2) 打一局**
```
perceive_game → predict_all_entities → （自行评估打/跑）→ game_action(action_type, x?, y?)
→ 每 N 轮 kb_append(战术/复盘) → 结束 kb_write(本局总结)
```

**3) 学一轮**
```
kb_search(关键词) → 有缺口 → kb_write(学到的战术) → 下一局引用
```

---

## 四、各客户端配置位置

| 客户端 | 配置文件 | 键名 |
|---|---|---|
| WorkBuddy | `~/.workbuddy/mcp.json` | `mcpServers` |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）/ `%APPDATA%\Claude\...`（Windows） | `mcpServers` |
| OpenCode | `~/.config/opencode/opencode.json` | `mcp` |
| VS Code / Cursor | `~/.vscode/mcp.json` 或工作区 `.vscode/mcp.json` | `servers` |
| Codex CLI | `~/.codex/config.toml` | `[mcp_servers.ugf]`（TOML，脚本只给指引，需手动加） |

手写配置等价形式：

```json
{
  "mcpServers": {
    "ugf": {
      "command": "/绝对路径/venv/bin/python",
      "args": ["/绝对路径/Universal-Game-Framework/mcp_server.py"],
      "env": { "UGF_DRY_RUN": "1", "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

---

## 五、验证装上了没

```bash
# 1) 服务本身能不能握手（stdio）
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | python mcp_server.py

# 2) 工具清单核对（16 个）
python tools/mcp_tools_check.py --strict

# 3) 安装器看到没有
python tools/install_mcp.py --list
```

---

## 六、注意事项

更多问答见 [FAQ.md](./FAQ.md)。

1. **默认 dry-run**（`UGF_DRY_RUN=1`）：安装器写入的配置**一定**带这个环境变量（除非显式 `--online`），
   所以刚装上时 `game_action` 只会校验参数并返回描述，绝不会动你的键鼠。：`game_action` **不会**真的动键鼠，只会校验并返回动作描述。确认接线无误后在授权环境下用 `--online` 或设 `UGF_DRY_RUN=0` 才放开。
2. **感知服务不是必须的**：没有 YOLO / 感知服务时，`perceive_game` 会降级为进程内合成帧（返回值里带 `_fallback` 标记），整条链路照样能跑通——这是刻意设计，方便外部 Agent 先联调再上真机。
3. **合规**：本能力包面向本地 / 自建 / 已授权环境。在他人运营的在线服务器上运行自动化程序违反其服务条款，框架不提供任何绕过手段。
4. **硬盘**：截图与视频帧用完即删，知识库体积有上限并会自动归档。
