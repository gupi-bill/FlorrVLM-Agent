# S8 · CLI 全命令冒烟报告

> 执行时间：2026-09-21 06:00~06:30（A 线）
> 环境：无头 Linux / 无 X server / 无 `.env`（无 LLM·VLM·YOLO 密钥）/ 隔离 venv `ugf`
> 冒烟工具：`tools/cli_smoke.py`（子进程真实调用，可复用为 S13 门禁）

---

## 一、结论

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 命令总数 | 28 | 31 |
| **traceback** | **1** | **0** ✅ |
| 因交互阻塞而超时的命令 | 1（`brief`） | 0 ✅ |
| 因卡死而超时的命令 | 3（`auto` / `play 2` / `--auto`） | 0 ✅ |
| 落到「未知命令」的已声明命令 | 3（`help` / `play` / `auto`） | 0 ✅ |
| 有意义输出占比 | 92%（且含 3 条假阳性「未知命令」） | **96%**（余下 1 条为故意的反向用例）✅ |

PLAN 验收标准「命令矩阵中无 traceback；至少 80% 命令在离线模式下给出有意义的输出」——**达成**。

---

## 二、冒烟方法

`tools/cli_smoke.py` 以**子进程**方式逐条执行 `agent_cli.py -c "<cmd>"`（不走 monkeypatch，
因此能抓到 import 期与运行期的真实崩溃），并为每条命令打超时。

关键设计：

1. **`stdin=subprocess.DEVNULL`** —— 这是本轮最重要的发现（见 C2）。父进程若把 tty 透传给
   子进程，CLI 任何 `input()` 都会永久阻塞；冒烟时必须显式隔离 stdin。
2. 环境变量统一：`UGF_DRY_RUN=1`（不碰真实键鼠 / 不调外部 LLM）、
   `UGF_PERCEPTION_BACKEND=mock`（感知走合成数据）、`PYTHONIOENCODING=utf-8`。
3. 判定「不可读错误」= 输出中出现 `Traceback (most recent call last)`。
4. `--json` 输出机器可读结果，`--strict` 在有 traceback 时退出码非 0 —— **S13 可直接接成门禁**。

```bash
python tools/cli_smoke.py            # 表格
python tools/cli_smoke.py --strict   # 门禁模式
python tools/cli_smoke.py --json     # 机器可读
python tools/cli_smoke.py --only kb_list kb_search
```

---

## 三、发现并修复的缺陷（9 项）

### C1 · `_append_log` 未定义 —— 阻断（真实崩溃）
`kb_list` / `kb_search` 在两个分支里调用 `_append_log()`，而该函数在 `agent_cli.py` 中
**根本不存在**。`-c "kb_list florr"`（游戏目录不存在时）直接抛 `NameError` 并吐 traceback。
→ 补齐实现：写入 `run_logs/agent_<YYYYMMDD>.log`，任何异常一律静默吞掉（日志失败绝不能影响主命令）。

### C2 · `-c brief` 永久阻塞 —— 阻断
`_collect_brief()` 无条件 `input()`。原先只靠 `EOFError` 兜底，**但 stdin 若是一个真实 tty，
`input()` 会一直等**——实测 `-c brief` 20s 超时、`-c "play 2"` 卡死 200s 以上。
→ 新增 `_ONE_SHOT` 全局开关：`-c` 与 `--auto` 属一次性调用，**无论 stdin 是什么都不提问**；
非交互时答案改从 `UGF_BRIEF_GAME_TYPE` / `UGF_BRIEF_FOCUS` / `UGF_BRIEF_WATCH_OUT` 读，没有则留空。

### C3 · `-c` 模式缺 `help` / `play` / `auto` —— 高
这三个命令在 `HELP_LINES` 里写着，但 `main()` 的命令表里没有，脚本化编排主循环无从下手。
→ 补齐；同时把命令表从 `main()` 的局部变量抽成 `_command_registry(arg)`，
使「帮助清单 ⊇ 命令表」这一致性可由单测锁定（此前只能靠人工）。

