#!/usr/bin/env bash
# 一键启动 Universal-Game-Framework 全部服务（v2.0 · S12）
#   感知服务(perception_server) + MCP服务(mcp_server) + Agent主循环 + 简易面板
#
# 用法:
#   bash start_all.sh                  # 正常启动（后台）
#   bash start_all.sh --dry-run        # 干跑：只打印将执行什么，不真起进程
#   UGF_DRY_RUN=1 bash start_all.sh    # 同上，并把 dry-run 透传给子进程
#   bash start_all.sh --no-check       # 跳过启动自检（不推荐）
#   bash start_all.sh --help
#
# 可调环境变量:
#   UGF_PYTHON    解释器（默认自动探测 python3/python）
#   UGF_DRY_RUN   1 = 干跑 + 子进程透传（不碰键鼠 / 不调外部 LLM）
#   UGF_GAME      临时切换游戏档案（等价于 AGENT_GAME）
#
# 端口口径统一来自 config.yaml（perception_port / panel_port），脚本不写死。
set -uo pipefail
cd "$(dirname "$0")"

DRY_RUN="${UGF_DRY_RUN:-0}"
NO_CHECK=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=1 ;;
    --no-check)  NO_CHECK=1 ;;
    -h|--help)
      sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数: $arg（用 --help 查看用法）" >&2; exit 2 ;;
  esac
done

# ---- 解释器探测 --------------------------------------------------------
if [ -n "${UGF_PYTHON:-}" ]; then
  PY="$UGF_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi
command -v "$PY" >/dev/null 2>&1 || { echo "找不到 Python 解释器（用 UGF_PYTHON 指定）" >&2; exit 1; }

# ---- 端口从 config.yaml 读取（避免脚本与配置漂移） --------------------
port_of() {  # $1=键名  $2=默认值
  "$PY" - "$1" "$2" <<'EOF'
import re, sys
key, default = sys.argv[1], sys.argv[2]
try:
    text = open("config.yaml", encoding="utf-8").read()
except OSError:
    print(default); sys.exit(0)
m = re.search(rf"^\s*{re.escape(key)}\s*:\s*([0-9]+)", text, re.M)
print(m.group(1) if m else default)
EOF
}
PERCEPTION_PORT="$(port_of perception_port 5001)"
PANEL_PORT="$(port_of panel_port 5002)"

export UGF_DRY_RUN="$DRY_RUN"
[ -n "${UGF_GAME:-}" ] && export AGENT_GAME="$UGF_GAME"

if [ "$DRY_RUN" = "1" ]; then
  echo "==> [dry-run] 模式：只打印流程，不启动任何进程、不碰键鼠、不调外部 API"
fi

echo "==> 解释器: $PY ｜ 感知端口 $PERCEPTION_PORT ｜ 面板端口 $PANEL_PORT ｜ UGF_DRY_RUN=$DRY_RUN"

# ---- 1. 启动自检（v2.0：WARN 只降级不阻断，ERROR 才终止） --------------
if [ "$NO_CHECK" = "1" ]; then
  echo "==> 已跳过启动自检（--no-check）"
else
  echo "==> 启动自检..."
  if ! "$PY" boot_check.py --fail-fast; then
    echo "自检未通过，已终止启动。请先按上面指引修复。" >&2
    exit 1
  fi
fi

# ---- 2. 逐个拉起服务 --------------------------------------------------
start_one() {  # $1=pid 名  $2=说明  其余=命令
  local name="$1"; shift
  local desc="$1"; shift
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] 将启动 $desc: $*"
    return 0
  fi
  echo "==> 启动 $desc..."
  "$@" &
  echo $! > ".$name.pid"
}

start_one perception "感知服务 (http://127.0.0.1:$PERCEPTION_PORT/perceive)" \
  "$PY" perception_server.py
start_one mcp "MCP 服务"       "$PY" mcp_server.py
start_one agent "Agent 主循环" "$PY" agent_main.py
start_one panel "简易面板 (http://127.0.0.1:$PANEL_PORT)" \
  "$PY" admin_panel.py

# 容器前台模式：挂住 agent 进程，容器才不会一起动完就退出（Dockerfile CMD 使用）
if [ "${UGF_FOREGROUND:-0}" = "1" ] && [ "$DRY_RUN" != "1" ]; then
  echo "==> 前台模式：挂载 agent 主循环（ctrl-c 退出）"
  wait "$(cat .agent.pid 2>/dev/null)" 2>/dev/null || true
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] 全流程检查通过，退出码 0（未创建任何 .pid，未占用端口）"
else
  echo "全部已后台启动。用 bash stop_all.sh 停止。"
fi
