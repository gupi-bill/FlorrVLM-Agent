#!/usr/bin/env python3
"""
FlorrVLM-Agent 外部 MCP 连接器 mcp_connector.py
================================================
v0.7 —— 让 Agent 不只是"对外暴露工具"，还能"主动去连别人的 MCP"。

功能：
- 读取 mcp_connectors.yaml，逐个 stdio_client 连接外部 MCP Server
- 连接成功 → 汇总外部工具清单（供 LLM/CLI 决策使用）
- 提供 call()：按 "server.tool" 名称调用外部工具
- 单个连接失败只跳过该条并提示，不影响整体启动

用法（配合 agent_cli 的 capabilities / research）：
  from mcp_connector import ExternalConnector
  ec = await ExternalConnector.create()      # 连接所有外部 MCP
  ec.summary()                                # 已连接的外部工具清单
  await ec.call("search.some_tool", {...})   # 调用外部工具
"""
import asyncio
import os

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONNECTORS_FILE = os.path.join(BASE_DIR, "mcp_connectors.yaml")

_FALLBACK_CONNECTORS = {
    "connectors": []
}


def _load_connectors() -> list:
    """读取外部 MCP 连接配置；文件缺失/损坏则返回空列表。"""
    try:
        import yaml
        with open(CONNECTORS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = _FALLBACK_CONNECTORS
    return data.get("connectors", [])


class ExternalConnector:
    """管理到外部 MCP Server 的多个连接。"""

    def __init__(self):
        self._servers = []   # [(name, read, write, session, tools_dict), ...]
        self._connected = 0
        self._failed = []

    @classmethod
    async def create(cls) -> "ExternalConnector":
        """创建并连接全部外部 MCP。"""
        self = cls()
        await self.connect_all()
        return self

    async def connect_all(self):
        """逐个连接配置里的外部 MCP。"""
        cfg_items = _load_connectors()
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            self._failed.append("mcp 库未安装(需 pip install mcp)")
            return self

        for item in cfg_items:
            name = str(item.get("name", "unknown"))
            command = item.get("command")
            args = item.get("args", [])
            if not command:
                self._failed.append(f"{name}(缺 command)")
                continue
            try:
                params = StdioServerParameters(command=command, args=list(args))
                read, write = await stdio_client(params).__aenter__()
                session = await ClientSession(read, write).__aenter__()
                await session.initialize()
                tools = await session.list_tools()
                tools_dict = {t.name: t for t in tools.tools}
                self._servers.append([name, read, write, session, tools_dict])
                self._connected += 1
            except Exception as e:
                self._failed.append(f"{name}({e})")
        return self

    def summary(self) -> str:
        """输出已连接的外部 MCP 及工具清单（供 capabilities / LLM 注入）。"""
        if not self._servers:
            base = "未连接任何外部 MCP（可在 mcp_connectors.yaml 里添加）"
        else:
            lines = ["已连接外部 MCP:"]
            for name, *_rest, tools in self._servers:
                if tools:
                    lines.append(f"  - {name}: {', '.join(sorted(tools))}")
                else:
                    lines.append(f"  - {name}: (无工具)")
            base = "\n".join(lines)
        if self._failed:
            base += f"\n连接失败(已跳过): {'; '.join(self._failed)}"
        return base

    def tool_catalog(self) -> list:
        """返回所有外部工具的 [server, tool] 列表。"""
        out = []
        for name, *_rest, tools in self._servers:
            for tname in tools:
                out.append(f"{name}.{tname}")
        return out

    async def call(self, qualified: str, params: dict = None):
        """
        调用外部工具。qualified 形如 "server.tool"。
        返回工具输出；找不到连接/工具时返回说明。
        """
        if "." not in qualified:
            return f"格式应为 server.tool: {qualified}"
        sname, tname = qualified.split(".", 1)
        entry = next((e for e in self._servers if e[0] == sname), None)
        if entry is None:
            return f"未连接名为 {sname} 的外部 MCP"
        tools = entry[4]
        if tname not in tools:
            return f"{sname} 无工具 {tname}，可用: {', '.join(sorted(tools))}"
        try:
            # 有些工具参数要按 schema 处理，这里把 params 平铺为文字化调用
            result = await entry[3].call_tool(tname, params or {})
            text = result.content[0].text if result.content else str(result)
            return text
        except Exception as e:
            return f"调用 {qualified} 失败: {e}"

    async def close(self):
        """关闭全部外部连接。"""
        for name, read, write, session, *_ in self._servers:
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                pass
        self._servers = []


async def _self_test():
    """命令行自检：连接外部 MCP 并打印清单。"""
    ec = await ExternalConnector.create()
    print(ec.summary())
    await ec.close()


if __name__ == "__main__":
    asyncio.run(_self_test())