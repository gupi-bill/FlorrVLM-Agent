# MCP 工具清单核对表（v2.0 S9）

> 生成方式：`python tools/mcp_tools_check.py`（`--json` 出机器可读，`--strict` 非零退出码）
> 单元测试：`tests/test_mcp_server.py`（109 用例）
> 核对日期：2026-09-21 · MCP SDK **2.2.0**（1.x / 2.x 双兼容已验证）

## 一、结论

README 宣称的 **15 个工具**与实际注册的 **15 个**逐字一致，全部可列举、可调用、返回可读文本。
清单核对、逐工具调用、知识库往返三项检查 **全部 PASS**。

## 二、工具清单（README ↔ 代码）

| # | 类别 | 工具 | 必填参数 | 文档 | 代码 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 📚 知识库 | `kb_list` | — | ✅ | ✅ | OK |
| 2 | 📚 知识库 | `kb_search` | `keyword` | ✅ | ✅ | OK |
| 3 | 📚 知识库 | `kb_write` | `filename`, `markdown_content` | ✅ | ✅ | OK |
| 4 | 📚 知识库 | `kb_append` | `filename`, `markdown_content` | ✅ | ✅ | OK |
| 5 | 📚 知识库 | `kb_export` | — | ✅ | ✅ | OK |
| 6 | 📚 知识库 | `kb_import` | `backup_path` | ✅ | ✅ | OK |
| 7 | 👁️ 感知 | `perceive_game` | — | ✅ | ✅ | OK |
| 8 | 👁️ 感知 | `predict_all_entities` | — | ✅ | ✅ | OK |
| 9 | 👁️ 感知 | `reset_predictor` | — | ✅ | ✅ | OK |
| 10 | 🕹️ 动作 | `game_action` | `action_type` | ✅ | ✅ | OK |
| 11 | 🕹️ 动作 | `switch_set` | `set_name` | ✅ | ✅ | OK |
| 12 | 🕹️ 动作 | `handle_afk` | — | ✅ | ✅ | OK |
| 13 | 🧹 维护 | `clean_cache` | — | ✅ | ✅ | OK |
| 14 | 🧹 维护 | `query_boss_history` | — | ✅ | ✅ | OK |
| 15 | 🧹 维护 | `switch_tactic` | `tactic_file` | ✅ | ✅ | OK |

核对维度：名称一致（无多/少/改名）、每个工具有非空描述、`inputSchema.type == "object"`、必填参数与函数签名一致、真实调用返回非空且非 `is_error`。

## 三、本轮发现并修复的缺陷

| 编号 | 级别 | 位置 | 问题 | 处理 |
|---|---|---|---|---|
| M1 | 阻断 | `kb_write` / `kb_append` | `filename` 未清洗，`../../evil.md` 直接 `os.path.join(KB_DIR, filename)` 写到知识库之外；空名会落到 `KB_DIR` 目录本身抛 `IsADirectoryError` | 新增 `_safe_name()` + 集中式 `_resolve_kb_path()`，`normpath` + `commonpath` 二次守门 |
| M2 | 阻断 | `kb_list` / `kb_search` | `game_name=".."` 仅把 `/` 替换成 `-`，`..` 原样保留 → 列出知识库**上一级**目录 | 同上，走 `_safe_name()`，空结果回退根目录 |
| M3 | 阻断 | `kb_maintainer.export/import_backup` | 打包用 `basename` 拍平子目录：`knowledge_md/florr/boss.md` → `knowledge_md/boss.md`，按游戏分类的知识库往返后**全部丢到根目录**，同名文件互相覆盖 | `export` 保留相对路径；`import` 按包内顶层目录还原并重建子目录 |
| M4 | 高 | `kb_maintainer.import_backup` | `knowledge_archive/*` 一律解进活跃库 → 已归档笔记被"复活"，`kb_max_mb` 体积控制形同虚设 | 按顶层目录分流：`knowledge_archive/*` 回到归档目录 |
| M5 | 高 | `kb_search` | 函数内 `USE_VECTOR_SEARCH = False` 局部变量把模块级 `FLORR_VECTOR_SEARCH` 开关**彻底短路**；且 `_vector_search()` 只收 1 个参数，真放行时 `TypeError` | 改读全局开关 + `_vector_search(keyword, search_base)` 对齐签名 |
| M6 | 中 | `game_action` | dry-run 分支在**合法性校验之前**返回，`game_action("fly")` 会回"动作已记录"，把无效动作伪装成成功 | 新增 `VALID_ACTIONS`，校验与 move 坐标检查前置 |
| M7 | 中 | `_text_search` | `return` 之后 3 行不可达代码（S7 遗留）；命中结果无计数前缀 | 删除死代码，补 `共找到 N 条结果` |
| M8 | 低 | 模块 docstring | 写「MCP 工具（13 个）」，实际 15 个 | 改为 15 并注明与 README 一致 |
| M9 | 低 | `clean_cache` | 帧目录不存在时仍报"已清理"，误导排障 | 区分「已清理 / 不存在（无需清理）」 |
| M10 | 低 | `switch_tactic` | `tactic_file` 未清洗，可穿越读取知识库外 `.md`；读取无异常保护 | 走 `_safe_name()`，`OSError` 转可读错误 |

## 四、SDK 版本差异（1.x ↔ 2.x）

| 项 | mcp 1.x | mcp 2.x（本机 2.2.0） |
|---|---|---|
| 服务端类 | `mcp.server.fastmcp.FastMCP` | `mcp.server.mcpserver.MCPServer`（`mcp_server.py` 已做兼容导入） |
| 工具 schema 字段 | `inputSchema`（驼峰别名） | `input_schema`（**无** `inputSchema`，直接访问会 `AttributeError`） |
| 进程内调用未知工具 | 返回 `is_error` 结果 | **抛 `ToolError`**（S7 记录的"软失败"只对工具内部异常成立） |
| 已注册工具数 | 15 | 15（一致） |

> 影响：`requirements.txt` 原锁 `mcp<2.0.0`，与本机实际 2.2.0 矛盾。S9 已在 2.2.0 上实测 15 工具全可用，故放宽为 `mcp>=1.0.0` 并注明差异。

## 五、验收记录

- `python -m pytest tests/ -q` → **614 passed**（S8 的 505 + S9 新增 109，0 failed）
- `python tools/mcp_tools_check.py --strict` → 清单 OK / 15 工具调用 OK / 往返 OK，**退出码 0**
- 往返实证：包内成员 `['knowledge_md/root.md', 'knowledge_md/florr/boss.md', 'knowledge_archive/old.md']`；
  还原后子目录保真 `True`、归档不被复活 `True`
- `compileall` 通过；探针产生的 `knowledge_md/_s9_probe*` / `_current_tactic.md` / `kb_backups/` 已清理

## 六、遗留

- `handle_afk` 只返回流程说明文本，不做任何实质处理（无真实弹窗坐标可测）。真实验证需人工点击，属预期降级。
- `kb_import` 对**旧格式**（扁平 `knowledge_md/xxx.md`）备份保持兼容并已回归锁定；但若旧备份里两个游戏目录有同名文件，导入仍会互相覆盖（导出侧已修，历史备份无法追溯）。
- 向量检索分支仍为预留实现（`chromadb` / `sentence-transformers` 未安装，且后者会拉入 torch，磁盘紧张不装），仅验证"开关不被短路 + 签名正确 + 回退文本检索"。
