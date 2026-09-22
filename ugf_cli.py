#!/usr/bin/env python3
"""
Universal-Game-Framework · 命令行入口  ugf_cli.py
================================================
装包之后提供三条命令：

    ugf-mcp        # 起 MCP 服务（stdio 默认，或 --transport streamable-http）
    ugf-install    # 把本服务装进某个支持 MCP 的客户端
    ugf-check      # 体检：依赖 + 真实握手，装不上时先看它

三条命令都由本文件转发到具体实现，保持单一入口、便于打包。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def mcp_main() -> int:
    """起 MCP 服务。等价于 `python mcp_server.py`。"""
    import mcp_server
    return mcp_server.console_main()


def install_main() -> int:
    """把服务装进客户端。等价于 `python tools/install_mcp.py`。"""
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    import install_mcp
    return install_mcp.main()


def check_main() -> int:
    """体检。等价于 `python tools/install_mcp.py --check`。"""
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    import install_mcp
    return install_mcp.cmd_check()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "mcp"
    table = {"mcp": mcp_main, "install": install_main, "check": check_main}
    if cmd not in table:
        print("用法: ugf_cli.py [mcp|install|check]")
        sys.exit(2)
    # 把子命令剥掉，剩下的参数交给具体实现去解析
    sys.argv = [f"ugf-{cmd}"] + sys.argv[2:]
    sys.exit(table[cmd]())
