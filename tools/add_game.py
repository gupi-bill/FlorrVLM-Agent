#!/usr/bin/env python3
"""
FlorrVLM-Agent 一键登记新游戏档案 tools/add_game.py  (v1.3)
===========================================================
想换游戏不用写代码：跑这个向导，填几个问题，就会：
  1) 生成 game_profiles/<name>.yaml（和 florr.yaml 同构）
  2) 自动把 config.yaml 的 agent.game 切到新游戏

用法:
  python tools/add_game.py             # 交互向导（回车=用默认/示例值）
  python tools/add_game.py demo_game   # 直接给名字，其余用默认，测试用
"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(BASE_DIR, "game_profiles")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

# 参考 florr.yaml 作为默认提示值（降低门槛）
REFERENCE = """如 florr: highest=[Unique,Eternal] boss=[Super] elite=[Ultra,Mythic,Legendary,Epic] normal=[Rare,Unusual,Common]"""


def _ask(label: str, default: str = "", echoes: bool = True) -> str:
    """读输入，空回车返回 default。非终端(管道)时直接用 default。"""
    if not sys.stdin.isatty():
        return default
    try:
        v = input(f"  {label} [{default or '回车'}]> ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return v or default


def _split_csv(text: str) -> list:
    return [s.strip() for s in re.split(r"[,\s，]+", text) if s.strip()]


def _parse_floats(text: str) -> list:
    return [float(s) for s in _split_csv(text)]


def collect(game_name: str = "") -> dict:
    print(f"\n  【新增游戏档案】 {game_name or '(交互填写)'}\n")
    name = game_name or _ask("游戏名(只允许字母数字下划线)", "florr")
    if not _split_csv(name):
        name = "florr"
    desc = _ask("一句话描述", "我的新游戏")
    # 稀有度金字塔（可一行内给多组：highest,boss,elite,normal）
    rar = _ask("稀有度金字塔(highest,boss,elite,normal)", "", echoes=False)
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
    chase = _ask("追击最低档次", "elite")
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
    }


def _fmt_num(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)


def render_yaml(data: dict) -> str:
    def _lst(name: str) -> str:
        items = ", ".join(f'"{x}"' for x in data[name]) or '[]'
        return f"  {name}: [{items}]"
    li = [f"    {k}: {_fmt_num(v)}" for k, v in data["threat"].items()]
    return (
        "# 游戏档案：%s（v1.3 向导生成，可用 config.yaml 的 agent.game 切换）\n"
        "game:\n"
        "  name: %s\n"
        "  description: %s\n"
        "\n"
        "predictor:\n"
        "%s\n%s\n%s\n%s\n"
        "  threat:\n%s\n"
        "\n"
        "combat:\n"
        "  chase_min_category: %s\n"
    ) % (
        data["name"], data["name"], data["description"],
        _lst("rarity_highest_boss"), _lst("rarity_boss"),
        _lst("rarity_elite"), _lst("rarity_normal"),
        "\n".join(li), data["chase_min_category"],
    )


def activate_game(name: str) -> str:
    """把 config.yaml 的 agent.game 切到 name。"""
    if not os.path.exists(CONFIG_PATH):
        return "config.yaml 不存在，无法切换"
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r"(?m)^(\s*game:\s*)([\w.-]+)",
                 lambda m: f"{m.group(1)}{name}", text, count=1)
    if new == text:
        return f"未找到可切换的 game: 行（保持当前）"
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new)
    return f"已切换 config.yaml 的 agent.game → {name}"


def main():
    name_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    data = collect(name_arg)
    os.makedirs(PROFILE_DIR, exist_ok=True)
    out = os.path.join(PROFILE_DIR, f"{data['name']}.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_yaml(data))
    print(f"\n  ✅ 已生成: {out}")
    print(f"  ✅ {activate_game(data['name'])}")
    print("      之后启动即自动读取该档案，核心零改动。\n")


if __name__ == "__main__":
    main()