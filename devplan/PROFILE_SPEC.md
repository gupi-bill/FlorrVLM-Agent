# 游戏档案规范 PROFILE_SPEC（S10 固化 · S16 扩为「模板 + 字段契约」）

> 一句话：**一款游戏一份 YAML，切游戏零改核心。** 本文件是 `game_profiles/*.yaml` 的字段契约，
> 由 `game_profile_check.py`（语义校验器）、`tools/add_game.py`（生成器）、
> `game_profiles/_template.yaml`（**唯一结构来源与数值默认来源**）、
> `tests/test_game_profiles.py`（38 用例）+ `tests/test_add_game.py`（26 用例）共同锁定。
> 改任一处都必须跑 `bash scripts/check.sh`。

## 0. S16 新增：参考模板 `_template.yaml`

`game_profiles/_template.yaml` 是「接入新游戏」的**标准答案**——全字段、全注释、标注了每个字段的
类型 / 取值域 / 安全上下限 / 缺失时的兜底行为。`tools/add_game.py` **不再用硬编码 f-string 拼档案**，
而是：

1. `load_template()` 读模板原文 → 结构与注释来自模板；
2. `template_defaults()` 解析模板字面值 → 威胁分 / 端口 / `chase_min_category` / 玩家状态的默认来自模板；
3. `render_from_template()` 填充槽位 → **渲染后若残留任何 `__UGF_*__` 槽位即抛 `ValueError` 硬失败**。

设计理由：模板新增槽位而生成器没跟上时，产出的档案「看起来合法、实则是坏档案」，
必须硬失败而不是静默通过。该行为由 `tests/test_add_game.py::test_render_fails_loudly_on_unknown_slot` 锁定。

| 槽位 | 含义 | 是否可空 |
|---|---|---|
| `__UGF_NAME__` / `__UGF_DESC__` | 游戏名（=文件名）与描述 | 必填 |
| `__UGF_RARITY_{HIGHEST_BOSS,BOSS,ELITE,NORMAL}__` | 四档稀有度列表 | 必填 |
| `__UGF_DEFAULT_SET__` | 默认套装（同时写入 `player.petal_set`） | 必填 |
| `__UGF_SETS__` / `__UGF_TACTICS__` / `__UGF_ENTITIES__` | 套装 / 战术 / mock 实体列表 | 必填 |
| `__UGF_SET_MAP__:` | 决策语义→套装映射；**为空时整段不出现** | 可空 |

> 模板以 `_` 开头，`game_profile_check` 与 `add_game._next_port()` 都会跳过它（模板不能占用端口）。

## 1. 加载优先级

```
config.py 内置 DEFAULT  <  config.yaml（通用项）  <  game_profiles/<agent.game>.yaml（游戏专属项）  <  tuned_overrides.yaml（自动调参）
```

切换游戏 = 改 `config.yaml` 的 `agent.game`（或环境变量 `AGENT_GAME`），核心模块
`predictor / combat_judge / agent_main / mcp_server` 全部只认**键的语义**，不认游戏名。
实证见 `tests/test_game_profiles.py::test_switch_game_changes_core_values`。

## 2. 顶层键（其余一律报错：未知顶层键）

| 顶层键 | 必填 | 说明 |
|---|---|---|
| `game` | ✅ | 元信息：`name`（**必须等于文件名**）、`description` |
| `predictor` | ✅ | 稀有度分档 + 威胁分金字塔 |
| `combat` | ✅ | 追击档位、套装清单、默认套装、战术模板 |
| `server` | 建议 | `perception_port`——每款游戏一个端口，避免多开挤在 5001 |
| `perception` | 可选 | `mock.*`——无 YOLO / 无真机时的离线场景数据 |
| `agent` / `mcp` / `paths` | 可选 | 预留，按需覆盖通用项 |

## 3. 字段细则

### `predictor`
- 四档稀有度列表，均为**非空字符串列表**：
  `rarity_highest_boss` / `rarity_boss` / `rarity_elite` / `rarity_normal`
- 威胁金字塔 `threat`（7 个键必须齐全、必须为数字、≥0）：
  `highest_boss ≥ boss ≥ elite ≥ normal`，另有 `player_enemy` / `player_ally` / `unknown`
- 语义约束：**同一个稀有度串不能出现在两个档位**（否则分类结果不确定）

### `combat`
- `chase_min_category`：`highest_boss | boss | elite | normal | player_enemy`
- `sets`：非空字符串列表。**名字必须与 `combat_judge.recommended_set` 一致**
  （`combat / tank / retreat / chase / team`），否则 `switch_set` 会落到「未知套装」
- `default_set`：必须 ∈ `sets`
- `set_map`（v2.0 S15）：**决策语义 → 本游戏套装名**的映射，键为
  `combat / tank / retreat / chase / team`（`combat_judge.recommended_set` 的输出），
  值必须 ∈ `sets`。florr 因套装名恰与决策语义同名而无需声明；**任何使用自定义套装名的
  游戏都必须声明**，否则决策层给出的套装在 `switch_set` 环节会落到「未知套装」。
- `tactics`：字符串列表，会写进知识库供决策检索引用

### `server`
- `perception_port`：florr=5001，space_invaders=5011，新游戏由 `add_game` 自动分配（步长 10）

