#!/usr/bin/env bash
# 优雅停止全部服务，并清理临时帧目录。
# 用法: bash stop_all.sh
cd "$(dirname "$0")"
PY=python

for name in agent panel mcp perception resource; do
  if [ -f .$name.pid ]; then
    pid=$(cat .$name.pid)
    kill "$pid" 2>/dev/null && echo "已停止 $name (pid $pid)" || echo "$name 未在运行"
    rm -f .$name.pid
  fi
done

echo "==> 清理临时帧目录..."
$PY - <<'EOF'
import os, shutil
base = os.path.dirname(os.path.abspath(__file__))
for d in ("video_frames",):
    p = os.path.join(base, d)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
        print("已删除", p)
EOF
echo "全部停止完成。"