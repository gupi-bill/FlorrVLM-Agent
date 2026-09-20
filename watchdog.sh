#!/usr/bin/env bash
# FlorrVLM-Agent 看门狗 watchdog.sh（v1.0 稳定性保障）
# ==================================================
# 作用:
#   1. 崩溃自动重启: agent_main 异常退出后自动拉起（带退避，防崩溃-fly）
#   2. 内存/CPU 上限: 用 ulimit 限制单进程内存，避免无限增长吃满机器
#
# 用法:
#   bash watchdog.sh                       # 前台运行 Agent(with 心跳重启)
#   bash watchdog.sh --max-mem=512M        # 限制内存上限 512MB
#   nohup bash watchdog.sh > run_logs/watchdog.log 2>&1 &   # 后台守护
#
# 配合 systemd/supervisor 可作为进程管理器；退出码 143 视为主动停止。

set -u
cd "$(dirname "$0")"

PY=python

# ---- 可调参数 --------------------------------------------------------
MAX_RESTARTS=10        # 连续重启上限，超过则放弃（防崩溃-fly）
BACKOFF_STEP=2         # 每次退避递增秒数
MAX_MEM="${MAX_MEM:-}" # e.g. 512M / 1G，空=不限制

# ---- 内存/CPU 上限 ----------------------------------------------------
if [ -n "${MAX_MEM}" ]; then
    echo "==> 设置内存上限: ${MAX_MEM}"
    ulimit -v "${MAX_MEM}" 2>/dev/null || echo "警告: 当前系统不支持 ulimit -v（忽略）"
fi
# CPU 软性上限(秒/核)备注: Linux 可用 systemd 控制，本脚本聚焦内存，不强制。

# ---- 崩溃自愈主循环 --------------------------------------------------
restarts=0
while [ "${restarts}" -lt "${MAX_RESTARTS}" ]; do
    echo "==> [$(date '+%H:%M:%S')] 启动 agent_main (第 $((restarts+1)) 轮)"
    $PY agent_main.py
    code=$?
    if [ "${code}" -eq 143 ] || [ "${code}" -eq 0 ]; then
        echo "==> agent_main 正常退出(code=${code})，看门狗退出。"
        exit 0
    fi
    restarts=$((restarts + 1))
    backoff=$(( restarts * BACKOFF_STEP ))
    echo "==> agent_main 崩溃(code=${code})，${backoff}s 后自动重启 (${restarts}/${MAX_RESTARTS})"
    [ "${restarts}" -ge "${MAX_RESTARTS}" ] && break
    sleep "${backoff}"
done

echo "==> 连续崩溃 ${MAX_RESTARTS} 次，停止重启。请检查日志(run_logs/)。"
exit 1