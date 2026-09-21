#!/usr/bin/env python3
"""
Universal-Game-Framework 一键登记新游戏档案 tools/add_game.py  (v2.0 / S10)
==========================================================================
想换游戏不用写代码：跑这个向导，填几个问题，就会：
  1) 生成 game_profiles/<name>.yaml（与 florr.yaml / space_invaders.yaml 同构）
  2) 自动把 config.yaml 的 agent.game 切到新游戏
  3) 生成后**立即按 strict 口径自检**（ERROR 与 WARN 都为 0 才算过），
     保证「生成即通过 validate」——不会出现"生成完一跑 validate 全是建议项"。

用法:
  python tools/add_game.py                     # 交互向导（回车=用默认/示例值）
  python tools/add_game.py demo_game           # 直接给名字，其余用默认，测试用
  python tools/add_game.py demo_game --no-activate   # 只生成档案，不改 config.yaml
  python tools/add_game.py --print demo_game   # 只把 YAML 打到 stdout，不落盘

S10 变更：
  - render_yaml 补齐推荐字段：server.perception_port / combat.sets /
    combat.default_set / combat.tactics / perception.mock.entities，
    新游戏登记完即可离线（mock）跑通全链路，无需再手工补端口与套装。
  - 端口自动避让：扫描 game_profiles/ 已占用的 perception_port，取 max+10。
  - 游戏名做安全化（只保留字母数字下划线与 .-），保证「文件名 == game.name」。
  - activate_game 精确改 agent: 段下的 game:，不再误伤其它同名键。
"""
import json
import os
import re
import sys

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE_DIR, "game_profiles")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

# 参考 florr.yaml 作为默认提示值（降低门槛）
REFERENCE = """如 florr: highest=[Unique,Eternal] boss=[Super] elite=[Ultra,Mythic,Legendary,Epic] normal=[Rare,Unusual,Common]"""

# 默认套装：与 combat_judge.recommended_set / mcp_server.switch_set 键位映射同名
DEFAULT_SETS = ["combat", "tank", "retreat", "chase", "team"]
# 生成 mock 实体时的初始坐标 / 速度（无 YOLO、无真机时用它跑通全链路）
MOCK_SPAWN = [
    (300, 260, 40, 0),
    (700, 260, 40, 0),
    (1100, 320, -60, 30),
    (1500, 400, -120, 60),
]
MOCK_PLAYER = {"alive": True, "hp": 100, "max_hp": 100, "x": 960, "y": 980,
               "power_score": 100}


