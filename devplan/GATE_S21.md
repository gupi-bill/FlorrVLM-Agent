# S21 · 测试门禁与可观测性固化

> 执行时间：2026-09-22 06:05~06:3x（F 线）
> 交付：`tests/test_check_script.py`（20 用例）、`config.runtime_mode()`、`agent_cli` `mode` 命令、README 门禁章节

## 1. 结论

此前「一条命令验证整个项目」名不副实：`tools/mcp_tools_check.py` 与 `tools/cli_smoke.py`
各自能跑，但**都没有进 `check.sh`** —— MCP 工具表漂移、CLI 命令报 traceback 都不会在门禁里暴露。
本阶段把两者接进门禁，并把运行模式做成单一真源可查询。

| 项 | 结果 |
|---|---|
| 门禁环节 | 4 → **6**（新增 MCP 工具核对、CLI 全命令冒烟） |
| 全量门禁耗时 | 3 分 07 秒（含 pytest + 31 条命令冒烟） |
| 全量门禁结果 | ✅ 通过，退出码 0 |
| 新增用例 | 20（`tests/test_check_script.py`） |
| 运行模式 | `config.runtime_mode()` 单一真源，CLI `mode` 命令 + 大盘展示 |

## 2. 门禁六个环节

| 环节 | 命令 | 失败退出码 |
|---|---|---|
| 1 语法编译 | `compileall -q .` | 1 |
| 2 启动自检 | `boot_check.py --fail-fast` | 2 |
| 3 游戏档案 | `game_profile_check.py --all` | 3 |
| 4 单元测试 | `pytest tests/ -q` | 4 |
| 5 **MCP 工具核对**（S21 新增） | `tools/mcp_tools_check.py --strict` | 5 |
| 6 **CLI 全命令冒烟**（S21 新增） | `tools/cli_smoke.py --strict --timeout 12` | 6 |

`--fast` 跳过 4/5/6，保留秒级静态与自检。退出码即环节编号，失败定位无需读日志。

实测（`bash scripts/check.sh`）：语法 OK → 自检 ERROR 0 → 档案全过 → pytest 全绿 →
MCP `总计: PASS` → CLI `合计 31 条：ok 31 / 有意义输出 30 (96%) / traceback 0`。

## 3. 运行模式可观测

问题：模式判定此前散落三处各写一套（`admin_panel._mode` 自己解析环境变量、`agent_main` 用
`_env_flag("UGF_DRY_RUN")`、感知后端又是一套），容易出现「大盘显示 mock、实际在等真机」。

现统一到 `config.runtime_mode()`，返回：

```python
{"mode": "dry-run"|"online", "dry_run": bool, "perception_backend": "mock"|"http"|"auto",
 "llm": "on"|"off", "vlm": "on"|"off", "game": "florr"}
```

- 环境变量优先级高于 `config.yaml`（与感知服务、主循环同口径）
- **dry-run + auto 时后端显示为 `mock`**（auto 在 dry-run 下必然降级，显示 auto 会误导）
- CLI：`python agent_cli.py -c mode`
- 大盘：`admin_panel._mode()` 改为调用该函数，只保留 auto 可用性探测与文案；新增 `llm` / `vlm` / `game` / `summary` 字段并进入卡片 title

## 4. 修改清单

- `scripts/check.sh`：新增环节 5/6 与退出码 5/6，`--fast` 下跳过
- `config.py`：`runtime_mode()` / `runtime_mode_text()`
- `agent_cli.py`：`_cmd_mode()` + 命令表注册 + 帮助清单 `mode`
- `admin_panel.py`：`_mode()` 改为单一真源，补充 LLM/VLM/游戏字段
- `README.md`：门禁章节改为 6 环节 + 运行模式查询示例，用例基线同步

## 5. 验收记录

```
$ bash scripts/check.sh --fast           ✅（秒级）
$ bash scripts/check.sh                  ✅ 全部门禁通过（3m07s）
$ python -m pytest tests/test_check_script.py -q    20 passed
$ python agent_cli.py -c mode
  运行模式 : dry-run（不碰键鼠、不调外部 LLM）
  感知后端 : mock
  LLM     : off
  VLM     : off
  激活游戏 : florr
```

## 6. 遗留

1. 全量门禁 3 分钟偏慢（pytest 约 90s + CLI 冒烟约 85s）。CI 可考虑拆成 `--fast` 与全量两级。
2. `cli_smoke` 的 `--timeout 12` 是本机实测的保守值；慢机器上个别命令可能超时误报，
   届时调大或加 `--only` 子集。
3. 大盘的 LLM/VLM 只显示 on/off，未显示具体模型与端点（避免泄露配置），后续可加 `--verbose`。