### `perception.mock`
- `player` / `entities[]`（`raw_id`、`rarity`、`x`、`y`、`vx`、`vy`）/ `drift` / `afk_popup`
- `entities[].rarity` 必须属于已声明档位，否则校验不通过（离线跑不通的档案 = 坏档案）

## 4. 校验等级

| 级别 | 触发 | 处理 |
|---|---|---|
| **ERROR**（退出码 1） | 必填缺失/类型错、稀有度跨档重复、威胁金字塔倒置、负威胁分、`game.name`≠文件名、未知顶层键、`sets` 非法、`default_set` 越界、mock 稀有度未声明 | 阻断 |
| **WARN**（建议） | 缺 `game.description` / `server.perception_port` / `combat.sets` / `combat.tactics`；套装名与决策语义完全不匹配且缺 `combat.set_map` | `--strict` 时升为阻断 |

命令：

```bash
python game_profile_check.py                 # 当前激活游戏
python game_profile_check.py <name>          # 指定档案
python game_profile_check.py --all           # 全部
python game_profile_check.py --all --strict  # CI 门禁口径（S13 接入）
python agent_cli.py -c "validate florr --strict"
```

## 5. 新增一款游戏（零手写）

```bash
python tools/add_game.py my_game             # 交互向导（回车用默认）
UGF_NONINTERACTIVE=1 python tools/add_game.py my_game   # 无人值守
python tools/add_game.py my_game --no-activate          # 只生成档案，不动 config.yaml
python tools/add_game.py my_game --print                # 只打印 YAML，不落盘
```

生成器 v2.0 保证「**生成即通过 validate**」：渲染后以 strict 口径自检
（ERROR 与 WARN 均为 0），非 0 时进程退出码 1。同时：
- 端口自动避让已占用端口（`_next_port()`）
- 游戏名安全化，保证文件名 == `game.name`
- 用户输入（描述/战术）经 JSON 双引号转义，冒号与引号不会写坏 YAML
- `activate_game()` 只改 `agent:` 段下的 `game:`，不误伤其它同名键

## 6. 现状（2026-09-22 S15 收尾）

| 档案 | 状态 | 端口 | 套装 | set_map |
|---|---|---|---|---|
| `florr.yaml` | ✅ strict 通过 | 5001 | combat / tank / retreat / chase / team | 无需（与决策语义同名） |
| `space_invaders.yaml` | ✅ strict 通过 | 5011 | shoot / dodge / focus_mothership | ✅ 已声明 |

**游戏切换的唯一来源是 `config.active_game()`**：
`AGENT_GAME` / `UGF_GAME` 环境变量 > `config.yaml` 的 `agent.game` > `florr`。
此前 `_reload()` 不读环境变量，导致「设 AGENT_GAME 切游戏」实际无效（S15 实测，已修复）。
`agent_main` 起 MCP 子进程时会把父进程已解析的激活游戏显式写入子进程环境，
保证父子口径一致。

**离线场景属于档案**：`perception.mock` 由各档案自带（config.yaml 已不再维护 mock 段）。
切换游戏时实体/队友/玩家状态随档案整体替换，不会残留上一款游戏的数据。

## 6.1 常见错误与症状（S16 补齐：错误 → 现象 → 修法）

| 错误写法 | 现象 | 修法 |
|---|---|---|
| `game.name` ≠ 文件名 | 校验 ERROR；`config.active_game()` 切过去读到空档案 | 改名使二者一致（`add_game` 已做安全化） |
| 同一稀有度串写进两个档位 | 分类结果不确定，威胁分随机 | 每档互斥，见 §3 |
| 威胁金字塔倒置（`boss` > `highest_boss`） | 校验 ERROR | 保证 `highest_boss ≥ boss ≥ elite ≥ normal` |
| 自定义套装名但漏 `set_map` | 校验仅 WARN，运行时 `switch_set` 落「未知套装」 | 声明 `combat.set_map`，值必须 ∈ `sets` |
| `set_map` 缩进写成 `sets:` 的子项 | **YAML 解析失败**（块映射混进列表） | `set_map` 必须与 `sets` 同级（缩进 2） |
| `perception.mock` 里 `teammates` 不声明 | 单机游戏继承到上一款游戏的队友（S15 实测串味） | 显式写 `teammates: []` |
| mock 实体 `rarity` 不在已声明档位 | 校验 ERROR，离线跑不通 | 补齐档位或改 rarity |
| 模板新增槽位但未改生成器 | 生成「合法但坏」的档案 | 渲染器按槽位残留硬失败（见 §0） |

## 7. 遗留

- 决策层输出的抽象套装名在日志展示里未翻译成游戏内名字
  （`switch_set` 已翻译，仅展示文案）—— **S16 已给出可复用路径**：`combat.set_map` 是决策语义
  →游戏内套装的唯一映射，展示层直接查该表即可，待 S20/S21 接入日志与大盘。
- `chase` / `team` 两档语义在单人街机类游戏下的映射是否贴合，需实机验证。
- `knowledge_md/` 根目录下的 florr 历史文件未做归档迁移（数据问题，非契约问题）。
- 模板目前只覆盖「必填 + 常用」字段；`agent` / `mcp` / `paths` 三个可选顶层键仅有文字说明，
  未进模板骨架（需要时手工补）。