def _ask(label: str, default: str = "") -> str:
    """读输入，空回车返回 default。非终端(管道)或 UGF_NONINTERACTIVE=1 时直接用默认值。

    自动化/CI 场景（stdin 是 tty 但无人应答）会卡死，故额外提供环境变量开关。
    """
    if os.environ.get("UGF_NONINTERACTIVE"):
        return default
    if not sys.stdin.isatty():
        return default
    try:
        v = input(f"  {label} [{default or '回车'}]> ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return v or default


def _split_csv(text: str) -> list:
    return [s.strip() for s in re.split(r"[,\s，]+", text or "") if s.strip()]


def _parse_floats(text: str) -> list:
    out = []
    for s in _split_csv(text):
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def _sanitize_name(name: str) -> str:
    """游戏名即文件名，必须与 game.name 一致 → 只保留安全字符。"""
    cleaned = re.sub(r"[^\w.-]+", "_", (name or "").strip()).strip("._-")
    return cleaned or "florr"


def _next_port(default: int = 5011) -> int:
    """扫描已登记的档案，取一个未被占用的感知端口（步长 10）。"""
    used = set()
    if os.path.isdir(PROFILE_DIR):
        for fn in os.listdir(PROFILE_DIR):
            if not fn.endswith(".yaml"):
                continue
            try:
                with open(os.path.join(PROFILE_DIR, fn), "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                port = (data.get("server") or {}).get("perception_port")
                if isinstance(port, int) and not isinstance(port, bool):
                    used.add(port)
            except Exception:
                continue
    port = default
    while port in used:
        port += 10
    return port


def _mock_entities(data: dict) -> list:
    """按已声明的稀有度档位合成 mock 实体（从高到低各取一个，保证 rarity 合法）。"""
    tiers = ["rarity_highest_boss", "rarity_boss", "rarity_elite", "rarity_normal"]
    ents = []
    for i, tier in enumerate(tiers):
        vals = data.get(tier) or []
        if not vals:
            continue
        x, y, vx, vy = MOCK_SPAWN[i % len(MOCK_SPAWN)]
        rid = str(vals[0])
        ents.append({"raw_id": rid, "rarity": rid, "x": x, "y": y, "vx": vx, "vy": vy})
    return ents


def collect(game_name: str = "") -> dict:
    print(f"\n  【新增游戏档案】 {game_name or '(交互填写)'}\n")
    name = _sanitize_name(game_name or _ask("游戏名(只允许字母数字下划线)", "florr"))
    if game_name and name != game_name:
        print(f"  ⚠ 游戏名已安全化为 '{name}'（文件名必须与 game.name 一致）")
    desc = _ask("一句话描述", f"{name} 游戏档案")
    # 稀有度金字塔（可一行内给多组：highest,boss,elite,normal）
    rar = _ask(f"稀有度金字塔(highest,boss,elite,normal) {REFERENCE}", "")
    rarity_highest, rarity_boss, rarity_elite, rarity_normal = [], [], [], []
    if rar:
        cat_split = [g for g in _split_csv(rar) if g.startswith("[")]
        if len(cat_split) >= 1:
            rarity_highest = list(cat_split[0][1:-1].split(","))
        if len(cat_split) >= 2:
            rarity_boss = list(cat_split[1][1:-1].split(","))
        if len(cat_split) >= 3:
            rarity_elite = list(cat_split[2][1:-1].split(","))
        if len(cat_split) >= 4:
            rarity_normal = list(cat_split[3][1:-1].split(","))
    if not rarity_highest:
        rarity_highest = _split_csv(_ask("highest_boss 稀有度", "Unique,Eternal"))
    if not rarity_boss:
        rarity_boss = _split_csv(_ask("boss 稀有度", "Super"))
    if not rarity_elite:
        rarity_elite = _split_csv(_ask("elite 稀有度", "Ultra,Mythic,Legendary,Epic"))
    if not rarity_normal:
        rarity_normal = _split_csv(_ask("normal 稀有度", "Rare,Unusual,Common"))
    # 威胁分，顺序: highest_boss,boss,elite,normal,player_enemy,player_ally,unknown
    th_text = _ask("威胁分(highest→unknown,7个)", "1000,400,120,15,150,0,5")
    th = _parse_floats(th_text) or [1000, 400, 120, 15, 150, 0, 5]
    while len(th) < 7:
        th.append(0)
    chase = _ask("追击最低档次(highest_boss/boss/elite/normal/player_enemy)", "elite")
    if chase not in {"highest_boss", "boss", "elite", "normal", "player_enemy"}:
        chase = "elite"
    # v2.0 推荐字段：端口 / 套装 / 战术
    port_text = _ask("感知服务端口(每款游戏一个，回车自动分配)", str(_next_port()))
    try:
        port = int(float(port_text))
    except (TypeError, ValueError):
        port = _next_port()
    if port <= 0 or port > 65535:
        port = _next_port()
    sets = _split_csv(_ask("套装清单(逗号分隔；与 combat_judge 的 recommended_set 同名)",
                           ",".join(DEFAULT_SETS))) or list(DEFAULT_SETS)
    default_set = _ask("默认套装", sets[0]) or sets[0]
    if default_set not in sets:
        default_set = sets[0]
    tactics_text = _ask("战术条目(用 | 分隔，回车用模板)", "")
    tactics = [t.strip() for t in (tactics_text or "").split("|") if t.strip()]
    if not tactics:
        tactics = [
            f"{rarity_highest[0] if rarity_highest else '最高档怪'} 出现时优先避战，"
            f"血量充足再考虑集火",
            f"面对 {rarity_elite[0] if rarity_elite else '中档怪'} 及以下可主动追击，"
            f"注意保留逃生手段",
            "血量低于 30% 立即切 retreat，不要恋战",
        ]
    return {
        "name": name,
        "description": desc,
        "rarity_highest_boss": rarity_highest,
        "rarity_boss": rarity_boss,
        "rarity_elite": rarity_elite,
        "rarity_normal": rarity_normal,
        "threat": {
            "highest_boss": th[0], "boss": th[1], "elite": th[2], "normal": th[3],
            "player_enemy": th[4], "player_ally": th[5], "unknown": th[6],
        },
        "chase_min_category": chase,
        "perception_port": port,
        "sets": sets,
        "default_set": default_set,
        "tactics": tactics,
    }


def _fmt_num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "0"
    return str(int(f)) if f.is_integer() else str(f)


def _lst(items: list) -> str:
    return "[" + ", ".join(_q(x) for x in items) + "]"


def _q(text) -> str:
    """把任意用户输入转成合法的 YAML 双引号标量（含冒号/引号/中文都不会炸）。"""
    return json.dumps(str(text), ensure_ascii=False)


def render_yaml(data: dict) -> str:
    """渲染完整档案（含推荐字段），保证生成即通过 game_profile_check --strict。"""
    li = [f"    {k}: {_fmt_num(v)}" for k, v in data["threat"].items()]
    sets_lines = "\n".join(f"    - {s}" for s in data["sets"])
    tactic_lines = "\n".join(f"    - {_q(t)}" for t in data["tactics"])
    ent_lines = "\n".join(
        "      - {raw_id: %s, rarity: %s, x: %s, y: %s, vx: %s, vy: %s}" % (
            e["raw_id"], e["rarity"], e["x"], e["y"], e["vx"], e["vy"])
        for e in _mock_entities(data)
    )
    return f"""# Universal-Game-Framework 游戏档案 {data['name']}.yaml
# ====================================================
# 一款游戏一份档案。核心模块(predictor/combat_judge/agent_main)只认这些键的语义，
# 不认具体游戏名。切换游戏 = 设 AGENT_GAME / config.yaml 的 agent.game 指向本档案，核心零改动。
#
# 优先级：DEFAULT 兜底 < config.yaml(通用项) < 本档案(游戏专属项) < tuned_overrides.yaml。
# 由 tools/add_game.py v2.0 生成；改动后请用 `python game_profile_check.py --all` 复检。

# 游戏元信息（name 必须与文件名一致）
game:
  name: {data['name']}
  description: {_q(data['description'])}

# 感知端口：每款游戏一个端口，多游戏并行时不会都挤在 5001
server:
  perception_port: {data['perception_port']}

# 实体分类金字塔（highest_boss ≥ boss ≥ elite ≥ normal，威胁分必须单调不增）
predictor:
  rarity_highest_boss: {_lst(data['rarity_highest_boss'])}
  rarity_boss: {_lst(data['rarity_boss'])}
  rarity_elite: {_lst(data['rarity_elite'])}
  rarity_normal: {_lst(data['rarity_normal'])}
  # 分类 -> 威胁分数（战斗评估判断打/跑/追）
  threat:
{chr(10).join(li)}

combat:
  chase_min_category: {data['chase_min_category']}      # 追击套最低怪物档次
  default_set: {data['default_set']}            # 必须出现在下面的 sets 里
  # 套装清单：与 combat_judge.recommended_set、mcp_server.switch_set 键位映射同名
  sets:
{sets_lines}
  # 战术模板（会写进知识库，供决策时检索引用）
  tactics:
{tactic_lines}

# 离线 / mock 感知数据：无 YOLO、无真机时用于跑通全链路与演示
# rarity 必须落在上面已声明的档位里，否则 game_profile_check 会报错
perception:
  mock:
    drift: true
    afk_popup: false
    player:
      alive: {str(MOCK_PLAYER['alive']).lower()}
      hp: {MOCK_PLAYER['hp']}
      max_hp: {MOCK_PLAYER['max_hp']}
      x: {MOCK_PLAYER['x']}
      y: {MOCK_PLAYER['y']}
      power_score: {MOCK_PLAYER['power_score']}
    entities:
{ent_lines}
"""


def activate_game(name: str) -> str:
    """把 config.yaml 的 agent.game 切到 name（精确命中 agent: 段下的 game:）。"""
    if not os.path.exists(CONFIG_PATH):
        return "config.yaml 不存在，无法切换"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        text = f.read()

    def _sub(block: str) -> tuple:
        return re.subn(r"(?m)^(\s*game:\s*)([\w.-]+)", lambda m: f"{m.group(1)}{name}",
                       block, count=1)

    new = text
    agent_block = re.search(r"(?ms)^agent:[ \t]*\n(.*?)(?=^\S|\Z)", text)
    if agent_block and re.search(r"(?m)^\s*game:\s*[\w.-]+", agent_block.group(1)):
        replaced, _n = _sub(agent_block.group(1))
        start, end = agent_block.start(1), agent_block.end(1)
        new = text[:start] + replaced + text[end:]
    else:
        new, _n = _sub(text)
    if new == text:
        return "未找到可切换的 game: 行（保持当前）"
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new)
    return f"已切换 config.yaml 的 agent.game → {name}"


def selfcheck(name: str) -> tuple:
    """按 strict 口径自检：ERROR 与 WARN 均为 0 才算通过。返回 (ok, problems)。"""
    sys.path.insert(0, BASE_DIR)
    from game_profile_check import check_detail
    detail = check_detail(name)
    problems = list(detail["errors"]) + [f"[建议] {w}" for w in detail["warnings"]]
    return detail["ok"] and not detail["warnings"], problems


def main():
    args = [a for a in sys.argv[1:] if a != "--no-activate"]
    print_only = "--print" in args
    args = [a for a in args if a != "--print"]
    no_activate = "--no-activate" in sys.argv[1:]
    name_arg = args[0] if args else ""
    data = collect(name_arg)
    text = render_yaml(data)
    if print_only:
        print(text)
        return 0
    os.makedirs(PROFILE_DIR, exist_ok=True)
    out = os.path.join(PROFILE_DIR, f"{data['name']}.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n  ✅ 已生成: {out}")
    # S10：生成后按 strict 自检，保证「生成即通过 validate」（建议项也算问题）
    ok, problems = selfcheck(data["name"])
    if ok:
        print(f"  ✅ 严格自检通过: {data['name']} 无错误、无建议项")
    else:
        print("  ⚠ 生成成功但自检发现问题:")
        for p in problems:
            print(f"     - {p}")
    if no_activate:
        print("  （--no-activate：未改动 config.yaml）")
    else:
        print(f"  ✅ {activate_game(data['name'])}")
    print("      之后启动即自动读取该档案，核心零改动。\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
