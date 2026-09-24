#!/usr/bin/env bash
# ============================================================================
# 后台循环守护 —— Universal-Game-Framework 计划定时执行（每 30 分钟一格）
# ----------------------------------------------------------------------------
# 为什么不用 crontab：本沙箱 /var/spool 文件系统禁止写文件，cron 的 spool 与
#   crontab 命令的 mkstemp 都被拒（Operation not permitted），且 cron 无 -c 可换
#   目录。故用循环兜底，效果等同「半小时一次定时任务」。
# 启动：bash devplan/cron_loop.sh   （建议用 run_in_background / nohup 拉起）
# 停止：pkill -f cron_loop.sh
# 迁移回系统 cron：等调度工具或沙箱放开后，把本脚本逻辑搬进 crontab 即可。
# ============================================================================
export TMPDIR=/home/g-bill/.workbuddy/tmp
export HOME=/home/g-bill
SCRIPT="/home/g-bill/文档/Default Project/Universal-Game-Framework/devplan/cron_exec.sh"
LOG="/home/g-bill/.workbuddy/tmp/cron_loop.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] loop 启动 pid=$$" >> "$LOG"
N=0
while true; do
  N=$((N+1))
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 第 $N 次触发" >> "$LOG"
  /bin/bash "$SCRIPT" >> "$LOG" 2>&1 || echo "[$(date)] 本次执行异常，继续下一轮" >> "$LOG"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 休眠 1800s" >> "$LOG"
  sleep 1800
done
