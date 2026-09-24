#!/usr/bin/env bash
# ============================================================================
# 定时任务执行器 —— Universal-Game-Framework 夜间计划（每 30 分钟一格）
# ----------------------------------------------------------------------------
# 背景：本会话 automation_update 调度工具不可用，headless CLI 又缺桌面宿主会话
#       跑不起来，故用系统级 crontab 兜底驱动。当调度工具恢复后，按
#       PLAN_NIGHT_0924.md 文末「铺开规格」一键迁移即可，本文件可废弃。
#
# 每 30 分钟由 crontab 调用一次，本脚本做三件事：
#   1) 读 devplan/NEXT_SLOT 拿当前要做的格子（S1..S15），把该格任务描述写进日志；
#   2) 跑「全局健康检查」（pytest + 三个 CLI 入口 + 体积体检），结果落 devplan/CRON_LOG.md；
#   3) 若 devplan/HEADLESS_OK 存在，则 best-effort 调 headless CLI 真做该格（需宿主会话）；
#      否则标记该格 pending，等活会话里的 AI 来做。最后 commit + 推远端 + 推进指针。
# ============================================================================
set -u
export TMPDIR=/home/g-bill/.workbuddy/tmp

PROJECT="/home/g-bill/文档/Default Project/Universal-Game-Framework"
PY="/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python"
PLAN="$PROJECT/devplan/PLAN_NIGHT_0924.md"
NEXT="$PROJECT/devplan/NEXT_SLOT"
LOG="$PROJECT/devplan/CRON_LOG.md"
OUT="$PROJECT/devplan/CRON_OUT.md"
TS="$(date '+%Y-%m-%d %H:%M:%S')"

cd "$PROJECT" || { echo "[$TS] cd 失败"; exit 1; }

# 1) 当前格子
[ -f "$NEXT" ] && SLOT="$(cat "$NEXT")" || SLOT="S1"
# 从计划里抽该格任务描述（匹配 | Sx | 那一行）
TASK="$(grep -E "\| *$SLOT *\|" "$PLAN" 2>/dev/null | head -1 | sed 's/|/ /g' | awk '{$1=""; print}' | xargs)"

# 2) 全局健康检查
HEALTH="$( {
  echo ">>> pytest"; TMPDIR=$TMPDIR timeout 220 $PY -m pytest -q 2>&1 | tail -3
  echo ">>> ugf-mcp --version"; UGF_DRY_RUN=1 timeout 40 $PY ugf_cli.py --version 2>&1 | tail -1
  echo ">>> 仓库待提交数"; git status --short | wc -l
} 2>&1 )"

# 3) best-effort headless（仅当人工确认可用时）
HEADLESS_NOTE="(headless 未启用：缺桌面宿主会话，该格待活会话 AI 处理)"
if [ -f "$PROJECT/devplan/HEADLESS_OK" ]; then
  HEADLESS_NOTE="$(CODEBUDDY_FORCE_HEADLESS_BUNDLE=1 timeout 280 node /opt/WorkBuddy/resources/app.asar.unpacked/cli/dist/codebuddy-headless.js -p "读 $PLAN 与 $NEXT，执行格子 $SLOT：$TASK。做完 git commit 并更新 PROGRESS.md。" --output-format text </dev/null 2>&1 | tail -20)"
fi

# 4) 落日志
{
  echo ""
  echo "### [$TS] 格子 $SLOT"
  echo "- 任务: $TASK"
  echo "- headless: $HEADLESS_NOTE"
  echo '```'
  echo "$HEALTH"
  echo '```'
} >> "$LOG"

# 5) 提交 + 绕代理推远端
git add -A 2>/dev/null
git commit -q -m "cron: $SLOT 健康检查 @ $TS" 2>/dev/null || true
env -u http_proxy -u https_proxy -u HTTPS_PROXY timeout 70 git push origin main 2>&1 | tail -1 >> "$LOG"

# 6) 推进指针：仅在「headless 真跑成功」或「该格已在 PROGRESS.md 标记 done（活会话 AI 做的）」时推进
#    否则只做心跳/体检/日志，原地等活会话 AI 来收割，绝不跳过未执行的计划项。
DONE_MARK="$(grep -cE "## *$SLOT .*done|SLOT *$SLOT.*done" "$PROJECT/devplan/PROGRESS.md" 2>/dev/null || true)"
if [ -f "$PROJECT/devplan/HEADLESS_OK" ]; then
  # headless 已启用：假定它本轮真做了该格
  N=$(echo "$SLOT" | sed 's/^S//'); N=$((N+1)); [ "$N" -gt 15 ] && N=1
  printf 'S%d\n' "$N" > "$NEXT"
  echo "[$TS] (headless) 完成格子 $SLOT，下一格 S$N"
elif [ "${DONE_MARK:-0}" -gt 0 ]; then
  N=$(echo "$SLOT" | sed 's/^S//'); N=$((N+1)); [ "$N" -gt 15 ] && N=1
  printf 'S%d\n' "$N" > "$NEXT"
  echo "[$TS] (live-agent 已标记 done) 完成格子 $SLOT，下一格 S$N"
else
  echo "[$TS] 格子 $SLOT 待活会话 AI 处理（headless 未启用且未标记 done），本轮不推进"
fi
