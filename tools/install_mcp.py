#!/usr/bin/env python3
"""
Universal-Game-Framework · MCP 一键安装器  tools/install_mcp.py
=============================================================
本项目的定位是「装到其他 Agent 上的 MCP 能力包」，不是独立 Agent。
这个脚本负责把本服务注册进各种支持 MCP 的客户端配置里。

用法：
  python tools/install_mcp.py --list                 # 看看有哪些客户端可写、现状如何
  python tools/install_mcp.py                        # 自动挑一个已存在的客户端写入
  python tools/install_mcp.py --target workbuddy     # 指定客户端
  python tools/install_mcp.py --target custom --path /abs/to/mcp.json
  python tools/install_mcp.py --target workbuddy --dry-run   # 只打印将要写入的内容，不落盘
  python tools/install_mcp.py --target workbuddy --remove    # 卸载注册
  python tools/install_mcp.py --online                # 不设 UGF_DRY_RUN（允许真实键鼠，慎用）

返回码：0=成功；1=失败/未找到目标；2=参数错误。
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PY = os.path.join(BASE_DIR, "mcp_server.py")

# kind=json → 合并进 JSON 的某个 key；kind=toml → 只给指引（避免写坏 TOML 结构）
TARGETS = {
    "workbuddy": {
        "desc": "WorkBuddy（本机 ~/.workbuddy/mcp.json）",
        "path": os.path.expanduser("~/.workbuddy/mcp.json"),
        "kind": "json", "key": "mcpServers",
    },
    "claude-desktop": {
        "desc": "Claude Desktop（Linux 路径）",
        "path": os.path.expanduser("~/.config/Claude/claude_desktop_config.json"),
        "kind": "json", "key": "mcpServers",
    },
    "opencode": {
        "desc": "OpenCode（~/.config/opencode/opencode.json，mcp 段）",
        "path": os.path.expanduser("~/.config/opencode/opencode.json"),
        "kind": "json", "key": "mcp",
    },
    "codex": {
        "desc": "Codex CLI（~/.codex/config.toml，TOML，本脚本只给指引）",
        "path": os.path.expanduser("~/.codex/config.toml"),
        "kind": "toml", "key": None,
    },
    "vscode": {
        "desc": "VS Code / Cursor（~/.vscode/mcp.json，部分版本支持）",
        "path": os.path.expanduser("~/.vscode/mcp.json"),
        "kind": "json", "key": "servers",
    },
}


def entry(dry: bool = True) -> dict:
    """生成 ugf 这一条 MCP 注册项。"""
    env = {"PYTHONUNBUFFERED": "1"}
    env["UGF_DRY_RUN"] = "1" if dry else "0"
    return {
        "command": sys.executable,
        "args": [SERVER_PY],
        "env": env,
        "disabled": False,
    }


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"❌ 读取配置失败 {path}: {e}")


def cmd_list() -> int:
    print("可写入的 MCP 客户端目标：\n")
    for name, t in TARGETS.items():
        p = t["path"]
        exists = os.path.exists(p)
        registered = False
        if exists and t["kind"] == "json":
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                registered = "ugf" in (data.get(t["key"]) or {})
            except Exception:
                registered = False
        flag = "✅ 已注册 ugf" if registered else ("— 未注册" if exists else "— 配置文件不存在")
        print(f"  {name:<15} {flag:<18} {p}")
        print(f"                  {t['desc']}")
    print("\n用法： python tools/install_mcp.py --target <name> [--dry-run] [--remove]")
    return 0


def _resolve(name: str, custom_path: str = "") -> tuple:
    if name == "custom":
        if not custom_path:
            return None, "用 --target custom 时必须给 --path"
        return {"desc": "自定义配置", "path": os.path.expanduser(custom_path),
                "kind": "json", "key": "mcpServers"}, None
    t = TARGETS.get(name)
    if not t:
        return None, f"未知目标: {name}（可用: {', '.join(TARGETS)} 或 custom）"
    return t, None


def cmd_install(name: str, custom_path: str, dry_run: bool,
                remove: bool, dry: bool) -> int:
    t, err = _resolve(name, custom_path)
    if err:
        print(f"❌ {err}")
        return 2

    if t["kind"] == "toml":
        print("ℹ 该客户端用 TOML 配置，本脚本不会改写（避免写坏结构）。请手动加入：\n")
        print('[mcp_servers.ugf]')
        print(f'command = "{sys.executable}"')
        print(f'args = ["{SERVER_PY}"]')
        print('env = { UGF_DRY_RUN = "1" }\n')
        return 0

    path = t["path"]
    data = _load(path)
    bucket = data.setdefault(t["key"], {})

    if remove:
        if "ugf" not in bucket:
            print(f"ℹ {path} 里没有 ugf，无需卸载")
            return 0
        if dry_run:
            print(f"[dry-run] 将移除 {path} 的 ugf 注册")
            return 0
        bucket.pop("ugf", None)
        _write(path, data)
        print(f"✅ 已移除 {path} 的 ugf 注册")
        return 0

    bucket["ugf"] = entry(dry=dry)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if dry_run:
        print(f"[dry-run] 将写入 {path}：\n")
        print(text)
        return 0
    _write(path, data)
    print(f"✅ 已注册到 {path}")
    print(f"   命令: {sys.executable}")
    print(f"   参数: {SERVER_PY}")
    print(f"   dry-run: {'开（不做真实键鼠）' if dry else '关（可执行真实键鼠，慎用）'}")
    print("\n接下来：在客户端的连接器/设置页把 ugf 设为信任，重启客户端即可调用。")
    return 0


def _write(path: str, data: dict):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description="把 Universal-Game-Framework 注册为 MCP 服务")
    ap.add_argument("--list", action="store_true", help="列出可写入的客户端目标与现状")
    ap.add_argument("--target", default="", help="目标客户端名（见 --list）或 custom")
    ap.add_argument("--path", default="", help="--target custom 时的配置文件绝对路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容，不落盘")
    ap.add_argument("--remove", action="store_true", help="移除已注册的 ugf")
    ap.add_argument("--online", action="store_true",
                    help="不设 UGF_DRY_RUN=1（允许真实键鼠操作，仅在授权环境下使用）")
    args = ap.parse_args()

    if not os.path.exists(SERVER_PY):
        print(f"❌ 找不到 mcp_server.py: {SERVER_PY}")
        return 1

    if args.list:
        return cmd_list()

    name = args.target
    if not name:
        # 自动挑一个配置文件已存在的目标
        for cand, t in TARGETS.items():
            if t["kind"] == "json" and os.path.exists(t["path"]):
                name = cand
                break
        if not name:
            print("❌ 没找到任何已存在的客户端配置；请用 --list 查看，" \
                  "或 --target custom --path /绝对路径/mcp.json")
            return 1
        print(f"ℹ 自动选择目标: {name}")
    return cmd_install(name, args.path, args.dry_run, args.remove, not args.online)


if __name__ == "__main__":
    sys.exit(main())