### C4 · `ui_pyqt.py` 的 `--auto search <game> <query>` 完全不匹配 —— 高（PLAN 点名项）
`ui_pyqt.py:139` 一直以 `["python3", "agent_cli.py", "--auto", "search", game, "basic guide"]`
拉起检索，而 CLI 既没有 `--auto` 参数、也没有 `search` 子命令，该调用 100% 落到「未知命令」。
→ 新增 `--auto` argparse 参数（`--auto <游戏>` 走全链路，`--auto search <游戏> <查询词>` 走
detect → research → ensure），并新增等价的 `-c "auto_search <游戏> <查询词>"`。

### C5 · `unload` 跨进程不恢复技能 —— 中
一次性调用下进程是新的、内存无技能，`-c "unload report"` 恒返回「未加载」，显式卸载永远不生效
（`run_skill` 早已有恢复逻辑，`unload` 漏了）。→ 卸载前先按档案恢复。

### C6 · `kb_*` 无法传第二参数（游戏名）—— 中
`-c "kb_search boss florr"` 里 `arg` 整体被当成关键词，搜的是 `"boss florr"`。
→ 新增 `_arg2()`：`("boss florr")` → `("boss", "florr")`，`kb_search` / `kb_write` / `kb_append` / `kb_list` 均支持。

### C7 · 交互模式缺 `kb_*` 四个分支 —— 中
`interactive()` 的 elif 链里根本没有 `kb_list` / `kb_search` / `kb_write` / `kb_append`，
在交互式会话中输入这四个命令一律「未知命令」。→ 补齐分支。

### C8 · `HELP_LINES` 漏登记 4 个 kb 命令 —— 低
帮助与 `describe_capabilities()` 都没提知识库能力。→ 补齐，并在能力清单里增列知识库段。

### C9 · `_run_auto` 的 return 之后有 28 行完全重复的死代码 —— 低
函数体被复制粘贴了一遍，`return` 之后的整段永不执行。→ 删除，并由 AST 断言锁定。

### 附带清理
- 删除重复的 `import config`；改用模块级 `import datetime` 替代函数内 `__import__("datetime")`。
- `research` 在离线时追加统一降级提示 `_offline_note()`。
- 未知命令退出码从 0 改为 1，并附可用命令列表（原先「未知命令」也算成功退出，脚本无法判断）。

---

## 四、冒烟矩阵（修复后，31 条）

| # | 命令 | rc | 结果 | traceback | 说明 |
|---|---|---|---|---|---|
| 1 | `help` | 0 | OK | 否 | 修复前为「未知命令」 |
| 2 | `capabilities` | 0 | OK | 否 | 能力清单（已补知识库段） |
| 3 | `state` | 0 | OK | 否 | JSON 会话档案 |
| 4 | `detect florr` | 0 | OK | 否 | 写档并回显 |
| 5 | `brief` | 0 | OK | 否 | **修复前 TIMEOUT** |
| 6 | `research` | 0 | OK | 否 | 离线降级：未连接外部 MCP |
| 7 | `ensure` | 0 | OK | 否 | 感知/MCP/brief 三项检查 |
| 8 | `validate florr` | 0 | OK | 否 | ✅ 档案完整 |
| 9 | `validate space_invaders` | 0 | OK | 否 | ✅ 档案完整 |
| 10 | `kb_list` | 0 | OK | 否 | 列出根目录 21 个文档 |
| 11 | `kb_list florr` | 0 | OK | 否 | **修复前 NameError** |
| 12 | `kb_write smoke_s8.md` | 0 | OK | 否 | 模板写入 |
| 13 | `kb_append smoke_s8.md` | 0 | OK | 否 | 追加/新建 |
| 14 | `kb_search boss` | 0 | OK | 否 | 全文检索 2 条命中 |
| 15 | `kb_search boss florr` | 0 | OK | 否 | 修复后正确按游戏目录过滤 |
| 16 | `stats` | 0 | OK | 否 | 多局战绩 |
| 17 | `report` | 0 | OK | 否 | 含日志尾部 |
| 18 | `notify` | 0 | OK | 否 | 落本地报告，无 Webhook |
| 19 | `session` | 0 | OK | 否 | 会话记忆 |
| 20 | `resume` | 0 | OK | 否 | 无待续玩进度 |
| 21 | `skills` | 0 | OK | 否 | 技能清单 |
| 22 | `load report` | 0 | OK | 否 | 持久化到档案 |
| 23 | `run_skill report` | 0 | OK | 否 | 跨进程恢复并输出真实进度 |
| 24 | `unload report` | 0 | OK | 否 | **修复前恒「未加载」** |
| 25 | `package portable` | 0 | OK | 否 | 148K 便携包（已清理） |
| 26 | `kb_export` | 0 | OK | 否 | 知识库 tar.gz（已清理） |
| 27 | `auto florr` | 0 | OK | 否 | **修复前 TIMEOUT** |
| 28 | `play 2` | 0 | OK | 否 | **修复前卡死 >200s**；现 14s 跑完 2 轮 |
| 29 | `--auto florr` | 0 | OK | 否 | **修复前 TIMEOUT** |
| 30 | `--auto search florr basic guide` | 0 | OK | 否 | **修复前：参数不存在** |
| 31 | `bogus_cmd_xyz` | 1 | OK（预期失败） | 否 | 反向用例：可读提示 + 退出码 1 |

