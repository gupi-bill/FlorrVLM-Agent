#!/usr/bin/env bash
# 一键启动 FlorrVLM-Agent 全部服务：
#   感知服务(perception_server) + MCP服务(mcp_server) + Agent主循环 + 简易面板
# 用法: bash start_all.sh
set -e
cd "$(dirname "$0")"
PY=python

# v1.0 启动自检：缺依赖/配置时给修复指引，且以 fail-fast 终止。
echo "==> 启动自检..."
if ! $PY boot_check.py --fail-fast; then
    echo "自检未通过，已终止启动。请先按上面指引修复。"
    exit 1
fi

echo "==> 启动感知服务 (端口 $(grep perception_port config.yaml))..."
$PY perception_server.py &  echo $! > .perception.pid

echo "==> 启动 MCP 服务..."
$PY mcp_server.py &         echo $! > .mcp.pid

echo "==> 启动 Agent 主循环..."
$PY agent_main.py &         echo $! > .agent.pid

echo "==> 启动简易面板 (http://127.0.0.1:$(grep panel_port config.yaml))..."
$PY admin_panel.py &        echo $! > .panel.pid

# v2.0 资源调度器：低配机器 7×24 稳定（超内存自动降级清理）
if $PY resource_guard.py --once >/dev/null 2>&1; then
    echo "==> 启动资源调度器 (每30s自检，日志 run_logs/resource.log)..."
    nohup $PY resource_guard.py > /dev/null 2>&1 &  echo $! > .resource.pid
else
    echo "==> 资源调度器不可用，跳过（不影响其他服务）"
fi

echo "全部已后台启动。用 stop_all.sh 停止。"