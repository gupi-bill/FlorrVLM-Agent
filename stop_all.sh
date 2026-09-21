#!/usr/bin/env bash
# 优雅停止全部服务 + 清理临时产物（v2.0 · S12）
#
# 用法:
#   bash stop_all.sh                   # 停进程 + 清临时帧 + 轮转过期日志
#   bash stop_all.sh --dry-run         # 只打印将做什么，不真删
#   bash stop_all.sh --keep-logs       # 保留日志，只停进程
#   bash stop_all.sh --help
#
# 可调环境变量:
#   UGF_LOG_KEEP_DAYS   日志保留天数（默认 7，<=0 表示不清理）
#   UGF_PYTHON          解释器
#
# 清理范围（只在项目目录内，不碰任何业务文件）:
#   video_frames/               视频帧缓存
#   knowledge_archive/          归档临时目录中的空目录
#   run_logs/*                  超过保留天数的日志
#   *.tmp / .write_probe        运行期临时探针
set -uo pipefail
cd "$(dirname "$0")"

DRY_RUN="${UGF_DRY_RUN:-0}"
KEEP_LOGS=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=1 ;;
    --keep-logs)  KEEP_LOGS=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
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

[ "$DRY_RUN" = "1" ] && echo "==> [dry-run] 模式：只打印，不 kill、不删除"

# ---- 1. 停进程（先 TERM，最多等 5s，超时再 KILL；清理失效 pid 文件） ----
for name in agent panel mcp perception; do
  pidfile=".$name.pid"
  [ -f "$pidfile" ] || continue
  pid="$(cat "$pidfile" 2>/dev/null || echo '')"
  if [ -z "$pid" ]; then rm -f "$pidfile"; continue; fi
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "==> $name 的 pid $pid 已不存在，清理失效 pid 文件"
    [ "$DRY_RUN" = "1" ] || rm -f "$pidfile"
    continue
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] 将停止 $name (pid $pid)"
    continue
  fi
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null && echo "已强杀 $name (pid $pid)" || true
  else
    echo "已停止 $name (pid $pid)"
  fi
  rm -f "$pidfile"
done

# ---- 2. 清理临时产物 + 过期日志 ---------------------------------------
echo "==> 清理临时帧目录与过期日志..."
UGF_DRY_RUN_FLAG="$DRY_RUN" UGF_KEEP_LOGS="$KEEP_LOGS" \
UGF_LOG_KEEP_DAYS="${UGF_LOG_KEEP_DAYS:-7}" "$PY" - <<'EOF'
import os, shutil, time

base = os.getcwd()  # stop_all.sh 已 cd 到项目根目录
dry = os.getenv("UGF_DRY_RUN_FLAG") == "1"
keep_logs = os.getenv("UGF_KEEP_LOGS") == "1"
keep_days = float(os.getenv("UGF_LOG_KEEP_DAYS") or 7)


def rmdir(rel):
    p = os.path.join(base, rel)
    if os.path.isdir(p):
        if dry:
            print("[dry-run] 将删除目录", rel)
        else:
            shutil.rmtree(p, ignore_errors=True)
            if os.path.isdir(p):
                print("[warn] 目录清理失败（可能被外部策略拦截），请手动删除:", rel)
            else:
                print("已删除目录", rel)


def rmfile(p):
    if dry:
        print("[dry-run] 将删除文件", os.path.relpath(p, base))
    else:
        try:
            os.remove(p)
            print("已删除", os.path.relpath(p, base))
        except OSError as e:
            print("[warn] 文件清理失败:", os.path.relpath(p, base), e)


rmdir("video_frames")

# 过期日志轮转（run_logs 按 mtime）
logs = os.path.join(base, "run_logs")
if keep_logs:
    print("==> --keep-logs：跳过日志清理")
elif keep_days > 0 and os.path.isdir(logs):
    now = time.time()
    limit = keep_days * 86400
    for fn in sorted(os.listdir(logs)):
        p = os.path.join(logs, fn)
        if not os.path.isfile(p):
            continue
        if now - os.path.getmtime(p) > limit:
            rmfile(p)

# 运行期临时探针
for fn in sorted(os.listdir(base)):
    if fn.endswith(".tmp") or fn == ".write_probe":
        p = os.path.join(base, fn)
        if os.path.isfile(p):
            rmfile(p)
EOF

echo "全部停止完成。"