`play 2` 实测输出（dry-run，2 轮 14 秒）：

```
[06:19:05] 模式: DRY-RUN —— 无真实键鼠 / 无外部 LLM / 感知走进程内 mock
[06:19:11] [MCP] 已连接，可用工具: ['kb_list', ... 'switch_tactic']   # 15 个
[06:19:12] [回合 1] HP=100.0 敌人=5 队友=1 决策=retreat 套装=retreat 心态=conservative → defend
[06:19:12] [回合 2] HP=100.0 敌人=5 队友=1 决策=retreat 套装=retreat 心态=conservative → defend
[06:19:13] [汇总] 回合=2 | 死亡=0 | 跳过帧=0 | 换套=1 | 动作=defendx2
[OK] 游戏主循环已结束
```

---

## 五、回归测试

`tests/test_agent_cli.py`（**48 用例**），逐条锁定上述 9 项缺陷：

- `_append_log` 存在性 / 落盘 / 异常静默（3）
- `kb_list` 游戏目录缺失、根目录缺失均不崩溃（2）—— **C1 主回归**
- `_ONE_SHOT` 下 `_is_interactive()` 恒 False、`_collect_brief` 返回 3 键、读环境变量、`_cmd_brief` 归档（4）—— **C2**
- `_arg2` 拆分 5 组（5）
- `kb_search/write/append` 双参数归目录、单参数归根目录、`.md` 后缀补全（6）—— **C6**
- 命令注册表一致性：HELP_LINES 中每个命令都有 handler；4 个 kb 命令既在帮助里也在注册表里；
  `play`/`auto`/`help` 在 `-c` 表中（3）—— **C3 / C8**
- 交互分发链含 kb_* 分支（源码断言）（1）—— **C7**
- `_run_auto` 末尾为 return（AST 断言，无死代码）（1）—— **C9**
- `unload` 跨进程恢复、未知技能可读返回（2）—— **C5**
- `--auto` / `--auto search` / `auto_search` 三种调用形状（3）—— **C4**
- 未知命令 `SystemExit(1)`、`help` 输出表、`state` 返回 JSON（3）
- 12 个基础命令离线可读性 + `detect` 大小写归一（2）

全量：`python -m pytest tests/ -q` → **505 passed**（S7 的 457 + 本轮 48）。

---

## 六、遗留

1. **`play` 的 dry-run 依赖 `_fallback_decide` 的规则分支**，`move` 类动作（安全区钳制 + 抖动）
   在冒烟的 2 轮里未被触发（`decision=retreat → defend`）。与 S7 遗留同源，建议 S13 前补规则化 move 策略。
2. **`package portable` / `kb_export` 会往 `dist/` 与 `kb_backups/` 落真实产物**（本次 148K / 16K，
   已被 `.gitignore` 覆盖，已手工清理）。长跑累积问题移交 **S12** 运维脚本统一处理。
3. **`research` 的真实联网检索仍未实测** —— 无外部 MCP 配置、无网络。本轮只验证到
   「未连接外部 MCP」这一降级分支可读，不崩溃。
4. **`ui_pyqt.py` 仍在用 `python3` 而非隔离 venv 解释器**调用 CLI。本次只对齐了参数形状（C4），
   解释器路径问题移交 **S11**（UI 收敛与统一启动器）。
5. `reset_brief` 的 lambda 用了海象+元组+`and` 的写法，可读性差但行为正确；未重构以避免扩大改动面，
   移交 **S13**。
