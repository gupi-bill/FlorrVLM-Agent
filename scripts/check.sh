#!/usr/bin/env bash
# 一条命令跑完全部门禁（S13 · 测试套件固化）
# =================================================
#   bash scripts/check.sh          # 全量：语法 → 自检 → 档案 → 单测
#   bash scripts/check.sh --fast   # 跳过 pytest（只做静态与自检，秒级）
#   bash scripts/check.sh --help
#
# 任一环节失败即整体退出码非 0（退出码 = 失败环节的编号，便于定位）。
# 环境变量：UGF_PYTHON 指定解释器（默认自动探测）。
set -uo pipefail
cd "$(dirname "$0")/.."

FAST=0
for arg in "$@"; do
  case "$arg" in
    --fast)  FAST=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $arg（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

if [ -n "${UGF_PYTHON:-}" ]; then
  PY="$UGF_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

step() { printf '\n===== [%s] %s =====\n' "$1" "$2"; }

step 1 "语法编译 compileall"
"$PY" -m compileall -q . || { echo "❌ 语法编译失败"; exit 1; }
echo "✅ 语法 OK"

step 2 "启动自检 boot_check（WARN 只降级，ERROR 才失败）"
"$PY" boot_check.py --fail-fast || { echo "❌ 启动自检存在 ERROR"; exit 2; }

step 3 "游戏档案校验 game_profile_check --all"
"$PY" game_profile_check.py --all || { echo "❌ 档案校验失败"; exit 3; }

if [ "$FAST" = "1" ]; then
  step 4 "pytest（--fast 已跳过）"
  echo "⏭  跳过"
else
  step 4 "单元测试 pytest"
  "$PY" -m pytest tests/ -q || { echo "❌ 单元测试失败"; exit 4; }
fi

printf '\n===== ✅ 全部门禁通过 =====\n'
