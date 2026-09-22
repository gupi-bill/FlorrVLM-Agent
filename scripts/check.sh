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

# 解释器优先级：UGF_PYTHON > 项目内 venv > 系统 python3
pick_python() {
  for cand in "${UGF_PYTHON:-}" .venv/bin/python venv/bin/python \
             "$HOME/.workbuddy/binaries/python/envs/ugf/bin/python" python3 python; do
    [ -n "$cand" ] || continue
    command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ] || continue
    if "$cand" -c "import yaml" >/dev/null 2>&1; then
      echo "$cand"; return 0
    fi
  done
  return 1
}

if ! PY="$(pick_python)"; then
  echo "❌ 找不到带核心依赖（pyyaml）的 Python 解释器。" >&2
  echo "   请用 UGF_PYTHON=/path/to/venv/bin/python bash scripts/check.sh 指定。" >&2
  exit 2
fi
echo "Python: $PY"

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

# S21：MCP 工具注册与 CLI 全命令冒烟接进门禁。
# 这两项此前各自能跑但没有进 check.sh —— "一条命令验证整个项目"名不副实：
# 工具表漂移、CLI 命令报 traceback 都不会在门禁里暴露。
if [ "$FAST" = "1" ]; then
  step 5 "MCP 工具核对（--fast 已跳过）"; echo "⏭  跳过"
  step 6 "CLI 全命令冒烟（--fast 已跳过）"; echo "⏭  跳过"
  step 7 "MCP 安装契约（--fast 已跳过）"; echo "⏭  跳过"
else
  step 5 "MCP 工具核对 mcp_tools_check"
  "$PY" tools/mcp_tools_check.py --strict || { echo "❌ MCP 工具核对失败"; exit 5; }

  step 6 "CLI 全命令冒烟 cli_smoke"
  "$PY" tools/cli_smoke.py --strict --timeout 12 || { echo "❌ CLI 冒烟失败"; exit 6; }

  # M 阶段：本项目对外交付形态是 MCP 服务，安装器与真实握手必须进门禁。
  step 7 "MCP 安装契约 install_mcp --check"
  "$PY" tools/install_mcp.py --check || { echo "❌ MCP 安装契约失败"; exit 7; }
fi

printf '\n===== ✅ 全部门禁通过 =====\n'
