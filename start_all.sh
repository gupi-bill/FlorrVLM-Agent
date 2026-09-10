#!/usr/bin/env bash
# 一键启动 FlorrVLM-Agent 全部服务：
#   感知服务(perception_server) + MCP服务(mcp_server) + Agent主循环 + 简易面板
# 用法: bash start_all.sh
set -e
cd "$(dirname "$0")"
PY=python

echo "==> 启动感知服务 (端口 $(grep perception_port config.yaml))..."
$PY perception_server.py &  echo $! > .perception.pid

echo "==> 启动 MCP 服务..."
$PY mcp_server.py &         echo $! > .mcp.pid

echo "==> 启动 Agent 主循环..."
$PY agent_main.py &         echo $! > .agent.pid

echo "==> 启动简易面板 (http://127.0.0.1:$(grep panel_port config.yaml))..."
$PY admin_panel.py &        echo $! > .panel.pid

echo "全部已后台启动。用 stop_all.sh 停止。"