# 游戏档案规范 PROFILE_SPEC（S10 固化）

> 一句话：**一款游戏一份 YAML，切游戏零改核心。** 本文件是 `game_profiles/*.yaml` 的字段契约，
> 由 `game_profile_check.py`（语义校验器）、`tools/add_game.py`（生成器）、
> `tests/test_game_profiles.py`（38 用例）三方共同锁定。改任一处都必须跑 `pytest tests/ -q`。

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
| **WARN**（建议） | 缺 `game.description` / `server.perception_port` / `combat.sets` / `combat.tactics` | `--strict` 时升为阻断 |

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

## 6. 现状（2026-09-21 S10 收尾）

| 档案 | 状态 | 端口 | 套装 |
|---|---|---|---|
| `florr.yaml` | ✅ strict 通过 | 5001 | combat / tank / retreat / chase / team |
| `space_invaders.yaml` | ✅ strict 通过 | 5011 | shoot / dodge / focus_mothership |

## 7. 遗留

- space_invaders 的套装名（`shoot`/`dodge`）与 `mcp_server.SET_TO_KEY` 的数字键映射
  （combat/tank/retreat/chase/team）不同名 → 换套会落到「未知套装」。
  `switch_set` 的键位映射目前是 florr 专属，**多游戏换套应改为按档案的 `sets` 顺序映射按键**，
  移交 S15（第二款游戏端到端跑通）。
- `config.yaml` 的 `perception.mock` 仍是 florr 场景；florr 档案自身未声明 `perception.mock`，
  离线数据不从档案走。迁移到档案内（真正的"一份档案一份离线场景"）移交 S15。
